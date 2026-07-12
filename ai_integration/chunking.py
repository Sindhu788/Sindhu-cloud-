"""Splits oversized documents into AI-cleanable pieces before they reach a
provider, and merges the cleaned pieces back into one document afterward.
Real context-window limits vary by provider/model and aren't tracked here;
instead this uses one conservative, fixed chunk size that comfortably fits
every supported provider, so chunking behavior never depends on which
provider happens to be active. Token count is a standard chars/4 estimate,
not a real tokenizer -- exactness isn't the point, staying safely under
every provider's limit is."""

_CHARS_PER_TOKEN = 4
_MAX_CHUNK_TOKENS = 6000
_MAX_CHUNK_CHARS = _MAX_CHUNK_TOKENS * _CHARS_PER_TOKEN
_OVERLAP_CHARS = 400


def estimate_tokens(text):
    return max(1, len(text or "") // _CHARS_PER_TOKEN)


def needs_chunking(text):
    return len(text or "") > _MAX_CHUNK_CHARS


def split_into_chunks(text):
    """Splits on paragraph boundaries where possible, staying under
    _MAX_CHUNK_CHARS per chunk, carrying a small trailing overlap into the
    next chunk so a rule split across a paragraph break isn't silently
    lost when chunks are cleaned independently."""
    if not needs_chunking(text):
        return [text]

    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > _MAX_CHUNK_CHARS and current:
            chunks.append(current)
            current = current[-_OVERLAP_CHARS:] + "\n\n" + para
        else:
            current = candidate
    if current:
        chunks.append(current)

    # A single paragraph longer than the whole chunk budget (e.g. one huge
    # transcript line with no blank-line breaks) -- hard-split as a fallback.
    final = []
    for c in chunks:
        if len(c) <= _MAX_CHUNK_CHARS:
            final.append(c)
        else:
            step = _MAX_CHUNK_CHARS - _OVERLAP_CHARS
            for i in range(0, len(c), step):
                final.append(c[i:i + _MAX_CHUNK_CHARS])
    return final


def merge_chunks(cleaned_chunks):
    """Cleaned chunks are already well-structured text; joining with a
    blank line keeps section boundaries readable for the downstream
    rule-based parser, which then extracts and saves ONE strategy/lesson
    from the merged whole -- never one per chunk."""
    return "\n\n".join(c.strip() for c in cleaned_chunks if c and c.strip())
