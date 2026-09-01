"""External Signal Tracker API -- every endpoint here reads/writes ONLY
external_signals.* modules and the external_* database tables. Never
imports paper_trading's engine/position_manager/guards, never touches
paper_positions/paper_account_state/paper_strategy_performance.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from external_signals import channels, channel_stats, config as ext_config, forwarder, ingest, paper_engine

router = APIRouter()


# ------------------------------------------------------------ Phase 1: channel management

class AddChannelRequest(BaseModel):
    name: str
    telegram_identifier: str


@router.get("/api/external-signals/channels")
def list_channels():
    return {"channels": channels.list_channels()}


@router.post("/api/external-signals/channels")
def add_channel(req: AddChannelRequest):
    try:
        channel_id = channels.add_channel(req.name, req.telegram_identifier)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"channel_id": channel_id}


@router.post("/api/external-signals/channels/{channel_id}/enable")
def enable_channel(channel_id: str):
    channels.set_enabled(channel_id, True)
    return {"ok": True}


@router.post("/api/external-signals/channels/{channel_id}/disable")
def disable_channel(channel_id: str):
    channels.set_enabled(channel_id, False)
    return {"ok": True}


class RenameChannelRequest(BaseModel):
    name: str


@router.post("/api/external-signals/channels/{channel_id}/rename")
def rename_channel(channel_id: str, req: RenameChannelRequest):
    try:
        channels.rename(channel_id, req.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@router.delete("/api/external-signals/channels/{channel_id}")
def remove_channel(channel_id: str):
    channels.remove(channel_id)
    return {"ok": True}


# ------------------------------------------------------------ Phase 1/2: messages + parsing

@router.get("/api/external-signals/channels/{channel_id}/messages")
def get_messages(channel_id: str, limit: int = 100):
    from data_engine import storage
    return {"messages": storage.list_external_messages(channel_id, limit=limit)}


class ManualMessageRequest(BaseModel):
    content_type: str = "text"
    raw_text: Optional[str] = None


@router.post("/api/external-signals/channels/{channel_id}/messages/manual")
def add_manual_message(channel_id: str, req: ManualMessageRequest):
    """For testing/demo and for a channel the CEO reads by hand and
    pastes in -- goes through the exact same capture+process pipeline as
    a Telegram-sourced message."""
    from data_engine import storage
    if not storage.get_external_channel(channel_id):
        raise HTTPException(404, "channel not found")
    message_id = ingest.capture_message(channel_id, req.content_type, raw_text=req.raw_text)
    return {"message_id": message_id}


@router.post("/api/external-signals/process-pending")
def process_pending(limit: int = 50):
    results = ingest.process_pending_messages(limit=limit)
    return {"results": results}


@router.get("/api/external-signals/channels/{channel_id}/signals")
def get_signals(channel_id: str, is_signal: Optional[bool] = None, limit: int = 100):
    from data_engine import storage
    return {"signals": storage.list_external_signals(channel_id, is_signal=is_signal, limit=limit)}


# ------------------------------------------------------------ Phase 3: paper positions

@router.post("/api/external-signals/signals/{signal_id}/open-position")
def open_position(signal_id: str):
    from data_engine import storage
    matches = [s for s in storage.list_external_signals(limit=1000) if s["id"] == signal_id]
    if not matches:
        raise HTTPException(404, "signal not found")
    signal = matches[0]
    if not signal["is_signal"]:
        raise HTTPException(400, "This message was not parsed as a real signal.")
    position_id = paper_engine.open_position_from_signal(signal)
    if not position_id:
        raise HTTPException(400, "Signal has no usable entry price.")
    return {"position_id": position_id}


@router.post("/api/external-signals/check-price-updates")
def check_price_updates(symbol: Optional[str] = None):
    return {"events": paper_engine.check_price_updates(symbol=symbol)}


@router.get("/api/external-signals/channels/{channel_id}/positions")
def get_positions(channel_id: str, status: Optional[str] = None):
    from data_engine import storage
    return {"positions": storage.list_external_positions(channel_id=channel_id, status=status)}


# ------------------------------------------------------------ Phase 4: dashboard

@router.get("/api/external-signals/channels/{channel_id}/report")
def get_channel_report(channel_id: str):
    report = channel_stats.channel_report(channel_id)
    if not report:
        raise HTTPException(404, "channel not found")
    return report


@router.get("/api/external-signals/comparison")
def get_comparison():
    return {"channels": channel_stats.comparison_view()}


# ------------------------------------------------------------ Phase 5: forwarding + settings

@router.get("/api/external-signals/channels/{channel_id}/eligibility")
def get_eligibility(channel_id: str):
    eligible, reason = forwarder.is_channel_eligible_for_forwarding(channel_id)
    return {"eligible": eligible, "reason": reason}


@router.get("/api/external-signals/settings")
def get_settings():
    settings = dict(ext_config.load())
    # Never expose the raw session string / api_hash to the frontend.
    settings["telegram_session_string"] = "SET" if settings.get("telegram_session_string") else None
    settings["telegram_api_hash"] = "SET" if settings.get("telegram_api_hash") else None
    settings["forward_bot_token"] = "SET" if settings.get("forward_bot_token") else None
    return settings


class UpdateSettingsRequest(BaseModel):
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    forward_bot_token: Optional[str] = None
    forward_channel_id: Optional[str] = None
    forwarding_enabled: Optional[bool] = None
    ingestion_enabled: Optional[bool] = None
    require_profitable_to_forward: Optional[bool] = None


@router.post("/api/external-signals/settings")
def update_settings(req: UpdateSettingsRequest):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    ext_config.update(**fields)
    return {"ok": True}
