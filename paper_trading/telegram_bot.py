"""Telegram Integration (Section A): a self-contained sending layer built
entirely on top of already-verified features (Confluence Scoring, Manual
Override, Drawdown Protection, Correlation Warnings, Trade Reasoning) --
nothing here computes a new trade decision or touches the trading loop,
it only formats and sends messages about decisions already made elsewhere.

Security: the bot token is stored in data/config/telegram_settings.json
(same JSON-config pattern as every other setting in this project) and is
NEVER returned by any GET endpoint or written to the log -- only a
"token_configured": true/false boolean is ever exposed after saving.

Proxy support: api.telegram.org is network-blocked in some countries at
the ISP/network level (TLS-handshake/SNI-based interference -- confirmed
via direct diagnostic testing, not a code-side timeout bug: DNS resolves
fine, a raw TCP connect succeeds instantly, but the actual HTTPS exchange
with that specific host stalls/resets while every other host works
normally). proxy_url (same write-only treatment as bot_token -- never
returned in plaintext, since it may embed a username:password) routes
ALL Telegram API calls through a configured SOCKS5 or HTTP proxy instead
of connecting directly, so this works unattended/24-7 without a manually
toggled VPN. Accepts any URL scheme Python's `requests` library itself
understands: "socks5://[user:pass@]host:port" (requires the PySocks
package, already added to requirements.txt) or "http://[user:pass@]host:port".
"""

import time
from datetime import datetime, timezone

import requests

from data_engine import config as base_config, storage, feature_toggles
from paper_trading import confluence as confluence_mod, insights

_DEFAULTS = {
    "bot_token": "",
    "channel_id": "",
    "auto_send_enabled": False,   # non-negotiable: OFF by default
    "auto_send_min_confluence_ratio": 1.0,  # require ALL counted factors aligned (e.g. 4/4) by default -- conservative
    "rate_limit_per_hour": 10,
    "send_close_followups": True,
    "proxy_enabled": False,
    "proxy_url": "",  # e.g. "socks5://user:pass@host:1080" or "http://user:pass@host:8080"
}

DISCLAIMER = ("This is an experimental signal from a system still under development. "
              "Not financial advice. Trade at your own risk.")

_API_CONNECT_TIMEOUT = 15
_API_READ_TIMEOUT = 30
_API_MAX_ATTEMPTS = 3
_API_RETRY_BACKOFF_SECONDS = 2


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_settings():
    return base_config.load_or_seed("telegram_settings.json", _DEFAULTS)


def save_settings(**fields):
    settings = load_settings()
    settings.update({k: v for k, v in fields.items() if v is not None})
    base_config.save_config("telegram_settings.json", settings)
    return settings


def public_settings():
    """Safe-to-display view -- never includes the raw token."""
    s = load_settings()
    return {
        "token_configured": bool(s.get("bot_token")),
        "channel_id": s.get("channel_id", ""),
        "auto_send_enabled": s.get("auto_send_enabled", False),
        "auto_send_min_confluence_ratio": s.get("auto_send_min_confluence_ratio", 1.0),
        "rate_limit_per_hour": s.get("rate_limit_per_hour", 10),
        "send_close_followups": s.get("send_close_followups", True),
        "proxy_enabled": s.get("proxy_enabled", False),
        "proxy_configured": bool(s.get("proxy_url")),
    }


def _rate_limited():
    settings = load_settings()
    limit = settings.get("rate_limit_per_hour", 10)
    since = (datetime.now(timezone.utc).timestamp() - 3600)
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
    sent = storage.count_telegram_messages_since(since_iso)
    return sent >= limit


def _build_proxies(settings):
    """Returns a requests-style {"http": url, "https": url} dict if a
    proxy is configured and enabled, else None (direct connection,
    today's default/original behavior -- nothing changes for anyone who
    never touches this setting). Both proxy entries point at the SAME
    url on purpose: Telegram's API is HTTPS-only, but requests still
    needs an "http" key present for some urllib3/proxy combinations to
    route correctly, and a single proxy server conventionally handles
    both schemes."""
    if not settings.get("proxy_enabled"):
        return None
    url = (settings.get("proxy_url") or "").strip()
    if not url:
        return None
    return {"http": url, "https": url}


