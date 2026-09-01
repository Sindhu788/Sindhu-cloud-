"""Phase 1 (capture) + Phase 2 (parse) orchestration for the External
Signal Tracker -- deliberately two separate stages, per the standing
requirement that a parsing failure must never lose the original message.

capture_message() ONLY ever writes to external_messages (raw text/media,
processed=0). process_pending_messages() is the only thing that reads
those rows, turns them into text (transcribing voice, OCR'ing images --
currently unavailable, see ocr.py), runs external_signals.parser on the
result, and writes the outcome to external_signals. If this second stage
throws, crashes, or is never run, the original message in
external_messages is completely untouched and can always be reprocessed
later -- nothing is ever lost.

Phase 3 (paper trade) + Phase 5 (forwarding eligibility check) happen
immediately after a successful parse, in the SAME pass -- per the task's
own speed requirement ("a stale copied signal has little value"), a new
signal is paper-traded and eligibility-checked the instant it's parsed,
never queued for a later batch job.
"""

import os
import uuid
from datetime import datetime, timezone

from data_engine import paths, storage
from external_signals import parser, transcription, ocr


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def capture_message(channel_id, content_type, telegram_message_id=None, raw_text=None,
                     raw_media_bytes=None, media_filename=None, received_at=None):
    """Stage 1: store the message exactly as received. Never parses,
    never calls AI/OCR/transcription -- purely a save. Returns the new
    message id."""
    if content_type not in ("text", "image", "voice"):
        raise ValueError(f"Unknown content_type: {content_type!r}")

    message_id = uuid.uuid4().hex[:16]
    media_path = None
    if raw_media_bytes is not None:
        os.makedirs(paths.EXTERNAL_SIGNALS_MEDIA_DIR, exist_ok=True)
        ext = os.path.splitext(media_filename or "")[1] or (".jpg" if content_type == "image" else ".ogg")
        media_path = os.path.join(paths.EXTERNAL_SIGNALS_MEDIA_DIR, f"{message_id}{ext}")
        with open(media_path, "wb") as f:
            f.write(raw_media_bytes)

    now = _now_iso()
    storage.save_external_message(
        message_id, channel_id, telegram_message_id, content_type, raw_text, media_path,
        received_at or now, now,
    )
    return message_id


def _resolve_text_for_message(msg):
    """Turns a captured message into plain text ready for parser.py, or
    (None, reason) if that isn't possible right now. Text messages pass
    straight through; voice is transcribed; images are honestly reported
    as unsupported (see ocr.py)."""
    if msg["content_type"] == "text":
        return msg["raw_text"], None

    if msg["content_type"] == "voice":
        if not msg["raw_media_path"] or not os.path.exists(msg["raw_media_path"]):
            return None, "Voice message has no stored audio file."
        with open(msg["raw_media_path"], "rb") as f:
            audio_bytes = f.read()
        text, error = transcription.transcribe_voice_note(audio_bytes, filename=os.path.basename(msg["raw_media_path"]))
        return text, error

    if msg["content_type"] == "image":
        if not msg["raw_media_path"] or not os.path.exists(msg["raw_media_path"]):
            return None, "Image message has no stored file."
        with open(msg["raw_media_path"], "rb") as f:
            image_bytes = f.read()
        text, error = ocr.extract_text_from_image(image_bytes)
        return text, error

    return None, f"Unhandled content_type: {msg['content_type']!r}"


def process_pending_messages(limit=50, use_ai_fallback=True):
    """Stage 2: for every unprocessed message, resolve it to text, parse
    it, save the (possibly rejected) signal, and mark the message
    processed. Returns a list of {"message_id", "processed": bool,
    "is_signal": bool|None, "error": str|None} -- one entry per message
    actually looked at, for real verification evidence."""
    results = []
    for msg in storage.list_unprocessed_external_messages(limit=limit):
        text, resolve_error = _resolve_text_for_message(msg)
        now = _now_iso()

        if text is None:
            storage.mark_external_message_processed(msg["id"], process_error=resolve_error)
            results.append({"message_id": msg["id"], "processed": True, "is_signal": None, "error": resolve_error})
            continue

        parsed = parser.parse_message(text, use_ai_fallback=use_ai_fallback)
        signal_id = uuid.uuid4().hex[:16]
        storage.save_external_signal(
            signal_id, msg["id"], msg["channel_id"], parsed["is_signal"], parsed["reject_reason"],
            parsed["symbol"], parsed["direction"], parsed["entries"], parsed["stop_loss"],
            parsed["take_profit"], parsed["leverage"], parsed["parsed_by"], now,
        )
        storage.mark_external_message_processed(
            msg["id"],
            raw_text_update=text if msg["content_type"] != "text" else None,
        )
        result = {
            "message_id": msg["id"], "processed": True, "is_signal": parsed["is_signal"],
            "error": None, "signal_id": signal_id,
        }

        if parsed["is_signal"]:
            # Phase 3: paper-trade every real signal automatically, in the
            # channel's own isolated book. Phase 5: check forwarding
            # eligibility for every NEW signal, right as it arrives -- the
            # whole point is speed, so this happens in the same pass as
            # parsing, not a separate delayed job.
            signal_dict = dict(parsed)
            signal_dict["id"] = signal_id
            signal_dict["channel_id"] = msg["channel_id"]
            try:
                from external_signals import paper_engine
                result["position_id"] = paper_engine.open_position_from_signal(signal_dict)
            except Exception as exc:
                result["paper_trade_error"] = str(exc)
            try:
                from external_signals import forwarder
                entry_time_ms = int(datetime.fromisoformat(msg["received_at"]).timestamp() * 1000)
                result["forwarding"] = forwarder.forward_signal_if_eligible(msg["channel_id"], signal_dict, entry_time_ms)
            except Exception as exc:
                result["forwarding"] = {"forwarded": False, "reason": f"Forwarding check failed: {exc}"}

        results.append(result)
    return results
