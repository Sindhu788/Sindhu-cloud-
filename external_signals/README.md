# External Signal Tracker

Tracks trading signals posted in external Telegram channels the CEO is a
member of, paper-trades them in a completely separate fake-money book,
scores each channel's real performance, and forwards a channel's future
signals to the CEO's own Telegram channel once it has genuinely proven
itself (30 closed trades **and** profitable overall).

## Isolation from the CEO's own Paper Trading / Evolution Engine

- **Tables**: every table this module touches is prefixed `external_` and
  keyed by `channel_id` (`external_channels`, `external_messages`,
  `external_signals`, `external_positions`, `external_channel_performance`
  -- see `data_engine/storage.py`'s "External Signal Tracker" schema
  section). None of these are ever written to by `paper_trading/` and
  none of `paper_positions`/`paper_account_state`/
  `paper_strategy_performance` are ever written to by this module --
  proven directly in `tests/test_external_paper_engine.py::
  test_never_writes_to_the_users_own_paper_trading_tables`.
- **Code**: `external_signals/` imports from `paper_trading` in exactly
  two places, both narrow, explicit, pure-function reuse with no shared
  state: `backtest_engine.engine.EMERGENCY_STOP_PCT` (the constant, so a
  missing stop-loss gets the identical fallback the CEO's own paper
  trades already use) and `paper_trading.telegram_bot.freshness_check`
  (the Signal Freshness Gate, reused verbatim for forwarding). Neither
  import reads or writes any `paper_*` table.
- **Evolution Engine**: reads `bot_strategies`/`evolution_jobs`/
  `champion_records` and `paper_positions` (via
  `evolution_engine/lesson_generator.py`, filtered by real `strategy_id`)
  -- it has no code path that ever queries an `external_*` table, so it
  cannot see, learn from, or evolve based on external-channel data.
- **Dashboards**: Strategy Lab, Challenge Mode, and the Maturity Tracker
  all read `paper_*`/`bot_strategies` data exclusively -- untouched by
  this module. The External Signal Tracker has its own dedicated nav
  page and CEO Control Room card, never merged into an existing one.
- **AI**: called only at message-parsing time
  (`external_signals/parser.py`'s Stage 2 AI fallback, and
  `external_signals/transcription.py` for voice notes). The paper-trading
  engine (`external_signals/paper_engine.py`) never calls AI.

## Credentials you need to obtain

### 1. Telegram reading (Phase 1) -- your OWN Telegram login

Bots cannot read a channel you've simply joined -- only a personal
Telegram session can, the same as opening Telegram on a new device.

1. Apne phone ya computer se **my.telegram.org** kholein.
2. Apna Telegram account wala phone number daalein, phir Telegram app
   par aane wala login code daalein.
3. **"API development tools"** par click karein.
4. Ek chota form aayega -- **"App title"** aur **"Short name"** mein kuch
   bhi likh dein (misaal: `SINDHU`), baaki sab khaali chod sakte hain.
5. **"Create application"** dabayein -- ab aapko **api_id** (sirf
   numbers) aur **api_hash** (letters + numbers ka mix) dikhega.
6. Yeh dono values SINDHU ke External Signal Tracker page par jaake save
   kar dein.
7. Login ka aakhri step (phone number + code, kabhi kabhi 2FA password
   bhi) ek live session mein saath milkar karte hain, kyunke Telegram
   code seedha aapke phone par bhejta hai -- yeh sirf ek dafa karna hota
   hai, uske baad session hamesha ke liye save ho jaata hai.

**Yeh sirf AAPKE apne Telegram account tak access deta hai -- api_id/
api_hash kisi ke saath share na karein.**

### 2. Voice-note transcription (Phase 2) -- no new credential needed

Uses Groq's `whisper-large-v3` endpoint through the SAME Groq API key
already configured for AI text extraction. Verified working with a real
test call during development.

### 3. Image (screenshot) OCR (Phase 2) -- NOT AVAILABLE

No OCR engine (Tesseract) and no working vision-capable AI model is
configured in this environment. Image messages are still fully captured
and stored (never lost), but are marked unprocessed with a clear reason
rather than guessed at. See `external_signals/ocr.py` for exactly what
would need to be added to turn this on.

### 4. Forwarding destination (Phase 5)

A Telegram bot token and destination chat id for the CEO's OWN channel
where forwarded signals should land -- can be the same bot already used
for the CEO's own paper-trading signals, or a separate one; either way
it's a separate setting (`external_signals/config.py`), never coupled to
`paper_trading`'s own bot settings in code.

## Known limitations (honest, as of this build)

- Image OCR is not implemented (see above).
- Text parsing (Stage 1, deterministic) handles the common
  `Coin:`/`Entry:`/`SL:`/`TP:` template shapes. Genuinely unstructured
  phrasing falls back to one small AI call (Stage 2); a message with no
  numbers at all is rejected without ever reaching AI, to save tokens.
- "Move SL to breakeven" / "close now" updates are only handled when the
  CEO (or a future automated matcher) explicitly links them to the
  original position id (`external_signals.paper_engine.move_stop_loss` /
  `close_position_manually`) -- there is no automatic NLP-based linking
  of a later update message back to its original signal yet.
- The live Telegram login (the interactive phone+code step) has not been
  completed in this environment -- it requires the CEO's real phone
  access and must be done in a live session together.
