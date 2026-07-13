"""Peatix search API — text-search 'singapore', then keep only events
whose timezone is Asia/Singapore (the country param is unreliable)."""
from __future__ import annotations

from datetime import timedelta

from dateutil import parser as dateparser

from ..config import PEATIX_SEARCH
from ..fetchutil import fetch
from ..models import FAMILY_WORDS, Record, clean_text

XHR = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}


def scrape(today, pages: int = 3) -> list[Record]:
    records, seen = [], set()
    for p in range(1, pages + 1):
        url = f"{PEATIX_SEARCH}?q=singapore&country=SG&p={p}&size=30"
        try:
            resp = fetch(url, headers=XHR)
            events = resp.json().get("json_data", {}).get("events", [])
        except Exception:
            if p == 1:
                raise
            break
        if not events:
            break
        for e in events:
            if e.get("timezone_id") != "Asia/Singapore":
                continue
            eid = e.get("id")
            name = clean_text(e.get("name", ""), 200)
            if not eid or not name or eid in seen:
                continue
            seen.add(eid)
            ds = de = None
            if e.get("datetime"):
                try:
                    d0 = dateparser.parse(e["datetime"]).date()
                    ds = d0.isoformat()
                    days = int(e.get("days") or 1)
                    de = (d0 + timedelta(days=max(0, days - 1))).isoformat()
                except (ValueError, TypeError):
                    pass
            venue = clean_text(e.get("venue_name") or e.get("address") or "", 80)
            lname = name.lower()
            cat = "family" if any(w in lname for w in FAMILY_WORDS) else "event"
            records.append(Record(
                source="peatix", source_name="Peatix", kind="event",
                category=cat, title=name,
                url=f"https://peatix.com/event/{eid}", venue=venue,
                date_start=ds, date_end=de, image=e.get("cover")))
    return records