def _raw_send(text):
    """Real HTTP call to the Telegram Bot API -- no simulation. Returns
    (success: bool, error: str|None).

    Retries up to _API_MAX_ATTEMPTS times (short backoff between attempts)
    on connection-level failures (timeout, connection reset, DNS/network
    errors) -- these are transient-network-shaped failures worth retrying.
    A real API response (even an error one, e.g. bad chat_id) is NOT
    retried -- that's a genuine, immediate answer from Telegram, retrying
    it would just get the same answer again.

    If proxy_enabled + proxy_url are configured, every request routes
    through that proxy instead of connecting directly -- see the module
    docstring for why (api.telegram.org is network-blocked in some
    countries at the ISP level, confirmed via direct diagnostic testing,
    not fixable by timeout/retry tuning alone)."""
    settings = load_settings()
    token, channel_id = settings.get("bot_token"), settings.get("channel_id")
    if not token or not channel_id:
        return False, "Telegram bot token or channel ID not configured yet"
    proxies = _build_proxies(settings)

    last_err = None
    for attempt in range(1, _API_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel_id, "text": text, "parse_mode": "HTML"},
                timeout=(_API_CONNECT_TIMEOUT, _API_READ_TIMEOUT),
                proxies=proxies,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, None
            return False, data.get("description", f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            last_err = repr(e)
            if attempt < _API_MAX_ATTEMPTS:
                time.sleep(_API_RETRY_BACKOFF_SECONDS)
    return False, f"failed after {_API_MAX_ATTEMPTS} attempts: {last_err}"


def test_proxy_connectivity():
    """Separate, lighter-weight check than send_test_message(): confirms
    the CONFIGURED PROXY ITSELF is reachable and can reach the public
    internet at all (via https://api.ipify.org, a tiny plain-text "what's
    my IP" endpoint), without needing a valid bot token/channel or
    touching Telegram. Useful for isolating "is my proxy server even
    working" from "is Telegram reachable through it" as two separate
    questions when troubleshooting."""
    settings = load_settings()
    proxies = _build_proxies(settings)
    if proxies is None:
        return {"ok": False, "error": "No proxy is configured/enabled -- nothing to test."}
    try:
        resp = requests.get("https://api.ipify.org?format=json", proxies=proxies,
                             timeout=(_API_CONNECT_TIMEOUT, _API_READ_TIMEOUT))
        if resp.status_code == 200:
            return {"ok": True, "exit_ip": resp.json().get("ip")}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except requests.RequestException as e:
        return {"ok": False, "error": repr(e)}


def send_test_message():
    """A1: real connection confirmation -- not simulated. Not rate-limited
    or logged to the trade audit trail (it's a connectivity check, not a
    trade signal), but still uses the exact same send path A2/A3 use."""
    ok, err = _raw_send(f"SINDHU test message -- connection successful.\n\n{DISCLAIMER}")
    return {"ok": ok, "error": err}


def _reason_text(position):
    """Reuses the existing plain-language reasoning already built for the
    dashboard (paper_trading.insights.humanize_reason) -- no new NLP."""
    try:
        return insights.humanize_reason(position.get("entry_reason"))
    except Exception:
        return position.get("entry_reason") or "No reason recorded."


def format_signal_message(position, confluence_result=None):
    direction_word = "LONG" if position["direction"] == "long" else "SHORT"
    lines = [
        f"<b>SINDHU Signal -- {direction_word}</b>",
        f"Strategy: {position.get('strategy_name') or 'Unknown'}",
        f"Coin: {position['symbol']}",
        f"Entry: {position['entry_price']}",
        f"Stop-Loss: {position.get('stop_loss', '-')}",
        f"Take-Profit: {position.get('take_profit', '-')}",
    ]
    if confluence_result:
        lines.append(f"Confluence: {confluence_result['label']}")
    lines.append(f"Reason: {_reason_text(position)}")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def send_signal_for_position(position_id, trigger_type="manual"):
    """The one real-send entry point both Manual Override (A2) and the
    automatic rule (A3) call. Rate-limited, always logged (success or
    failure) to telegram_message_log -- a full audit trail, per A4."""
    pos = storage.get_paper_position(position_id)
    now = _now_iso()
    if not pos:
        storage.log_telegram_message(position_id, None, None, trigger_type, "", False, "position not found", now)
        return {"ok": False, "error": "position not found"}

    if _rate_limited():
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, "rate limit reached for this hour", now,
        )
        return {"ok": False, "error": "rate limit reached for this hour"}

    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    try:
        conf = confluence_mod.score_confluence(
            pos.get("strategy_id"), pos["symbol"], exchange,
            pos.get("market_state"), pos.get("session"), pos["direction"],
        )
    except Exception:
        conf = None

    text = format_signal_message(pos, conf)
    ok, err = _raw_send(text)
    storage.log_telegram_message(
        position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type, text, ok, err, now,
    )
    return {"ok": ok, "error": err, "message": text}


