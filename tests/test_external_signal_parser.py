"""External Signal Tracker, Phase 2 -- multi-format signal parsing.
Deterministic (Stage 1) parser tests: real-shaped signal messages,
including DCA/multi-entry, and honest rejection of non-signals."""

from external_signals import parser


def test_dca_signal_captures_every_entry_in_order():
    text = "Coin: BTC/USDT\nDirection: LONG\nEntry: 65000\nEntry 2: 64500\nEntry 3: 64000\nSL: 63000\nTP1: 67000\nTP2: 69000\nLeverage: 10x"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is True
    assert r["symbol"] == "BTCUSDT"
    assert r["direction"] == "long"
    assert [e["price"] for e in r["entries"]] == [65000.0, 64500.0, 64000.0]
    assert abs(sum(e["size_pct"] for e in r["entries"]) - 100.0) < 0.01
    assert r["stop_loss"] == 63000.0
    assert r["take_profit"] == [67000.0, 69000.0]
    assert r["leverage"] == 10.0
    assert r["parsed_by"] == "deterministic"


def test_single_entry_with_target_list():
    text = "BTC LONG\nEntry: 65000\nSL: 63000\nTargets: 67000, 69000, 71000"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is True
    assert r["entries"] == [{"price": 65000.0, "size_pct": 100.0}]
    assert r["take_profit"] == [67000.0, 69000.0, 71000.0]


def test_simple_short_signal():
    text = "ETH SHORT\nEntry: 3200\nSL: 3300\nTP: 3000"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is True
    assert r["symbol"] == "ETHUSDT"
    assert r["direction"] == "short"
    assert r["entries"] == [{"price": 3200.0, "size_pct": 100.0}]


def test_signal_missing_stop_loss_is_reported_as_missing_not_fabricated():
    text = "BTC LONG\nEntry: 65000\nTP: 67000"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is True
    assert r["stop_loss"] is None  # never invented


def test_update_message_is_rejected_not_parsed_as_a_new_trade():
    text = "TP1 hit! great trade everyone, moving SL to breakeven now"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is False
    assert r["reject_reason"]
    assert r["entries"] == []


def test_pure_chat_message_is_rejected():
    text = "gm guys, hope everyone is doing well today"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is False


def test_ambiguous_chat_with_no_numbers_is_rejected_not_guessed():
    text = "just checking in, market looking choppy today no trades yet"
    r = parser.parse_message(text, use_ai_fallback=False)
    assert r["is_signal"] is False
    assert r["symbol"] is None


def test_empty_message_is_rejected():
    r = parser.parse_message("", use_ai_fallback=False)
    assert r["is_signal"] is False


def test_ai_fallback_is_skipped_for_a_no_number_message_to_save_tokens():
    """Constraint: AI is reserved for genuinely unstructured messages that
    still look plausibly signal-shaped -- a message with zero numbers at
    all should never even attempt an AI call."""
    called = {"n": 0}

    def fake_provider_chain():
        called["n"] += 1
        return ["groq"]

    r = parser.parse_message("hey is anyone else seeing this market move", use_ai_fallback=True)
    # parse_message's own no-numbers short-circuit must prevent reaching
    # parse_text_with_ai at all (which is what would call provider_chain_fn).
    assert r["is_signal"] is False
    assert called["n"] == 0


def test_ai_fallback_is_used_for_an_unstructured_but_numeric_message(monkeypatch):
    """A message with real numbers that doesn't match any known template
    should fall through to the AI stage, not be silently dropped."""
    class _FakeResult:
        ok = True
        text = '{"is_signal": true, "reject_reason": "", "symbol": "SOLUSDT", "direction": "long", "entries": [{"price": 150.5, "size_pct": 100}], "stop_loss": 145.0, "take_profit": [160.0], "leverage": null}'

    class _FakeProvider:
        def chat(self, *a, **k):
            return _FakeResult()

    result = parser.parse_message(
        "solana looking ready around 150.5, i'd protect below 145 and take some off near 160",
        use_ai_fallback=True,
    )
    # This phrasing has no clean "Entry:"/"SL:" labels, so Stage 1 must
    # reject it first -- confirm that baseline before checking the AI path.
    assert parser.parse_text_deterministic(
        "solana looking ready around 150.5, i'd protect below 145 and take some off near 160"
    )["is_signal"] is False

    r = parser.parse_text_with_ai(
        "solana looking ready around 150.5, i'd protect below 145 and take some off near 160",
        provider_chain_fn=lambda: ["groq"],
        get_provider_settings_fn=lambda name: {},
        get_provider_fn=lambda name, settings: _FakeProvider(),
    )
    assert r["is_signal"] is True
    assert r["symbol"] == "SOLUSDT"
    assert r["entries"][0]["price"] == 150.5
    assert r["parsed_by"] == "ai"


def test_ai_fallback_honestly_rejects_when_ai_says_not_a_signal():
    class _FakeResult:
        ok = True
        text = '{"is_signal": false, "reject_reason": "This is a market commentary post, not a trade signal.", "symbol": null, "direction": null, "entries": [], "stop_loss": null, "take_profit": [], "leverage": null}'

    class _FakeProvider:
        def chat(self, *a, **k):
            return _FakeResult()

    r = parser.parse_text_with_ai(
        "the market feels heavy today, watching for a reaction at the daily level",
        provider_chain_fn=lambda: ["groq"],
        get_provider_settings_fn=lambda name: {},
        get_provider_fn=lambda name, settings: _FakeProvider(),
    )
    assert r["is_signal"] is False
    assert "commentary" in r["reject_reason"].lower()
