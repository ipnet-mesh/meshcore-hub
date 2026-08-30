"""RSS 2.0 / Atom feed builders for public mesh data.

Stdlib ``xml.etree.ElementTree`` only — zero new dependencies (the same
precedent as the hand-rolled sitemap in the web tier). All user-controlled
text (message payloads, node names, channel names) flows through ElementTree
serialisation, which escapes ``&``, ``<``, and ``>`` — plus a control-character
scrub for bytes XML 1.0 forbids outright — so mesh text can never inject
markup into a feed document.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

# XML 1.0 forbids most C0 control characters (and DEL) anywhere in a
# document; ElementTree would happily emit them, so scrub first.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(text: Optional[str]) -> str:
    """Scrub characters XML 1.0 cannot represent; None becomes empty."""
    if not text:
        return ""
    return _XML_ILLEGAL.sub("", text)


def _as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC (DB columns are timestamptz/UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class FeedItem:
    """One feed entry, shared by the RSS and Atom builders."""

    title: str
    description: str
    guid: str
    link: str
    pub_date: datetime
    guid_is_permalink: bool = False


@dataclass
class FeedMeta:
    """Feed-level metadata."""

    title: str
    link: str
    description: str
    # Absolute URL of the feed document itself (rel="self"); optional.
    feed_url: Optional[str] = None


def _serialize(root: Element) -> str:
    """Serialize with an explicit UTF-8 declaration."""
    body = tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def _newest_date(items: List[FeedItem]) -> datetime:
    """Newest item date, or feed build time when the feed is empty."""
    if not items:
        return datetime.now(timezone.utc)
    return max(_as_utc(item.pub_date) for item in items)


def build_rss(meta: FeedMeta, items: List[FeedItem]) -> str:
    """Build an RSS 2.0 document (RFC 822 dates)."""
    root = Element(
        "rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"}
    )
    channel = SubElement(root, "channel")
    SubElement(channel, "title").text = _clean(meta.title)
    SubElement(channel, "link").text = meta.link
    SubElement(channel, "description").text = _clean(meta.description)
    SubElement(channel, "lastBuildDate").text = format_datetime(_newest_date(items))
    SubElement(channel, "generator").text = "MeshCore Hub"
    if meta.feed_url:
        SubElement(
            channel,
            "atom:link",
            {"href": meta.feed_url, "rel": "self", "type": "application/rss+xml"},
        )

    for item in items:
        pub_date = _as_utc(item.pub_date)
        entry = SubElement(channel, "item")
        SubElement(entry, "title").text = _clean(item.title)
        SubElement(entry, "link").text = item.link
        SubElement(entry, "description").text = _clean(item.description)
        guid = SubElement(
            entry,
            "guid",
            {"isPermaLink": "true" if item.guid_is_permalink else "false"},
        )
        guid.text = item.guid
        SubElement(entry, "pubDate").text = format_datetime(pub_date)

    return _serialize(root)


def build_atom(meta: FeedMeta, items: List[FeedItem]) -> str:
    """Build an Atom document (RFC 3339 dates)."""
    root = Element("feed", {"xmlns": "http://www.w3.org/2005/Atom"})
    SubElement(root, "title").text = _clean(meta.title)
    SubElement(root, "link", {"rel": "alternate", "href": meta.link})
    if meta.feed_url:
        SubElement(
            root,
            "link",
            {"href": meta.feed_url, "rel": "self", "type": "application/atom+xml"},
        )
    # The feed's canonical URL is the most stable identifier available.
    SubElement(root, "id").text = meta.link
    SubElement(root, "updated").text = _newest_date(items).isoformat()
    SubElement(root, "generator").text = "MeshCore Hub"

    for item in items:
        pub_date = _as_utc(item.pub_date)
        entry = SubElement(root, "entry")
        SubElement(entry, "title").text = _clean(item.title)
        SubElement(entry, "link", {"rel": "alternate", "href": item.link})
        SubElement(entry, "id").text = item.guid
        SubElement(entry, "updated").text = pub_date.isoformat()
        SubElement(entry, "published").text = pub_date.isoformat()
        SubElement(entry, "summary").text = _clean(item.description)

    return _serialize(root)
