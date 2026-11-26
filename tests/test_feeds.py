"""Feeds: parsing, the print_feed action, setup, the morning slip and voice."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.coordinator import render_job
from custom_components.tiny_press.fetch import FeedConfig, find_feed
from custom_components.tiny_press.generators.feeds import (
    WIKIQUOTE_API_URL,
    WIKIQUOTE_URL,
    FeedError,
    FeedItem,
    html_to_text,
    parse_feed,
    shorten,
    wikiquote_api_html,
    wikiquote_quote,
)
from custom_components.tiny_press.jobs import feed_job, qr_mm
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

FEED_URL = "https://news.example.com/rss"
RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Example News</title>
  <link>https://news.example.com/</link>
  <item>
    <title>Library opens a &amp; new reading room</title>
    <link>https://news.example.com/a/1</link>
    <pubDate>Thu, 26 Nov 2026 13:05:00 GMT</pubDate>
    <description><![CDATA[<p>The <b>new room</b> has <a href="x">big windows</a>.</p>
      <script>alert(1)</script><img src="x.jpg">]]></description>
  </item>
  <item>
    <title>Second story</title>
    <link>javascript:alert(1)</link>
    <description>Plain text summary.</description>
  </item>
  <item><title></title><description></description></item>
</channel>
</rss>"""
ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title type="html">Example &lt;b&gt;Blog&lt;/b&gt;</title>
  <link rel="self" href="https://blog.example.com/feed"/>
  <link href="https://blog.example.com/"/>
  <entry>
    <title>Hello Atom</title>
    <link rel="alternate" href="https://blog.example.com/hello"/>
    <updated>2026-11-25T08:00:00Z</updated>
    <summary>First post.</summary>
  </entry>
</feed>"""
RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel><title>RDF Feed</title><link>https://rdf.example.com/</link></channel>
  <item><title>RDF item</title><link>https://rdf.example.com/1</link>
    <dc:date>2026-11-24T10:00:00+00:00</dc:date></item>
</rdf:RDF>"""
# Same structure as Wikiquote's "Quote of the day" box (quote text here is
# Abraham Lincoln's, public domain).
WIKIQUOTE = """<div><table><tr><td><img src="x.jpg"></td><td>
<table class="cquote"><tr><td>“</td>
<td>Whatever you are, be a <a href="/wiki/Good">good</a> one .</td>
<td>”</td></tr><tr><td colspan="3"><p><cite style="x">—<a href="/wiki/Abraham_Lincoln">Abraham Lincoln</a></cite></p></td></tr>
</table></td></tr></table><small><style>.x{}</style>There is a page for each month</small></div>"""


def test_parse_rss() -> None:
    feed = parse_feed(RSS)
    assert feed.title == "Example News" and feed.link == "https://news.example.com/"
    assert len(feed.items) == 2  # the empty item is dropped
    first, second = feed.items
    assert first.title == "Library opens a & new reading room"
    assert first.summary == "The new room has big windows."
    assert first.published == datetime(2026, 11, 26, 13, 5, tzinfo=UTC)
    assert second.link is None  # only http(s) links are kept
    assert parse_feed(RSS, limit=1).items == (first,)


def test_parse_sorts_newest_first() -> None:
    def item(title: str, when: str | None) -> str:
        date_tag = f"<pubDate>{when}</pubDate>" if when else ""
        return f"<item><title>{title}</title>{date_tag}</item>"

    data = (
        "<rss><channel><title>T</title>"
        + item("old", "Mon, 23 Nov 2026 21:46:34 +0000")
        + item("undated", None)
        + item("newest", "Thu, 26 Nov 2026 12:08:50 +0000")
        + item("middle", "Thu, 26 Nov 2026 10:04:12 +0000")
        + "</channel></rss>"
    ).encode()
    titles = [i.title for i in parse_feed(data).items]
    assert titles == ["newest", "middle", "old", "undated"]
    assert [i.title for i in parse_feed(data, limit=2).items] == ["newest", "middle"]


def test_parse_atom_and_rdf() -> None:
    atom = parse_feed(ATOM)
    assert atom.title == "Example Blog" and atom.link == "https://blog.example.com/"
    assert atom.items[0].link == "https://blog.example.com/hello"
    assert atom.items[0].published == datetime(2026, 11, 25, 8, 0, tzinfo=UTC)
    rdf = parse_feed(RDF)
    assert rdf.title == "RDF Feed" and rdf.items[0].title == "RDF item"
    assert rdf.items[0].published is not None


@pytest.mark.parametrize(
    "data",
    [
        b"not xml",
        b"<html><body>hi</body></html>",
        b"<rss></rss>",
        b'<!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel/></rss>',
    ],
)
def test_parse_rejects(data: bytes) -> None:
    with pytest.raises(FeedError):
        parse_feed(data)


def test_text_helpers() -> None:
    assert html_to_text("<p>a</p><style>x</style><p>b &amp; c</p>") == "a b & c"
    assert html_to_text(None) == ""
    assert shorten("one two three four", 12) == "one two…"
    assert shorten("short", 12) == "short"


