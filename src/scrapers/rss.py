"""Generic WordPress RSS scraper — one parser covers all feed sources.

WordPress feeds support ?paged=N, which lets the first run bootstrap
several days of history in one go.
"""
from __future__ import annotations

import re

import feedparser
from dateutil import parser as dateparser

from ..dates import extract_dates
from ..fetchutil import fetch
from ..models import Record, classify, clean_text

IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def scrape(source: dict, today, pages: int = 2) -> list[Record]:
    records, seen = [], set()
    for p in range(1, pages + 1):
        url = source["url"] if p == 1 else f"{source['url']}?paged={p}"
        try:
            resp = fetch(url)
        except Exception:
            if p == 1:
                raise
            break  # deeper pages are best-effort
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            break
        for e in feed.entries:
            link = getattr(e, "link", None)
            title = clean_text(getattr(e, "title", ""), 200)
            if not link or not title or link in seen:
                continue
            seen.add(link)
            raw_desc = getattr(e, "description", "") or getattr(e, "summary", "")
            summary = clean_text(raw_desc)
            published = None
            if getattr(e, "published", None):
                try:
                    published = dateparser.parse(e.published).isoformat()
                except (ValueError, TypeError):
                    pass
            img = IMG_RE.search(raw_desc or "")
            ds, de = extract_dates(f"{title} {summary}", today)
            if source["kind"] == "deal" and ds and not de:
                de = ds  # "on 12 Jul" style one-day promos end that same day
            records.append(Record(
                source=source["key"], source_name=source["name"],
                kind=source["kind"],
                category=classify(title, summary, link, source["default_category"]),
                title=title, url=link, summary=summary,
                date_start=ds, date_end=de, published=published,
                image=img.group(1) if img else None))
    return records
