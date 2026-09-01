"""Two-stage, honest signal parsing for the External Signal Tracker.

Stage 1 (always tried first, free, deterministic): regex extraction of the
handful of template shapes real Telegram signal channels actually use
("Coin:", "Entry:", "SL:", "TP1/TP2", "Leverage:"). Costs nothing, never
varies between runs.

Stage 2 (only when Stage 1 finds nothing usable, and only if the message
still looks plausibly signal-shaped): ONE small AI call, reusing
ai_integration's existing provider chain -- never a second implementation
of provider calling/retry logic.

Honesty rule throughout: a message that isn't clearly a trade signal (a
chat message, "TP1 hit! 🎉", "moved SL to breakeven", a greeting) is marked
is_signal=False with a plain reason -- NEVER guessed into a fabricated
trade. A signal missing its stop-loss is reported with stop_loss=None,
never a made-up number.

DCA / multi-entry support is not bolted on: `entries` is always a list of
{"price": float, "size_pct": float} from the very first entry point,
whether the message names one price or five.
"""

import re

_DIRECTION_WORDS = {
    "long": ["long", "buy", "bullish"],
    "short": ["short", "sell", "bearish"],
}

# A bare coin ticker, optionally with a quote asset / leading $ or #, at
# the start of a line or after a "Coin:"/"Pair:" label.
_SYMBOL_LABELED_RE = re.compile(r"(?:coin|pair|symbol)\s*[:\-]?\s*\$?#?([A-Za-z0-9]{2,15})(?:\s*/\s*(usdt|usd|busd))?", re.IGNORECASE)
_SYMBOL_BARE_RE = re.compile(r"\b\$?#?([A-Z]{2,10})(?:\s*/\s*(USDT|USD|BUSD))?\b(?!\s*%)")
_DIRECTION_RE = re.compile(r"\b(long|short|buy|sell|bullish|bearish)\b", re.IGNORECASE)

