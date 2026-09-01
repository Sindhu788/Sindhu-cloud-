"""External Signal Tracker -- ingests trading signals posted in external
Telegram channels the CEO is a member of, paper-trades them in complete
isolation from the CEO's own strategies, tracks each channel's real
performance, and forwards a channel's signals to the CEO's own Telegram
channel once it has genuinely proven itself.

ISOLATION (see data_engine/storage.py's "External Signal Tracker" section
and the README in this directory for the full write-up): every table this
package touches is prefixed external_ and keyed by channel_id, never
strategy_id. Nothing here is imported by paper_trading/, evolution_engine/,
or backtest_engine/, and this package itself never imports paper_positions/
paper_account_state access functions. AI is called only at message-parsing
time (ai_integration is reused, never reimplemented) -- the paper-trading
engine in this package never calls AI at runtime.
"""
