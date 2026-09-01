"""Image (screenshot) OCR for the External Signal Tracker.

HONESTLY NOT IMPLEMENTED in this environment. Verified during development:
- No local OCR engine (Tesseract) is installed, and no `pytesseract`
  package is available.
- The configured Groq API key has no working vision-capable model on this
  account (tested against several current vision model ids -- all
  returned 404 "does not exist or you do not have access to it").

Rather than ship an OCR path that was never actually proven to work, image
messages are still fully INGESTED (Phase 1: stored with content_type=
"image", the raw file kept, never lost) but marked unprocessed with a
clear reason instead of silently producing wrong or fabricated signal
data.

To make image signals work for real, one of the following is needed:
1. Install Tesseract OCR locally + `pip install pytesseract pillow`, and
   implement extract_text_from_image() below to call it, OR
2. Configure an AI provider/model on this account with real image
   (vision) support, and add an image-capable branch to
   external_signals/parser.py.

Once either exists, wiring it into the ingestion pipeline
(external_signals/ingest.py's `_process_image_message`) is a small,
localized change -- the storage/parsing split (Phase 1's own design) means
no already-ingested image is ever lost by adding this later.
"""

OCR_AVAILABLE = False


def extract_text_from_image(file_bytes):
    """Always returns (None, reason) in this environment -- see module
    docstring. Kept as a real function (not just a missing import) so the
    ingestion pipeline has one stable call site to update once a working
    OCR/vision path is configured."""
    return None, "Image OCR is not available in this environment (no OCR engine or vision-capable AI model configured)."
