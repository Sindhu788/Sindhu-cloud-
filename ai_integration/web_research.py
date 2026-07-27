"""Autonomous Strategy Research (External Knowledge Acquisition Group,
items 9+10): ON-DEMAND ONLY -- there is no scheduled/background trigger
anywhere in this module, it only runs when a person calls research_and_queue()
via the dashboard. Searches the web for trading-strategy content, restricted
to a small allow-list of established, reputable sources (Source Quality
Filter, item 10), then feeds every trusted result through
ai_integration.import_queue.enqueue() -- the EXACT SAME entry point manually
pasted text uses. No special trust: every strategy sourced this way lands in
the same NEEDS_REVIEW/READY queue and must clear the same
backtest -> validate -> Walk-Forward pipeline as anything else. Nothing here
auto-approves or auto-deploys a strategy.

Search implementation note: uses DuckDuckGo's key-less HTML endpoint rather
than a paid search API (Google/Bing Custom Search etc.), since no API key
was available to configure. This is a reasonable, working v1 -- but it's a
screen-scrape of a page DuckDuckGo could restructure at any time, not a
stable contracted API. If a paid search API key becomes available, swapping
search_web()'s implementation is a self-contained, one-function change --
everything downstream (the trust filter, the fetch/extract, the queueing)
is already decoupled from how results were found.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urlparse, parse_qs, unquote

import requests

from ai_integration.import_queue import enqueue

# Source Quality Filter (item 10): a small, deliberately conservative
# allow-list of well-established trading/finance education sources.
# Anything not in this list is rejected before it's ever fetched. Expand
# this list deliberately (a person editing this file), never silently.
TRUSTED_DOMAINS = {
    "babypips.com",
    "investopedia.com",
    "tradingview.com",
    "binance.com",       # covers academy.binance.com and www.binance.com
    "cmegroup.com",
}

_REQUEST_TIMEOUT = 15
_USER_AGENT = "SINDHU-Research/1.0 (personal trading-strategy research assistant)"
_MIN_ARTICLE_CHARS = 200


def _domain_of(url):
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def is_trusted_source(url):
    """True only if the URL's domain is exactly one of TRUSTED_DOMAINS, or a
    subdomain of one (e.g. academy.binance.com matches binance.com)."""
    domain = _domain_of(url)
    if not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in TRUSTED_DOMAINS)


class _TextExtractor(HTMLParser):
    """Minimal, dependency-free HTML-to-text: drops <script>/<style>
    content and tags, keeps everything else as plain text. Good enough for
    feeding an article into the AI extraction pipeline, which already has
    to tolerate messy real-world document text (PDFs, DOCX)."""

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped)

    def get_text(self):
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self._chunks))


def _resolve_ddg_redirect(href):
    """DuckDuckGo's HTML results wrap outbound links in a /l/?uddg=<encoded>
    redirect -- unwrap it so we fetch/store the real article URL, not a DDG
    tracking link."""
    if "duckduckgo.com/l/" in href or href.startswith("/l/?"):
        query = parse_qs(urlparse(href).query)
        real = query.get("uddg", [None])[0]
        if real:
            return unquote(real)
    return href


def search_web(query, max_results=15):
    """Key-less DuckDuckGo HTML search -- see module docstring for why.
    Never raises on a malformed/changed page; returns [] instead so a
    scrape breakage degrades to "no results" rather than a 500."""
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    results = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        resp.text, re.S,
    ):
        href = m.group(1).replace("&amp;", "&")
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        url = _resolve_ddg_redirect(href)
        if url and title:
            results.append({"url": url, "title": title})
        if len(results) >= max_results:
            break
    return results


def fetch_article_text(url):
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    extractor = _TextExtractor()
    extractor.feed(resp.text)
    return extractor.get_text()


def queue_from_url(url, title=None):
    """Direct single-URL path: given a specific article URL (e.g. a person
    pasting a link they found themselves), still enforces the Source
    Quality Filter, fetches + extracts it, and queues it through the
    standard import pipeline -- same treatment as search_web()'s results,
    just skipping the (currently unreliable, see module docstring) search
    step. Returns {"queued": {...}} or {"skipped": {...}}, never raises."""
    if not is_trusted_source(url):
        return {"skipped": {"url": url, "title": title, "reason": "source not in the trusted allow-list"}}
    try:
        text = fetch_article_text(url)
    except Exception as e:
        return {"skipped": {"url": url, "title": title, "reason": f"could not fetch the page: {e!r}"}}
    if len(text.strip()) < _MIN_ARTICLE_CHARS:
        return {"skipped": {"url": url, "title": title, "reason": "page had too little readable text to be a real article"}}
    item_id = enqueue(text, title=title or url, source_hint=url, use_ai=True, input_kind="text")
    return {"queued": {"url": url, "title": title, "queue_id": item_id}}


def research_and_queue(query, max_results=5):
    """The one entry point the dashboard calls (explicit trigger only).
    Searches, filters by the trusted-source allow-list, fetches + extracts
    text for every trusted result, and queues each through the standard
    import pipeline -- identical treatment to a manually pasted strategy.
    Returns what was queued and what was skipped (with a plain-language
    reason for each skip), so nothing happens silently."""
    raw_results = search_web(query, max_results=max_results * 4)  # over-fetch: many will be filtered/fail
    queued, skipped = [], []

    for r in raw_results:
        if len(queued) >= max_results:
            break
        if not is_trusted_source(r["url"]):
            skipped.append({"url": r["url"], "title": r["title"], "reason": "source not in the trusted allow-list"})
            continue
        try:
            text = fetch_article_text(r["url"])
        except Exception as e:
            skipped.append({"url": r["url"], "title": r["title"], "reason": f"could not fetch the page: {e!r}"})
            continue
        if len(text.strip()) < _MIN_ARTICLE_CHARS:
            skipped.append({"url": r["url"], "title": r["title"], "reason": "page had too little readable text to be a real article"})
            continue

        item_id = enqueue(text, title=r["title"], source_hint=r["url"], use_ai=True, input_kind="text")
        queued.append({"url": r["url"], "title": r["title"], "queue_id": item_id})

    return {"query": query, "queued": queued, "skipped": skipped}
