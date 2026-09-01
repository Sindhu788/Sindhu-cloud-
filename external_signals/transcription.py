"""Voice-note transcription for the External Signal Tracker.

Uses Groq's hosted Whisper endpoint (whisper-large-v3) -- the SAME Groq
API key already configured for text extraction (ai_integration.config),
no new credential needed. This is a genuinely verified, working path (a
real test call against the live endpoint returned a correct transcript
during development), unlike image OCR (see ocr.py), which is honestly
left unimplemented because no working engine is available in this
environment.

Once a voice note is transcribed, the resulting text goes through the
EXACT SAME parser.parse_message() as a text message -- transcription only
turns audio into text, it never does its own signal extraction."""

import requests

_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_MODEL = "whisper-large-v3"


def transcribe_voice_note(file_bytes, filename="voice.ogg", timeout=30):
    """Returns (text: str|None, error: str|None). Never raises."""
    from ai_integration import config as ai_config

    settings = ai_config.get_provider_settings("groq")
    api_key = settings.get("api_key")
    if not api_key:
        return None, "No Groq API key configured -- voice transcription needs the same key used for AI text parsing."

    try:
        resp = requests.post(
            _TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, file_bytes, "audio/ogg")},
            data={"model": _MODEL},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return None, f"Network error reaching Groq: {exc}"

    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        text = resp.json().get("text")
    except ValueError:
        return None, "Groq returned a response that wasn't valid JSON."

    if not text or not text.strip():
        return None, "Transcription came back empty."
    return text.strip(), None
