"""The Paper Trading Engine: ties every pipeline stage into one 24/7
background loop.

Live Market -> Coin Filter -> Market State -> Event Trigger -> Relevant
Strategies -> Relevant Lessons -> Decision Engine -> Confidence Score ->
Risk Manager -> Position Lock / Cooldown / Opposite-Signal / Duplicate
Protection / Trade Reservation -> Signal Priority -> Paper Trade -> Trade
Monitor -> Trade Close -> Reflection -> Evolution -> Database Save.

Runs as a single background thread (same concurrency model as the
existing backup thread / job_manager jobs elsewhere in this project) --
no multiprocessing, so Trade Reservation's in-memory set is a documented
safety net for future concurrency rather than a currently-necessary mutex.
"""

import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta as _timedelta

from data_engine import storage, config as base_config, feature_toggles
from data_engine.exchanges.registry import get_exchange_client
from data_engine.logging_setup import log as default_log

# Lightweight cloud runner support: same opt-in flag data_engine/resample.py
# checks. When set, coin selection comes directly from a live exchange +
# CoinGecko call (data_engine.symbols.pick_top_symbols, already fully
# DB-free) instead of storage.load_symbols() reading the locally-cached
# `symbols` table -- and the local-database "keep candles warm" step
# (live_feed.refresh_coins) is skipped entirely, since resample.get_ohlcv()
# already fetches fresh directly from the exchange on every call in this
# mode, so there is nothing to warm. Unset (the local laptop, always,
# unless deliberately configured otherwise): both lines below are never
# reached, byte-for-byte unchanged behavior.
LIVE_CANDLES_ONLY = os.environ.get("SINDHU_LIVE_CANDLES") == "1"

from paper_trading import config as pt_config
from paper_trading import coin_filter, live_feed, market_state, strategy_matcher, lesson_matcher
from paper_trading import signal_generator, confidence, risk_manager, guards, position_manager
from paper_trading import auto_avoid, drawdown_guard, lesson_auto_apply, telegram_bot, capital_allocation
from paper_trading import confluence


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _default_exchange():
    cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    return cfg["default"]


# Task 4 (Batch 2): the hourly Telegram fresh-signal sweep (see
# telegram_bot.sweep_unsent_qualifying_signals) is throttled to run at
# most this often, piggy-backing on this engine's own tick loop (already
# ticking every tick_interval_seconds, typically 60s) rather than a
# second background thread -- same pattern evolution_engine and the
# SINDHU Strategy scheduler already use for their own time-gated work.
TELEGRAM_SWEEP_INTERVAL_SECONDS = 3600


