"""Phase 1 -- reading messages from Telegram channels the CEO is
genuinely a member of.

Bots CANNOT do this: a bot can only read a channel it has itself been
added to as an admin/member by the channel owner, which the CEO has no
control over for channels they merely joined. The only correct approach
is a personal Telegram USER session (MTProto, via Telethon) logging in AS
the CEO's own account -- exactly the same as opening Telegram on a new
device. This is why external_signals.config stores telegram_api_id/
telegram_api_hash/telegram_session_string, not a bot token, for reading.

TERMS OF SERVICE / RATE LIMITS: this module only ever reads channels the
CEO has explicitly added via external_signals.channels (i.e. channels
they are already a member of) -- it never joins a channel on its own,
never scrapes a channel the CEO hasn't added, and uses Telethon's own
built-in flood-wait handling (which automatically backs off when Telegram
asks it to) rather than a custom polling loop that could hammer the API.

Deferred import (matching ai_integration/file_extractors.py's own
pattern): this module can always be imported even before `pip install
telethon` has been run or before credentials exist -- every function
gives a clear, actionable error instead of crashing at import time.
"""

from datetime import datetime, timezone

from data_engine import storage
from external_signals import config as ext_config, ingest


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def telethon_available():
    try:
        import telethon  # noqa: F401
        return True
    except ImportError:
        return False


def _get_client():
    """Builds a Telethon client from the CEO's already-completed login
    session (telegram_session_string). Raises a clear, actionable
    RuntimeError if credentials/session aren't set up yet -- never a raw
    ImportError/AttributeError leaking to the caller."""
    if not telethon_available():
        raise RuntimeError(
            "Telethon isn't installed. Run: pip install telethon"
        )
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    settings = ext_config.load()
    api_id, api_hash, session_string = (
        settings.get("telegram_api_id"), settings.get("telegram_api_hash"), settings.get("telegram_session_string"),
    )
    if not api_id or not api_hash:
        raise RuntimeError(
            "Telegram api_id/api_hash not configured yet -- get them from https://my.telegram.org "
            "and save them on the External Signal Tracker settings page."
        )
    if not session_string:
        raise RuntimeError(
            "Not logged in yet -- complete the one-time interactive Telegram login "
            "(External Signal Tracker settings page) before reading channels."
        )
    return TelegramClient(StringSession(session_string), int(api_id), api_hash)


async def start_interactive_login(api_id, api_hash, phone_number, code_callback, password_callback=None):
    """The one-time interactive login (Phase 1 credential setup). Only
    ever run explicitly by the CEO from the settings page -- never
    automatic, never retried silently. code_callback()/password_callback()
    are awaited to get the code Telegram just sent and (if 2FA is on) the
    CEO's cloud password; the caller (the API layer) is responsible for
    actually prompting the CEO for these in the UI. Returns the
    session_string to persist via external_signals.config.update(...)."""
    if not telethon_available():
        raise RuntimeError("Telethon isn't installed. Run: pip install telethon")
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.send_code_request(phone_number)
        code = await code_callback()
        try:
            await client.sign_in(phone_number, code)
        except Exception as exc:
            if "password" in str(exc).lower() and password_callback:
                password = await password_callback()
                await client.sign_in(password=password)
            else:
                raise
    session_string = client.session.save()
    await client.disconnect()
    return session_string


async def fetch_new_messages(channel, limit=50):
    """Pulls up to `limit` messages newer than the last one already
    captured for this channel, and hands each one to
    ingest.capture_message() (Stage 1 only -- never parses here). Returns
    the list of new message ids captured. Real Telethon call -- requires
    a completed login (see start_interactive_login)."""
    client = _get_client()
    await client.connect()
    try:
        existing = storage.list_external_messages(channel["id"], limit=1)
        last_telegram_id = int(existing[0]["telegram_message_id"]) if existing and existing[0]["telegram_message_id"] else 0

        captured_ids = []
        async for msg in client.iter_messages(channel["telegram_identifier"], limit=limit, min_id=last_telegram_id):
            content_type, raw_text, media_bytes, filename = "text", msg.message or "", None, None
            if msg.photo:
                content_type = "image"
                media_bytes = await client.download_media(msg, file=bytes)
                filename = "signal.jpg"
            elif msg.voice:
                content_type = "voice"
                media_bytes = await client.download_media(msg, file=bytes)
                filename = "signal.ogg"
            elif not (msg.message or "").strip():
                continue  # nothing readable in this message (e.g. a sticker) -- skip, don't fabricate a blank signal

            message_id = ingest.capture_message(
                channel["id"], content_type, telegram_message_id=str(msg.id),
                raw_text=raw_text, raw_media_bytes=media_bytes, media_filename=filename,
                received_at=msg.date.replace(tzinfo=timezone.utc).isoformat() if msg.date else _now_iso(),
            )
            captured_ids.append(message_id)
        return captured_ids
    finally:
        await client.disconnect()


async def poll_all_enabled_channels(limit_per_channel=50):
    """The real ingestion tick: every enabled channel, newest messages
    only. Meant to be called on a short interval by a background job --
    Telethon's own flood-wait handling keeps this within Telegram's rate
    limits automatically."""
    settings = ext_config.load()
    if not settings.get("ingestion_enabled", True):
        return {}
    results = {}
    for channel in storage.list_external_channels(enabled_only=True):
        try:
            results[channel["id"]] = await fetch_new_messages(channel, limit=limit_per_channel)
        except Exception as exc:
            results[channel["id"]] = {"error": str(exc)}
    return results