_ENTRY_LABEL_RE = re.compile(r"entr(?:y|ies)\s*(?:zone|price)?\s*[:\-]?\s*([0-9.,\-–\s/]+)", re.IGNORECASE)
_ENTRY_NUMBERED_RE = re.compile(r"entry\s*\d+\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_SL_RE = re.compile(r"(?:stop[\s\-]?loss|\bsl\b)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_TP_LABELED_RE = re.compile(r"(?:take[\s\-]?profit|target|\btp)\s*\d*\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_TARGETS_LIST_RE = re.compile(r"targets?\s*[:\-]?\s*([0-9.,\-–\s]+)", re.IGNORECASE)
_LEVERAGE_RE = re.compile(r"leverage\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*x?|\b([0-9]{1,3})x\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")

# Strong signals this message is an UPDATE to a previous signal, or pure
# commentary -- never parsed as a fresh trade even if it happens to
# contain a number or a coin ticker.
_UPDATE_OR_COMMENTARY_PHRASES = [
    "moved sl", "move sl", "move stop", "stop moved", "sl to breakeven", "sl to entry",
    "close now", "closed now", "closing now", "take profit hit", "tp hit", "tp1 hit", "tp2 hit", "tp3 hit",
    "hit tp", "target hit", "target reached", "stopped out", "sl hit", "cancel this", "cancelled",
    "update:", "reminder", "congrats", "well done", "good trade", "gm ", "good morning", "thank you",
]

_MIN_SIGNAL_SCORE = 2  # how many distinct real signal fields we need before trusting a match


def _extract_symbol(text):
    m = _SYMBOL_LABELED_RE.search(text)
    if m:
        return m.group(1).upper() + "USDT"
    # Bare form: first all-caps 2-10 letter token that isn't a common
    # non-coin acronym (SL/TP/RR/DCA etc.), immediately followed by /USDT
    # or standing alone as the first such token in the message.
    for m in _SYMBOL_BARE_RE.finditer(text):
        token = m.group(1).upper()
        if token in ("SL", "TP", "RR", "DCA", "USDT", "USD", "LONG", "SHORT", "BUY", "SELL"):
            continue
        return token + "USDT"
    return None


def _extract_direction(text):
    m = _DIRECTION_RE.search(text)
    if not m:
        return None
    word = m.group(1).lower()
    for direction, words in _DIRECTION_WORDS.items():
        if word in words:
            return direction
    return None


def _split_numbers(chunk):
    return [float(n) for n in _NUMBER_RE.findall(chunk)]


def _extract_entries(text):
    """Returns a list of {"price", "size_pct"} -- equal-split sizing
    unless the message states explicit percentages per entry (rare; not
    guessed at, just evenly split when unstated -- an honest default, not
    a fabricated one, since every entry is still real and comes from the
    text).

    DCA messages commonly write the FIRST entry as a bare "Entry:" line
    and every additional one as "Entry 2:"/"Entry 3:" -- both forms must
    be picked up together, in order, or the first (largest) entry silently
    vanishes."""
    prices = []
    m = _ENTRY_LABEL_RE.search(text)
    if m:
        # "Entry:" can itself hold a dash/comma-separated range ("Entry:
        # 65000-64500") -- take every number on that one line.
        prices.extend(_split_numbers(m.group(1)))
    for n in _ENTRY_NUMBERED_RE.findall(text):
        v = float(n)
        if v not in prices:
            prices.append(v)
    prices = [p for p in prices if p > 0]
    if not prices:
        return []
    size = round(100.0 / len(prices), 4)
    return [{"price": p, "size_pct": size} for p in prices]


def _extract_stop_loss(text):
    m = _SL_RE.search(text)
    return float(m.group(1)) if m else None


def _extract_take_profits(text):
    labeled = _TP_LABELED_RE.findall(text)
    if labeled:
        seen, out = set(), []
        for n in labeled:
            v = float(n)
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out
    m = _TARGETS_LIST_RE.search(text)
    if m:
        return _split_numbers(m.group(1))
    return []


def _extract_leverage(text):
    m = _LEVERAGE_RE.search(text)
    if not m:
        return None
    return float(m.group(1) or m.group(2))


def _looks_like_update_or_commentary(text):
    low = text.lower()
    return any(phrase in low for phrase in _UPDATE_OR_COMMENTARY_PHRASES)


def parse_text_deterministic(text):
    """Returns a dict: {"is_signal": bool, "reject_reason": str|None,
    "symbol":, "direction":, "entries": [...], "stop_loss":,
    "take_profit": [...], "leverage":, "parsed_by": "deterministic"}.
    Never raises. Never fabricates a missing field -- absent stays None/[]."""
    text = (text or "").strip()
    if not text:
        return _rejected("Empty message.")
    if _looks_like_update_or_commentary(text):
        return _rejected("Looks like an update/commentary on a previous signal, not a new trade.")

    symbol = _extract_symbol(text)
    direction = _extract_direction(text)
    entries = _extract_entries(text)
    stop_loss = _extract_stop_loss(text)
    take_profit = _extract_take_profits(text)
    leverage = _extract_leverage(text)

    score = sum(1 for v in (symbol, direction, entries) if v)
    if score < _MIN_SIGNAL_SCORE:
        return _rejected("Doesn't have enough clear signal fields (coin/direction/entry) to be confidently parsed.")

    return {
        "is_signal": True, "reject_reason": None,
        "symbol": symbol, "direction": direction, "entries": entries,
        "stop_loss": stop_loss, "take_profit": take_profit, "leverage": leverage,
        "parsed_by": "deterministic",
    }


def _rejected(reason):
    return {
        "is_signal": False, "reject_reason": reason,
        "symbol": None, "direction": None, "entries": [], "stop_loss": None,
        "take_profit": [], "leverage": None, "parsed_by": "deterministic",
    }


_AI_SYSTEM_PROMPT = (
    "You read ONE Telegram message from a crypto trading-signal channel. Decide: is this a FRESH trade "
    "signal (a new entry to take), or is it something else (chat, an update/close on a PREVIOUS signal, "
    "a celebration message, an announcement)? Only a fresh signal has is_signal=true.\n\n"
    "If it is a fresh signal, extract ONLY what the message actually states -- never invent a stop-loss, "
    "target, or entry price that isn't written. Multiple entry prices (DCA/averaging) are common -- list "
    "every one you find, evenly weighted unless the message states specific sizes.\n\n"
    "Respond with ONLY this JSON, no other text:\n"
    '{"is_signal": true|false, "reject_reason": "" or a short reason, "symbol": "BTCUSDT"|null, '
    '"direction": "long"|"short"|null, "entries": [{"price": number, "size_pct": number}], '
    '"stop_loss": number|null, "take_profit": [number, ...], "leverage": number|null}'
)


def parse_text_with_ai(text, provider_chain_fn=None, get_provider_settings_fn=None, get_provider_fn=None):
    """Stage 2 fallback -- ONE small AI call, only reached when Stage 1
    found nothing usable. Reuses ai_integration's own provider
    chain/config, never a second HTTP client. Injectable fn params exist
    only for tests (mocking network calls); real callers omit them and
    get the real ai_integration modules."""
    from ai_integration import config as ai_config
    from ai_integration import providers as ai_providers
    from ai_integration.schema import _parse_json_object, _CODE_FENCE_RE

    provider_chain_fn = provider_chain_fn or ai_config.provider_fallback_chain
    get_provider_settings_fn = get_provider_settings_fn or ai_config.get_provider_settings
    get_provider_fn = get_provider_fn or ai_providers.get_provider

    chain = provider_chain_fn()
    if not chain:
        return _rejected("AI is unavailable, and this message didn't match a known signal template.")

    for provider_name in chain:
        try:
            settings = get_provider_settings_fn(provider_name)
            provider = get_provider_fn(provider_name, settings)
            result = provider.chat(text, system=_AI_SYSTEM_PROMPT)
            if not result.ok or not (result.text or "").strip():
                continue
            cleaned = _CODE_FENCE_RE.sub("", result.text).strip()
            data = _parse_json_object(cleaned)
            if not isinstance(data, dict):
                continue
            if not data.get("is_signal"):
                return _rejected(str(data.get("reject_reason") or "AI judged this is not a fresh trade signal."))
            entries = [
                {"price": float(e["price"]), "size_pct": float(e.get("size_pct") or 0)}
                for e in (data.get("entries") or []) if e.get("price") is not None
            ]
            if not entries:
                return _rejected("AI said this was a signal but returned no usable entry price.")
            if all(e["size_pct"] == 0 for e in entries):
                even = round(100.0 / len(entries), 4)
                for e in entries:
                    e["size_pct"] = even
            return {
                "is_signal": True, "reject_reason": None,
                "symbol": data.get("symbol"), "direction": data.get("direction"),
                "entries": entries, "stop_loss": data.get("stop_loss"),
                "take_profit": [float(t) for t in (data.get("take_profit") or [])],
                "leverage": data.get("leverage"), "parsed_by": "ai",
            }
        except Exception:
            continue
    return _rejected("Every AI provider failed, and this message didn't match a known signal template.")


def parse_message(text, use_ai_fallback=True):
    """The single entry point: try deterministic first (free), only fall
    back to AI when Stage 1 rejected the message for lacking clear fields
    AND it still looks plausibly signal-shaped (has at least one number in
    it -- a pure "gm guys" message never burns an AI call)."""
    result = parse_text_deterministic(text)
    if result["is_signal"] or not use_ai_fallback:
        return result
    if not _NUMBER_RE.search(text or ""):
        return result  # no numbers at all -- definitely not worth an AI call
    if _looks_like_update_or_commentary(text):
        return result  # Stage 1 already correctly rejected this, don't second-guess it with AI
    return parse_text_with_ai(text)
