"""Ingest MediaCrawler's Xiaohongshu jsonl output (no network calls here).

Run update_xhs.bat to refresh vendor/MediaCrawler/data/xhs/jsonl/*;
this module normalizes whatever exists on disk into Records. Identity
is the note_id (note URLs carry rotating xsec_token parameters).
"""
from __future__ import annotations

import json
import time as _time
from datetime import date, datetime
from pathlib import Path

from ..config import ROOT
from ..dates import extract_dates
from ..models import Record, classify, clean_text

XHS_DATA_DIR = ROOT / "vendor" / "MediaCrawler" / "data" / "xhs" / "jsonl"
MAX_FILE_AGE_DAYS = 30   # ignore jsonl files older than this
MAX_NOTE_AGE_DAYS = 21   # ignore notes published earlier than this


def scrape(today: date) -> list[Record]:
    if not XHS_DATA_DIR.exists():
        return []
    notes: dict = {}
    cutoff = _time.time() - MAX_FILE_AGE_DAYS * 86400
    for f in sorted(XHS_DATA_DIR.glob("search_contents_*.jsonl")):
        if f.stat().st_mtime < cutoff:
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                n = json.loads(line)
            except json.JSONDecodeError:
                continue
            if n.get("note_id"):
                notes[n["note_id"]] = n  # later crawls win

    records = []
    for nid, n in notes.items():
        title = clean_text(n.get("title") or n.get("desc") or "", 200)
        if not title:
            continue
        desc = clean_text(n.get("desc") or "")
        published = None
        if n.get("time"):
            try:
                published = datetime.fromtimestamp(int(n["time"]) / 1000).isoformat()
            except (ValueError, OSError, TypeError):
                pass
        # time-desc search still surfaces old hot notes; keep the radar fresh
        if published and (today - date.fromisoformat(published[:10])).days > MAX_NOTE_AGE_DAYS:
            continue
        ds, de = extract_dates(f"{title} {desc}", today)
        extra = json.dumps({
            "likes": str(n.get("liked_count") or ""),
            "kw": n.get("source_keyword") or "",
            "loc": n.get("ip_location") or "",
        }, ensure_ascii=False)
        records.append(Record(
            source="xiaohongshu", source_name="小红书", kind="xhs",
            category=classify(title, desc, "", "other"),
            title=title,
            url=n.get("note_url") or f"https://www.xiaohongshu.com/explore/{nid}",
            summary=desc, date_start=ds, date_end=de, published=published,
            image=n.get("image_list") if isinstance(n.get("image_list"), str) else None,
            rid=f"xhs|{nid}", extra=extra))
    return records
