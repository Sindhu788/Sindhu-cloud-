"""YouTube Import -- one of the supported inputs for the AI Knowledge
Learning Engine, alongside pasted text and uploaded PDF/DOCX/TXT files.
Downloads the video's public transcript, strips transcript noise (filler
words, [Music]/[Applause] tags, repeated whitespace), and hands the cleaned
text into the exact same import pipeline as any other pasted document -- no
separate downstream code path.

Uses the youtube-transcript-api package (no API key required -- it reads the
video's own public caption track), lazy-imported exactly like pypdf/
python-docx in file_extractors.py so the rest of SINDHU never depends on it
being installed. Never raises: every failure mode (invalid URL, captions
disabled, video private/unavailable, network error) is reported back as a
plain string, the same Offline-Mode-safe pattern every other AI Center
failure follows -- a broken YouTube import must never crash SINDHU or block
any other module.
"""

import re

_VIDEO_ID_PATTERNS = [
    re.compile(r"(?:v=|/videos/|embed/|youtu\.be/|/v/|/shorts/)([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
]

_FILLER_WORDS_RE = re.compile(r"\b(um+|uh+|you know|i mean)\b[, ]*", re.IGNORECASE)
_BRACKET_TAG_RE = re.compile(r"\[[^\]]{1,30}\]")  # [Music], [Applause], [Laughter], ...
_MUSIC_NOTE_RE = re.compile(r"[♪♫♩-♯]+")  # bare music-note glyphs (no brackets), common in auto-captions


def transcript_api_available():
    """Whether youtube-transcript-api is installed -- lets the frontend hide/
    disable the YouTube import button instead of letting every attempt fail."""
    try:
        import youtube_transcript_api  # noqa: F401
        return True
    except ImportError:
        return False


def extract_video_id(url_or_id):
    """Accepts a full YouTube URL (watch/shorts/youtu.be/embed) or a bare
    11-character video id. Returns the id, or None if nothing recognizable
    was found."""
    text = (url_or_id or "").strip()
    if not text:
        return None
    for pattern in _VIDEO_ID_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def clean_transcript(raw_text):
    """Removes noise the AI Deep Understanding prompt shouldn't have to
    waste attention on: caption sound-effect tags, common filler words, and
    collapses whitespace left behind by stitching many short caption lines
    together."""
    text = _BRACKET_TAG_RE.sub("", raw_text or "")
    text = _MUSIC_NOTE_RE.sub("", text)
    text = _FILLER_WORDS_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_transcript(video_id):
    """Returns (cleaned_text_or_None, error_or_None). Never raises -- every
    failure (library missing, captions disabled, video unavailable, network
    error) is reported back as a plain string for the Import Report."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, "youtube-transcript-api is not installed on this server."

    try:
        try:
            # youtube-transcript-api >= 1.0: instance-based fetch().
            fetched = YouTubeTranscriptApi().fetch(video_id)
            segments = [snippet.text for snippet in fetched]
        except AttributeError:
            # youtube-transcript-api < 1.0: module-level classmethod.
            raw_segments = YouTubeTranscriptApi.get_transcript(video_id)
            segments = [seg["text"] for seg in raw_segments]
    except Exception as exc:  # pragma: no cover -- network/library errors, never crash
        return None, f"Could not fetch transcript for video '{video_id}': {exc}"

    joined = " ".join(segments).strip()
    if not joined:
        return None, "Transcript was empty."
    return clean_transcript(joined), None


def import_from_url(url):
    """Returns (cleaned_text_or_None, video_id_or_None, error_or_None) --
    the one function the importer calls for a YouTube input."""
    video_id = extract_video_id(url)
    if not video_id:
        return None, None, "Could not find a valid YouTube video ID in that URL."
    text, error = fetch_transcript(video_id)
    if error:
        return None, video_id, error
    return text, video_id, None
