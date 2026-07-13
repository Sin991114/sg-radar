"""Eventbrite Singapore listing — parses the embedded schema.org JSON-LD."""
from __future__ import annotations

import json
import re

from ..config import EVENTBRITE_URL
from ..fetchutil import fetch
from ..models import FAMILY_WORDS, Record, clean_text

LD_RE = re.compile(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S)


def scrape(today, pages: int = 3) -> list[Record]:
    records, seen = [], set()
    for p in range(1, pages + 1):
        url = EVENTBRITE_URL if p == 1 else f"{EVENTBRITE_URL}?page={p}"
        try:
            resp = fetch(url)
        except Exception:
            if p == 1:
                raise
            break
        for block in LD_RE.findall(resp.text):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            for it in data.get("itemListElement") or []:
                ev = it.get("item") or {}
                if ev.get("@type") != "Event":
                    continue
                ev_url = ev.get("url")
                name = clean_text(ev.get("name", ""), 200)
                if not ev_url or not name or ev_url in seen:
                    continue
                seen.add(ev_url)
                loc = ev.get("location") or {}
                venue = clean_text(
                    loc.get("name")
                    or (loc.get("address") or {}).get("streetAddress") or "", 80)
                lname = name.lower()
                cat = "family" if any(w in lname for w in FAMILY_WORDS) else "event"
                records.append(Record(
                    source="eventbrite", source_name="Eventbrite", kind="event",
                    category=cat, title=name, url=ev_url, venue=venue,
                    date_start=ev.get("startDate"), date_end=ev.get("endDate"),
                    image=ev.get("image")))
    return records