def test_wikiquote_quote() -> None:
    assert wikiquote_quote(WIKIQUOTE.encode()) == (
        "Whatever you are, be a good one.",
        "Abraham Lincoln",
    )
    assert wikiquote_quote(b"<p>no box</p>") is None
    no_author = WIKIQUOTE.replace("<cite", "<span").replace("</cite>", "</span>")
    assert wikiquote_quote(no_author.encode()) is None
    long = WIKIQUOTE.replace("Whatever", "word " * 120)
    assert wikiquote_quote(long.encode()) is None


def test_wikiquote_api_html() -> None:
    v2 = json.dumps({"parse": {"text": WIKIQUOTE}}).encode()
    v1 = json.dumps({"parse": {"text": {"*": WIKIQUOTE}}}).encode()
    assert wikiquote_api_html(v2) == wikiquote_api_html(v1) == WIKIQUOTE.encode()
    assert wikiquote_api_html(b'{"error": {"code": "missingtitle"}}') is None
    assert wikiquote_api_html(b"<html>") is None


async def test_live_quote_falls_back_to_page(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(WIKIQUOTE_API_URL, json={"error": {"code": "ratelimited"}})
    aioclient_mock.get(WIKIQUOTE_URL, text=WIKIQUOTE)
    await _setup(hass, config_entry, morning_bottom="quote")
    await _call(hass, "print_morning_slip")
    assert aioclient_mock.call_count == 2
    store = config_entry.runtime_data.store
    assert store.get_setting("live_quote_cache")["text"] == (
        "Whatever you are, be a good one."
    )


def test_find_feed() -> None:
    feeds = [FeedConfig("bbc", "BBC News", "u"), FeedConfig("blog", "My Blog", "v")]
    assert find_feed(feeds, None) == feeds[0]
    assert find_feed(feeds, "my blog") == feeds[1]
    assert find_feed(feeds, "bbc") == feeds[0]
    assert find_feed(feeds, "the bbc news") == feeds[0]
    assert find_feed(feeds, "weather") is None
    assert find_feed([], None) is None


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_feed_layout(width: int) -> None:
    items = (
        FeedItem(
            "A headline " * 6, "https://x.example/1", datetime.now(UTC), "Sum " * 40
        ),
        FeedItem("No link", None, None, ""),
    )
    footer = layout.Footer("Feed", "AAAA", date(2026, 11, 26), show_id=False)
    parts = layout.feed_parts(
        width,
        "News",
        items,
        footer,
        to_local=lambda d: d,
        printed_at=datetime.now(UTC),
        qr=True,
    )
    assert [link for _c, link in parts] == ["https://x.example/1", None]
    for canvas, _link in parts:
        assert canvas.render()[0].width == width
    empty = layout.feed_parts(
        width, "News", (), footer, to_local=lambda d: d, printed_at=datetime.now(UTC)
    )
    assert len(empty) == 1
    assert 10 < qr_mm("https://x.example/1") < qr_mm("https://x.example/" + "a" * 200)
    job = feed_job("News", parse_feed(RSS), 5)
    assert job.sections is None and job.build(width).render()[0].width == width
    qr_job = feed_job("News", parse_feed(RSS), 5, qr=True)
    parts, height, extra_mm, truncated = render_job(qr_job, width, 100_000)
    natives = b"".join(extra for _image, extra in parts)
    assert natives.count(b"1P0https://news.example.com/a/1") == 1  # one QR
    assert extra_mm == qr_mm("https://news.example.com/a/1") and not truncated
    assert height > 0
    # Short on paper: stops before the QR and says it was cut.
    parts, _h, extra_mm, truncated = render_job(qr_job, width, 300)
    assert truncated and extra_mm == 0


FEEDS = [
    {"id": "news", "name": "Example News", "url": FEED_URL, "items": 5},
    {"id": "blog", "name": "Example Blog", "url": "https://blog.example.com/feed"},
]


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, service: str, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


async def test_print_feed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(FEED_URL, content=RSS)
    aioclient_mock.get("https://blog.example.com/feed", content=ATOM)
    await _setup(hass, config_entry, feeds=FEEDS)

    res = await _call(hass, "print_feed")
    assert res["type"] == "feed" and res["feed"] == "Example News"
    assert res["items"] == 2 and res["headlines"][1] == "Second story"
    with_qr = await _call(hass, "print_feed", feed="news", items=1, qr=True)
    assert with_qr["items"] == 1 and with_qr["length_mm"] > res["length_mm"] / 3

    blog = await _call(hass, "print_feed", feed="example blog")
    assert blog["feed"] == "Example Blog" and blog["headlines"] == ["Hello Atom"]
    via_print = await _call(hass, "print", type="feed")
    assert via_print["feed"] == "Example News"
    preview = await _call(hass, "preview", type="feed")
    assert preview["image"].startswith("data:image/png;base64,")

    with pytest.raises(ServiceValidationError, match="no feed called"):
        await _call(hass, "print_feed", feed="sports")
    with pytest.raises(ServiceValidationError, match="print_history"):
        await _call(hass, "print", type="history")


async def test_print_feed_problems(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="No feeds"):
        await _call(hass, "print_feed")
    hass.config_entries.async_update_entry(config_entry, options={"feeds": FEEDS})
    await hass.async_block_till_done()
    aioclient_mock.get(FEED_URL, status=404)
    with pytest.raises(
        HomeAssistantError, match="Couldn't read Example News: HTTP 404"
    ):
        await _call(hass, "print_feed")
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, content=b"<html>nope</html>")
    with pytest.raises(HomeAssistantError, match="not an RSS or Atom feed"):
        await _call(hass, "print_feed")
    voice = await _call(hass, "voice_print", type="feed")
    assert voice["printed"] is False and "Couldn't read Example News" in voice["speech"]


