"""External Signal Tracker settings -- its own JSON file under
data/config, same load_or_seed pattern as every other settings module,
but a completely separate file from paper_trading_settings.json so
nothing here can ever be read as a paper-trading setting or vice versa.
"""

from data_engine import config as base_config

_DEFAULTS = {
    # Telegram USER session (Phase 1) -- reading channels the CEO is a
    # member of needs a personal MTProto session, not a bot. api_id/
    # api_hash come from https://my.telegram.org (see README.md for the
    # exact steps). session_string is produced once by the interactive
    # login and then reused on every restart -- never re-entered.
    "telegram_api_id": None,
    "telegram_api_hash": None,
    "telegram_session_string": None,

    # Forwarding destination (Phase 5) -- deliberately a SEPARATE bot
    # token/channel id from paper_trading's own signal bot, so a mistake
    # in one can never send to the wrong place. Reusing the same bot
    # token is fine if the CEO wants that; the two settings are just never
    # coupled in code.
    "forward_bot_token": None,
    "forward_channel_id": None,
    "forwarding_enabled": True,

    "proving_trades_required": 30,
    "require_profitable_to_forward": True,  # CEO's explicit choice: 30 trades alone is NOT enough

    "ingestion_enabled": True,
}


def load():
    return base_config.load_or_seed("external_signals_settings.json", _DEFAULTS)


def save(settings):
    base_config.save_config("external_signals_settings.json", settings)


def update(**fields):
    settings = load()
    settings.update({k: v for k, v in fields.items() if v is not None})
    save(settings)
    return settings
