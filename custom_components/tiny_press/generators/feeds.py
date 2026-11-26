"""RSS and Atom feeds: parse, clean to plain text, and pick Wikiquote's quote.

Pure: ``fetch.py`` downloads the bytes. Only titles, links, dates and text
summaries are kept; images, scripts and markup are dropped.

Parsing uses the standard library's expat parser, which never fetches
external entities and (with expat 2.4.1 or newer) limits entity expansion.
Documents that declare entities are refused anyway, and the download is
size-capped before it gets here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import html
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET

MAX_ITEMS = 10
DEFAULT_ITEMS = 5
SUMMARY_CHARS = 240

ATOM = "{http://www.w3.org/2005/Atom}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


class FeedError(ValueError):
    """The bytes aren't an RSS or Atom feed Tiny Press can read."""


@dataclass(frozen=True, slots=True)
class FeedItem:
    """One headline."""

    title: str
    link: str | None = None
    published: datetime | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class Feed:
    """A parsed feed."""

    title: str
    link: str | None
    items: tuple[FeedItem, ...]


class _Text(HTMLParser):
    """Collect visible text, with breaks for block elements."""

    BLOCKS = frozenset({"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "td"})
    SKIP = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str | None, *, keep_lines: bool = False) -> str:
    """Plain text from an HTML (or plain) string, whitespace collapsed."""
    if not value:
        return ""
    parser = _Text()
    parser.feed(value)
    parser.close()
    text = html.unescape("".join(parser.parts))
    lines = [" ".join(line.split()) for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines) if keep_lines else " ".join(lines)


def shorten(text: str, limit: int = SUMMARY_CHARS) -> str:
    """Cut at a word boundary with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-–— ")
    return f"{cut}…"


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)  # RSS: RFC 822
    except TypeError, ValueError, IndexError:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))  # Atom
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _find_text(element: ET.Element, *names: str) -> str | None:
    for name in names:
        found = element.find(name)
        if found is not None and (found.text or "").strip():
            return found.text
    return None


def _atom_link(element: ET.Element) -> str | None:
    best = None
    for link in element.findall(f"{ATOM}link"):
        href = link.get("href")
        if href and link.get("rel", "alternate") == "alternate":
            return href
        best = best or href
    return best


def _safe_link(value: str | None) -> str | None:
    value = (value or "").strip()
    return value if value.startswith(("https://", "http://")) else None


def parse_feed(data: bytes, limit: int = MAX_ITEMS) -> Feed:
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom bytes."""
    if b"<!ENTITY" in data[:4096].upper():
        raise FeedError("feeds that declare XML entities aren't supported")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as err:
        raise FeedError(f"not valid XML: {err}") from err

    items: list[FeedItem] = []
    if root.tag == f"{ATOM}feed":
        title = html_to_text(_find_text(root, f"{ATOM}title")) or "Feed"
        link = _safe_link(_atom_link(root))
        for entry in root.findall(f"{ATOM}entry"):
            summary = _find_text(entry, f"{ATOM}summary", f"{ATOM}content")
            items.append(
                FeedItem(
                    html_to_text(_find_text(entry, f"{ATOM}title")),
                    _safe_link(_atom_link(entry)),
                    _date(_find_text(entry, f"{ATOM}published", f"{ATOM}updated")),
                    shorten(html_to_text(summary)),
                )
            )
    elif root.tag in ("rss", f"{RDF}RDF"):
        rdf = root.tag != "rss"
        channel = root.find(f"{RSS1}channel" if rdf else "channel")
        if channel is None:
            raise FeedError("RSS without a channel")
        ns = RSS1 if rdf else ""
        title = html_to_text(_find_text(channel, f"{ns}title")) or "Feed"
        link = _safe_link(_find_text(channel, f"{ns}link"))
        for item in (root if rdf else channel).findall(f"{ns}item"):
            summary = _find_text(item, f"{ns}description", f"{CONTENT}encoded")
            items.append(
                FeedItem(
                    html_to_text(_find_text(item, f"{ns}title")),
                    _safe_link(_find_text(item, f"{ns}link", "guid")),
                    _date(_find_text(item, "pubDate", f"{DC}date")),
                    shorten(html_to_text(summary)),
                )
            )
    else:
        raise FeedError("not an RSS or Atom feed")
    items = [item for item in items if item.title or item.summary]
    return Feed(title, link, tuple(items[:limit]))


WIKIQUOTE_URL = (
    "https://en.wikiquote.org/w/index.php"
    "?title=Main_Page/Quote_of_the_day&action=render"
)
WIKIQUOTE_CREDIT = "Wikiquote (CC BY-SA 4.0)"


class _QuoteBox(HTMLParser):
    """Read Wikiquote's quote box: the first ``table.cquote`` and its <cite>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0  # nesting inside the cquote table
        self.in_cite = False
        self.quote: list[str] = []
        self.author: list[str] = []
        self.done = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self.done:
            return
        if tag == "table":
            classes = (dict(attrs).get("class") or "").split()
            if self.depth or "cquote" in classes:
                self.depth += 1
        elif tag == "cite" and self.depth:
            self.in_cite = True
        elif tag in ("style", "script") and self.depth:
            self.depth += 1000  # skip their text

    def handle_endtag(self, tag: str) -> None:
        if self.done or not self.depth:
            return
        if tag in ("style", "script"):
            self.depth -= 1000
        elif tag == "cite":
            self.in_cite = False
        elif tag == "table":
            self.depth -= 1
            self.done = self.depth == 0

    def handle_data(self, data: str) -> None:
        if self.depth and self.depth < 1000:
            (self.author if self.in_cite else self.quote).append(data)


def wikiquote_quote(data: bytes) -> tuple[str, str] | None:
    """Read the quote and author from Wikiquote's "Quote of the day" page.

    Returns None when the page doesn't hold a short quote with an author, so
    the caller falls back to the bundled quotes.
    """
    box = _QuoteBox()
    box.feed(data.decode("utf-8", "replace"))
    box.close()
    quote = " ".join(html.unescape("".join(box.quote)).split()).strip(' "“”')
    author = " ".join(html.unescape("".join(box.author)).split()).strip(" —–-~")
    quote = re.sub(r"\s+([.,;:!?])", r"\1", quote)
    if not 10 <= len(quote) <= 500 or not author or len(author.split()) > 8:
        return None
    return quote, author