# --------------------------------------------------------------- A3: automatic high-confidence rule

def evaluate_auto_send(position_id):
    """A3's documented rule -- ALL of the following, checked fresh each
    time (never cached, correctness over speed for a safety gate):
      1. auto_send_enabled is explicitly True in settings (OFF by default).
      2. Confluence ratio (passed/total factors) >= auto_send_min_confluence_ratio
         (default 1.0 -- i.e. every counted factor must be aligned; this is
         deliberately the strictest possible starting point since this is a
         gate for an UNSUPERVISED external message, not just a display label).
      3. The strategy is NOT currently paused by Drawdown Protection.
      4. No open position already exists on this same symbol from a
         DIFFERENT strategy in the correlation-flagged set (cheap proxy:
         reuses confluence's own "coin not already crowded" factor).
      5. The strategy's live realized PnL this session is >= 0 (a "positive
         live PnL trend" reading, in the plainest possible form: not
         currently net negative).
    Returns (should_send: bool, reason: str) -- reason is always populated,
    even when True, for auditability."""
    settings = load_settings()
    if not settings.get("auto_send_enabled", False):
        return False, "automatic sending is turned off in Settings"
    if feature_toggles.is_master_paused():
        return False, "all automation is currently paused (master switch)"

    pos = storage.get_paper_position(position_id)
    if not pos:
        return False, "position not found"

    strategy_id = pos.get("strategy_id")
    paused, pause_reason, _ = storage.is_strategy_paused(strategy_id)
    if paused:
        return False, f"strategy is paused by Drawdown Protection: {pause_reason}"

    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    conf = confluence_mod.score_confluence(
        strategy_id, pos["symbol"], exchange, pos.get("market_state"), pos.get("session"), pos["direction"],
    )
    if conf["total"] == 0:
        return False, "not enough data yet to score confluence"
    ratio = conf["passed"] / conf["total"]
    min_ratio = settings.get("auto_send_min_confluence_ratio", 1.0)
    if ratio < min_ratio:
        return False, f"confluence {conf['label']} below the required bar"

    pnl_total = storage.get_paper_realized_pnl_total(strategy_id)
    if pnl_total < 0:
        return False, f"strategy's live PnL this session is currently negative (${pnl_total:.2f})"

    return True, f"passed all automatic-send checks (confluence {conf['label']}, live PnL ${pnl_total:.2f})"


# --------------------------------------------------------------- A5: two-way awareness (close follow-up)

def send_close_followup(closed_position):
    """Called after a trade closes (see position_manager._close()) -- only
    sends a follow-up if a signal was actually sent for this exact position
    earlier (storage.has_telegram_signal_for_position), so the channel
    never gets a "result" message for a trade nobody was told about."""
    settings = load_settings()
    if not settings.get("send_close_followups", True) or feature_toggles.is_master_paused():
        return None
    position_id = closed_position["id"]
    if not storage.has_telegram_signal_for_position(position_id):
        return None

    pnl = closed_position.get("pnl") or 0.0
    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK-EVEN"
    text = (
        f"<b>SINDHU Result -- {outcome}</b>\n"
        f"Strategy: {closed_position.get('strategy_name') or 'Unknown'}\n"
        f"Coin: {closed_position['symbol']}\n"
        f"Exit: {closed_position.get('exit_price', '-')} ({closed_position.get('exit_reason', '-')})\n"
        f"Result: {'+' if pnl >= 0 else ''}{pnl:.2f} ({closed_position.get('pnl_pct', 0):.2f}%)\n\n"
        f"{DISCLAIMER}"
    )
    ok, err = _raw_send(text)
    storage.log_telegram_message(
        position_id, closed_position.get("strategy_id"), closed_position.get("strategy_name"),
        "close_followup", text, ok, err, _now_iso(),
    )
    return {"ok": ok, "error": err}