class PaperTradingEngine:
    def __init__(self):
        self._thread = None
        self._stop_flag = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self._event_tracker = market_state.EventTracker()
        self._guards = guards.GuardState()
        self._log = default_log
        self._on_event = None
        self._last_tick_at = None
        self._last_summary = {"shortlisted": [], "opened": 0, "closed": 0, "rejected": 0}
        self._tick_count = 0
        self._started_at = None
        self._last_telegram_sweep_at = None  # Task 4 (Batch 2) -- see TELEGRAM_SWEEP_INTERVAL_SECONDS

    # ------------------------------------------------------------ control
    def is_running(self):
        return self._running

    def start(self, log=None, on_event=None):
        """Every strategy enabled in paper_strategy_config (opt-in: a
        strategy with NO config row is treated as DISABLED, see
        storage.get_paper_strategy_config and strategy_matcher, which both
        default to enabled=False) competes every tick --
        multiple strategies each run their own independent book
        simultaneously (see paper_trading.guards.book_key and
        risk_manager/guards' per-book scoping), so starting the engine
        once is enough for however many strategies are active; the
        automation pipeline's Paper Trading handoff just enables a new
        strategy's config rather than restarting the engine scoped to it."""
        with self._lock:
            if self._running:
                return False
            self._log = log or default_log
            self._on_event = on_event
            self._stop_flag.clear()
            self._running = True
            self._started_at = _now_iso()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return True

    def stop(self):
        with self._lock:
            if not self._running:
                return False
            self._stop_flag.set()
        return True

    def status(self):
        """Overall (all books combined) plus a per-strategy breakdown --
        the combined balance is the sum of every book's own independent
        balance (each strategy starts from the same initial_balance and
        accrues its own realized pnl), never one shared/averaged number."""
        settings = pt_config.load()
        open_positions = storage.get_open_paper_positions()
        initial_balance = settings.get("initial_balance", 10000.0)
        states = storage.list_paper_account_states()

        # paper_account_state only gets a row once a book has CLOSED its
        # first trade. A freshly-activated strategy that already holds OPEN
        # positions therefore had no row at all, so it was completely
        # invisible here -- verified live with 26 open positions across 7
        # books while this returned an empty per_strategy list. Books with
        # open-but-not-yet-closed trades are merged in below at their true
        # state (realized pnl 0, no closed trades yet, real open count) so
        # the dashboard shows a strategy the moment it starts trading
        # rather than only after its first exit.
        books = {s["strategy_id"]: s for s in states}
        # open_positions above already holds every open position, so each
        # book's distinct-coin count is derived here instead of issuing one
        # extra get_open_paper_position_symbols() query PER BOOK. That per-
        # book query was cheap when this endpoint only ever saw the handful
        # of books with a closed trade, but the fix above made every
        # actively-trading book appear -- turning one status() call into
        # 1 + N round trips, each opening its own connection (see
        # storage.get_conn()). With the Paper Trading and Evolution engines
        # both writing, /api/paper-trading/status was exceeding the
        # frontend's 15s timeout. Same numbers, same distinct-coin
        # semantics, one query.
        open_symbols_by_book = {}
        for p in open_positions:
            book = p.get("strategy_id") or "__lessons__"
            books.setdefault(book, {
                "strategy_id": book, "realized_pnl_total": 0.0,
                "closed_count": 0, "win_count": 0,
            })
            open_symbols_by_book.setdefault(book, set()).add(p["symbol"])

        per_strategy = []
        for book, s in books.items():
            per_strategy.append({
                "strategy_id": None if book == "__lessons__" else book,
                "balance": round(initial_balance + s["realized_pnl_total"], 2),
                "realized_pnl_total": round(s["realized_pnl_total"], 2),
                "closed_count": s["closed_count"],
                "win_count": s["win_count"],
                "open_trades": len(open_symbols_by_book.get(book, ())),
            })
        # Every book counted here holds its own real starting capital, so a
        # book that is trading but has not closed anything yet must still
        # contribute its initial_balance -- previously it contributed
        # nothing at all, understating the combined figure.
        combined_balance = initial_balance * len(books) + sum(s["realized_pnl_total"] for s in books.values())
        return {
            "running": self._running,
            "dry_run": settings.get("dry_run", True),
            "started_at": self._started_at,
            "last_tick_at": self._last_tick_at,
            "tick_count": self._tick_count,
            "open_trades": len(open_positions),
            "queue": len(self._last_summary.get("shortlisted", [])),
            "balance": round(combined_balance, 2),
            "last_summary": self._last_summary,
            "per_strategy": per_strategy,
        }

    def run_single_tick_now(self):
        """Used by the "Dry Run test" / manual trigger from the dashboard,
        and by verification -- runs exactly one tick synchronously."""
        self._tick()
        return self._last_summary

    # ------------------------------------------------------------ loop
    def _loop(self):
        self._log("[paper-trading] engine started")
        self._emit({"type": "engine_started", "dry_run": pt_config.load().get("dry_run")})
        while not self._stop_flag.is_set():
            try:
                self._tick()
            except Exception as e:
                self._log(f"[paper-trading] tick error: {e!r}")
            interval = pt_config.load().get("tick_interval_seconds", 60)
            self._stop_flag.wait(interval)
        self._running = False
        self._log("[paper-trading] engine stopped")
        self._emit({"type": "engine_stopped"})

    def _emit(self, payload):
        if self._on_event:
            try:
                self._on_event(payload)
            except Exception:
                pass

    # ------------------------------------------------------------ tick
    def _tick(self):
        settings = pt_config.load()
        exchange = _default_exchange()
        client = get_exchange_client(exchange)
        if LIVE_CANDLES_ONLY:
            from data_engine.symbols import pick_top_symbols
            coins_cfg = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])
            symbols = pick_top_symbols(client, n=coins_cfg["num_coins"], quote=coins_cfg["quote_asset"])
        else:
            symbols = storage.load_symbols(exchange)
        if not symbols:
            self._last_summary = {"shortlisted": [], "opened": 0, "closed": 0, "rejected": 0}
            return

        shortlist = coin_filter.shortlist(exchange, symbols, settings.get("coin_filter_top_n", 20),
                                          log=self._log)
        shortlisted_symbols = [s["symbol"] for s in shortlist]
        if not LIVE_CANDLES_ONLY:
            live_feed.refresh_coins(client, shortlisted_symbols, log=self._log)

        opened, closed, rejected = 0, 0, 0
        self._guards.release_all()

        for entry in shortlist:
            symbol = entry["symbol"]
            try:
                snapshot = market_state.classify(exchange, symbol)
            except Exception as e:
                self._log(f"[paper-trading] market state error {symbol}: {e!r}")
                continue
            if snapshot is None:
                continue

            closed += len(position_manager.monitor_and_close(
                exchange, symbol, snapshot["price"],
                high=snapshot.get("high"), low=snapshot.get("low"),
            ))

            events = self._event_tracker.check(snapshot)
            if not events:
                continue

            try:
                o, r = self._process_coin(exchange, symbol, snapshot, settings)
                opened += o
                rejected += r
            except Exception as e:
                self._log(f"[paper-trading] decision error {symbol}: {e!r}")

        closed += self._monitor_orphaned_positions(exchange, client, shortlisted_symbols)

        # Lesson Auto-Apply (item 2): re-scan pattern memory once per tick
        # and promote/refresh any pattern that now clears the auto-apply
        # bar. Cheap (one indexed group-by query); never touches a trade
        # directly -- only writes rows that confidence.score() later reads.
        try:
            if feature_toggles.is_enabled("lesson_auto_apply_enabled"):
                lesson_auto_apply.promote_candidates()
        except Exception as e:
            self._log(f"[paper-trading] lesson auto-apply error: {e!r}")

        # Capital Allocation Engine (B2): recompute per-strategy multipliers
        # once per tick -- cheap (reuses already-computed risk metrics).
        try:
            if feature_toggles.is_enabled("capital_allocation_enabled"):
                capital_allocation.recompute_all_allocations()
        except Exception as e:
            self._log(f"[paper-trading] capital allocation error: {e!r}")

        # Task 4 (Batch 2): hourly Telegram fresh-signal sweep -- throttled
        # here rather than every tick (tick_interval_seconds is typically
        # 60s; this must not re-check all open positions' gating that
        # often). Never bypasses or weakens gating -- see
        # telegram_bot.sweep_unsent_qualifying_signals's own docstring.
        now = time.monotonic()
        if self._last_telegram_sweep_at is None or (now - self._last_telegram_sweep_at) >= TELEGRAM_SWEEP_INTERVAL_SECONDS:
            self._last_telegram_sweep_at = now
            try:
                sent = telegram_bot.sweep_unsent_qualifying_signals()
                if sent:
                    self._log(f"[paper-trading] Telegram hourly sweep sent {len(sent)} previously-unsent signal(s): "
                               f"{[s['position_id'] for s in sent]}")
            except Exception as e:
                self._log(f"[paper-trading] Telegram hourly sweep error: {e!r}")

        self._tick_count += 1
        self._last_tick_at = _now_iso()
        self._last_summary = {
            "shortlisted": shortlisted_symbols, "opened": opened, "closed": closed, "rejected": rejected,
        }
        self._emit({"type": "tick", "summary": self._last_summary, "at": self._last_tick_at})

    def _monitor_orphaned_positions(self, exchange, client, shortlisted_symbols):
        """Trade Monitor must keep watching a coin's open position even if
        it later drops out of this tick's shortlist -- fetched via one
        cheap ticker call instead of a full candle refresh."""
        open_symbols = {p["symbol"] for p in storage.get_open_paper_positions(exchange)}
        orphaned = [s for s in open_symbols if s not in shortlisted_symbols]
        if not orphaned:
            return 0
        try:
            coins_cfg = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])
            tickers = client.get_tickers(coins_cfg["quote_asset"])
        except Exception as e:
            self._log(f"[paper-trading] orphaned-position ticker fetch failed: {e!r}")
            return 0
        closed = 0
        for symbol in orphaned:
            ticker = tickers.get(symbol)
            if not ticker:
                # A symbol with an OPEN position that's vanished from the
                # exchange's own ticker batch (delisted, or the exchange is
                # otherwise no longer quoting it) used to hit a silent
                # `continue` here -- the position just sat open forever with
                # zero visibility that anything was wrong. Logged (like every
                # other per-symbol failure in this file) AND recorded as a
                # real alert (throttled to once per hour per symbol, reusing
                # paper_alerts -- `strategy_id` column repurposed to hold the
                # symbol here since this is a data/symbol-level issue, not a
                # strategy-level one) so it's visible on the dashboard, not
                # only in server logs a person would have to go find.
                self._log(f"[paper-trading] orphaned position on {symbol} missing from ticker batch "
                          f"(possibly delisted or no longer quoted) -- position still open, price stale")
                since = (datetime.now(timezone.utc) - _timedelta(hours=1)).isoformat()
                if not storage.get_recent_paper_alert("orphaned_position_missing_ticker", symbol, since):
                    storage.create_paper_alert(
                        "orphaned_position_missing_ticker", symbol, None,
                        f"{symbol} has an open position but the exchange stopped returning a price for it "
                        f"(possibly delisted) -- its stop-loss/take-profit can't be checked until it "
                        f"reappears. Consider closing it manually.",
                        "warning", _now_iso(),
                    )
                continue
            closed += len(position_manager.monitor_and_close(exchange, symbol, ticker["price"]))
        return closed

    def _process_coin(self, exchange, symbol, snapshot, settings):
        market_type = snapshot["market_state"]
        strategies = strategy_matcher.relevant_strategies(symbol, market_type)
        lessons = lesson_matcher.relevant_lessons(market_type, settings.get("lesson_default_timeframe", "1h"))

        candidates = signal_generator.generate_candidates(exchange, symbol, strategies, lessons, settings)
        if not candidates:
            return 0, 0

        rejected = 0
        approved = []
        for c in candidates:
            if not c["approved"]:
                self._log_decision(exchange, symbol, c, "rejected", c["veto_reason"], snapshot)
                rejected += 1
                continue
            fingerprint = guards.signal_fingerprint(exchange, symbol, c)
            if self._guards.is_duplicate(fingerprint):
                self._log_decision(exchange, symbol, c, "rejected", "duplicate signal (unchanged market condition)", snapshot)
                rejected += 1
                continue
            c["confidence"] = confidence.score(c, snapshot)
            approved.append(c)

        if not approved:
            return 0, rejected

        # Group by book (strategy_id, or the shared "__lessons__" book for
        # lesson-only candidates) and process each group independently --
        # this is what lets two different strategies BOTH open a position
        # on the same coin in the same tick, even in opposite directions,
        # instead of one silently winning a single engine-wide priority
        # contest. Within one group (the same strategy, or several lessons
        # firing together), Signal Priority still picks one winner, same as
        # before -- a strategy never fights against itself.
        groups = {}
        for c in approved:
            groups.setdefault(guards.book_key(c), []).append(c)

        opened = 0
        for book, group in groups.items():
            pick = guards.rank_candidates(group, settings.get("priority_rule", "confidence"))
            o, r = self._open_if_allowed(book, exchange, symbol, pick, snapshot, settings)
            opened += o
            rejected += r

        return opened, rejected

    def _open_if_allowed(self, book, exchange, symbol, pick, snapshot, settings):
        if not self._guards.reserve(book, exchange, symbol):
            return 0, 0

        paused, pause_reason, _ = storage.is_strategy_paused(book)
        if paused:
            self._log_decision(exchange, symbol, pick, "rejected",
                                f"strategy paused (Drawdown Protection): {pause_reason}", snapshot)
            return 0, 1

        avoid_reason = (
            auto_avoid.is_avoided(book, symbol, snapshot.get("market_state"), snapshot.get("session"))
            if feature_toggles.is_enabled("auto_avoid_enabled") else None
        )
        if avoid_reason:
            self._log_decision(exchange, symbol, pick, "rejected", avoid_reason, snapshot)
            return 0, 1

        side = "long" if pick["direction"] == "bullish" else "short"

        if guards.position_locked(book, exchange, symbol, side):
            self._log_decision(exchange, symbol, pick, "rejected", "position lock: identical position already open", snapshot)
            return 0, 1

        cooldown_min = settings.get("cooldown_minutes", 15)
        if guards.cooldown_active(book, exchange, symbol, side, cooldown_min):
            self._log_decision(exchange, symbol, pick, "rejected", f"cooldown active ({cooldown_min}min)", snapshot)
            return 0, 1

        action, info = guards.resolve_opposite_signal(book, exchange, symbol, side, settings.get("opposite_signal_policy", "block"))
        if action == "block":
            self._log_decision(exchange, symbol, pick, "rejected", info, snapshot)
            return 0, 1
        if action == "close_and_reverse":
            position_manager.force_close(info, snapshot["price"], reason="reversed")

        risk_ok, risk_reason, size, risk_amount = risk_manager.evaluate(book, symbol, pick, settings, exchange=exchange)
        if not risk_ok:
            self._log_decision(exchange, symbol, pick, "rejected", risk_reason, snapshot)
            return 0, 1

        if settings.get("dry_run", True):
            self._log_decision(exchange, symbol, pick, "dry_run",
                                "dry run -- would have opened this trade", snapshot)
            return 0, 0

        pos = position_manager.open_position(exchange, symbol, pick, size, risk_amount, pick["confidence"], snapshot)
        self._log_decision(exchange, symbol, pick, "opened", "trade opened", snapshot, position_id=pos["id"])
        self._log(f"[paper-trading] OPENED {symbol} {pos['direction']} @ {pos['entry_price']:.6f} "
                  f"(strategy={pick.get('strategy_name') or pick.get('lesson_title')})")
        self._emit({"type": "position_opened", "position": pos})

        # Historical Confluence Score Tracking (Remaining Dashboard
        # Enhancements, item 5): logs this signal's confluence score so its
        # trend over time can be shown, not just the current value -- fully
        # independent of Telegram (confluence.score_confluence() is a plain
        # paper_trading module), logged for every real position regardless
        # of Telegram/auto-send settings.
        try:
            conf = confluence.score_confluence(book, symbol, exchange, snapshot.get("market_state"),
                                                snapshot.get("session"), pick["direction"])
            if conf["total"] > 0:
                storage.save_confluence_score(book, pos["id"], conf["passed"] / conf["total"], _now_iso())
        except Exception as e:
            self._log(f"[paper-trading] confluence history logging failed: {e!r}")

        # A3 + Task 4 (Priority Batch 1): automatic Telegram signal, dual
        # tier -- OFF by default (telegram_bot.evaluate_auto_send_tier
        # checks the settings flag first and short-circuits immediately if
        # it's not explicitly enabled). Tries the HIGH tier (full
        # confluence + the 25-trade Wilson gate, unchanged) first; if
        # nothing currently qualifies for that, falls back to the LOW tier
        # so signal flow doesn't stop entirely -- only a genuine "high"
        # tier result gets the High Confidence marker on the message.
        try:
            tier, reason = telegram_bot.evaluate_auto_send_tier(pos["id"])
            if tier is not None:
                telegram_bot.send_signal_for_position(pos["id"], trigger_type="automatic", high_confidence=(tier == "high"))
                self._log(f"[paper-trading] Telegram auto-signal sent for {pos['id']} (tier={tier}): {reason}")
        except Exception as e:
            self._log(f"[paper-trading] Telegram auto-send check failed: {e!r}")

        return 1, 0

    def _log_decision(self, exchange, symbol, candidate, decision, reason, snapshot, position_id=None):
        storage.log_paper_decision({
            "exchange": exchange, "symbol": symbol, "direction": candidate.get("direction"),
            "decision": decision, "reason": reason,
            "strategy_id": candidate.get("strategy_id"), "strategy_name": candidate.get("strategy_name"),
            "lesson_ids": candidate.get("lesson_ids", []), "confidence": candidate.get("confidence"),
            "market_state": snapshot.get("market_state"), "session": snapshot.get("session"),
            "timeframe": candidate.get("timeframe"), "position_id": position_id,
            "market_snapshot": snapshot, "created_at": _now_iso(),
        })


engine = PaperTradingEngine()


def resume_engine_on_startup():
    """Batch 9, Task 3: restores the Paper Trading Engine to the CEO's
    last EXPLICIT start/stop choice (pt_config's "engine_enabled",
    written the instant /api/paper-trading/start or /stop is called --
    see sindhu_web/api/paper_trading.py) rather than always defaulting
    to off just because PaperTradingEngine._running starts False on
    every fresh process. Never forces it on: if it was deliberately
    stopped, engine_enabled is False and this is a no-op. Same
    "resume only if it was already running" contract as
    evolution_engine.engine.resume_evolution_jobs_on_startup, called
    once from sindhu_web/server.py's lifespan."""
    enabled = pt_config.load().get("engine_enabled", False)
    if enabled:
        default_log("[paper-trading] Restoring to ON -- it was running when the server last stopped.")
        engine.start(log=default_log)
    else:
        default_log("[paper-trading] Staying OFF -- it was off when the server last stopped.")
