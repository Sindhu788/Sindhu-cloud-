"""Raw-text extraction for uploaded documents. Imports of pypdf/python-docx
are deferred into each function so this module can always be imported even
if one of those optional packages isn't installed yet -- the AI Center's
paste-text workflow (and every other page) must never break because of it.
A missing package surfaces as a clear ImportError message from the specific
extractor function, not a crash at import time."""


def extract_text_from_pdf(file_bytes):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("PDF import requires the 'pypdf' package. Install it with: pip install pypdf")

    import io
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def extract_text_from_docx(file_bytes):
    try:
        import docx
    except ImportError:
        raise ImportError("DOCX import requires the 'python-docx' package. Install it with: pip install python-docx")

    import io
    document = docx.Document(io.BytesIO(file_bytes))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts).strip()


def extract_text(filename, file_bytes):
    """Dispatch by extension. YouTube transcripts and plain notes are
    expected to be pasted directly as text, not uploaded as files, so no
    .txt-specific handling is needed beyond decoding."""
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if lower.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    if lower.endswith(".txt") or lower.endswith(".md"):
        return file_bytes.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type for '{filename}'. Supported: .pdf, .docx, .txt, .md")