async def test_feed_options(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(FEED_URL, content=RSS)
    aioclient_mock.get("https://bad.example.com/rss", status=500)

    async def add(**data: Any):
        result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "add_feed"}
        )
        return await hass.config_entries.options.async_configure(
            result["flow_id"], {"items": 5, **data}
        )

    result = await add(name="News", url="ftp://x")
    assert result["errors"] == {"url": "invalid_url"}
    result = await add(name="News", url="https://bad.example.com/rss")
    assert result["errors"] == {"url": "cannot_read_feed"}
    result = await add(name="News", url=FEED_URL, items=3)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert loaded_entry.options["feeds"] == [
        {
            "id": "news",
            "name": "News",
            "url": FEED_URL,
            "items": 3,
            "auto_print": False,  # off by default
            "check_minutes": 15,
            "quiet_start": "21:00",
            "quiet_end": "07:00",
            "quiet_mode": "skip",
            "auto_qr": False,
        }
    ]
    result = await add(name="news", url=FEED_URL)
    assert result["errors"] == {"name": "feed_exists"}

    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, "morning_feed": "news"}
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    assert "remove_feed" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_feed"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"feeds": ["news"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert loaded_entry.options["feeds"] == []
    assert loaded_entry.options["morning_feed"] is None


async def test_morning_live_quote_and_headlines(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(
        WIKIQUOTE_API_URL, json={"parse": {"title": "x", "text": WIKIQUOTE}}
    )
    aioclient_mock.get(FEED_URL, content=RSS)
    await _setup(hass, config_entry, morning_bottom="quote", feeds=FEEDS)
    store = config_entry.runtime_data.store
    await _call(hass, "print_morning_slip")
    await _call(hass, "print_morning_slip")
    assert aioclient_mock.call_count == 1  # cached for the day
    assert store.get_setting("live_quote_cache")["author"] == "Abraham Lincoln"
    assert store.recent("quote") == []  # no bundled quote used

    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            "morning_bottom": "feed",
            "morning_feed": "news",
        },
    )
    await hass.async_block_till_done()
    await _call(hass, "print_morning_slip")
    assert aioclient_mock.call_count == 2


async def test_morning_fallbacks(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(FEED_URL, status=500)
    await _setup(
        hass, config_entry, morning_bottom="feed", feeds=FEEDS, live_quote=False
    )
    store = config_entry.runtime_data.store
    await _call(hass, "print_morning_slip")  # feed fails: a bundled quote instead
    assert len(store.recent("quote")) == 1
    hass.config_entries.async_update_entry(
        config_entry, options={"morning_bottom": "feed", "live_quote": False}
    )
    await hass.async_block_till_done()
    await _call(hass, "print_morning_slip")  # no feeds at all: quote again
    assert len(store.recent("quote")) == 2


async def test_voice_and_llm_feed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    from homeassistant.core import Context
    from homeassistant.helpers import llm as llm_helper
    from homeassistant.setup import async_setup_component

    aioclient_mock.get(FEED_URL, content=RSS)
    aioclient_mock.get("https://blog.example.com/feed", content=ATOM)
    await _setup(hass, config_entry, feeds=FEEDS)
    res = await _call(hass, "voice_print", type="feed", feed="blog")
    assert res["speech"] == "Printing 1 headline from Example Blog."
    res = await _call(hass, "voice_print", type="feed")
    assert res["speech"] == "Printing 2 headlines from Example News."
    missing = await _call(hass, "voice_print", type="feed", feed="sports")
    assert missing == {"printed": False, "speech": "There's no feed called sports"}

    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "llm", {})
    context = llm_helper.LLMContext("test", Context(), "en", "conversation", None)
    api = await llm_helper.async_get_api(hass, llm_helper.LLM_API_ASSIST, context)
    tool = next(t for t in api.tools if t.name == "tiny_press__print")
    assert tool.parameters({"type": "feed", "feed": "Example Blog"})
    result = await api.async_call_tool(
        llm_helper.ToolInput(
            "tiny_press__print", {"type": "feed", "feed": "Example Blog"}
        )
    )
    assert result.data["printed"] is True and result.data["feed"] == "Example Blog"
