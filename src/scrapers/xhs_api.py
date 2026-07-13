"""Fetch Xiaohongshu notes via the TikHub REST API (paid, key required).

No login, no browser, no risk to your own account — TikHub runs the crawl
server-side and you pay per request (~$0.01). Output is identical to
scrapers/xhs.py (kind="xhs", rid="xhs|<note_id>"), so the site section and
dedup logic are unchanged whether notes come from TikHub or MediaCrawler.

TikHub's response field names aren't fully documented, so extraction is
defensive: it hunts the note list recursively and tries several field
aliases. If the first real run mislabels a field, tweak _note_fields().
"""
from __future__ import annotations

import json
import time as _time
from datetime import date, datetime

import requests

from ..config import (TIKHUB_BASE, TIKHUB_SEARCH_PATH, XHS_KEYWORDS,
                      XHS_PAGES_PER_KEYWORD)
from ..dates import extract_dates
from ..models import Record, classify, clean_text

MAX_NOTE_AGE_DAYS = 21
NOTE_HINT_KEYS = ("note_id", "note_card", "note", "display_title", "xsec_token")


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if v not in (None, "", [], {}):
            return v
    return None


def _find_note_list(obj, depth=0):
    """Recursively locate the first list of note-like dicts in the payload."""
    if depth > 7:
        return None
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and any(
                k in obj[0] for k in NOTE_HINT_KEYS + ("id",)):
            return obj
        for x in obj:
            found = _find_note_list(x, depth + 1)
            if found:
                return found
        return None
    if isinstance(obj, dict):
        for v in obj.values():
            found = _find_note_list(v, depth + 1)
            if found:
                return found
    return None


def _ts_to_iso(ts):
    if ts is None or ts == "":
        return None
    try:
        n = int(ts)
    except (ValueError, TypeError):
        s = str(ts)
        return s[:10] if s[:4].isdigit() else None
    if n > 1_000_000_000_000:   # milliseconds
        n //= 1000
    try:
        return datetime.fromtimestamp(n).isoformat()
    except (OSError, ValueError, OverflowError):
        return None


def _note_fields(item: dict):
    """Flatten one search-result item into note fields, alias-tolerant.

    TikHub nests the note under item["note"], with liked_count and a
    millisecond `timestamp` directly on it (no interact_info wrapper).
    Some notes carry last_update_time=0, so 0 is treated as "no value".
    """
    card = item.get("note") or item.get("note_card") or {}
    nid = _first(card, "note_id", "id") or _first(item, "note_id", "id")
    title = _first(card, "display_title", "title") or _first(item, "display_title", "title")
    desc = _first(card, "desc", "description") or _first(item, "desc", "description")
    inter = card.get("interact_info") or {}
    liked = (_first(card, "liked_count", "like_count")
             or _first(inter, "liked_count", "like_count")
             or _first(item, "liked_count", "likes"))
    ts = None
    for src in (card, item):
        if not isinstance(src, dict):
            continue
        for k in ("timestamp", "time", "create_time", "publish_time",
                  "update_time", "last_update_time"):
            v = src.get(k)
            if v not in (None, "", 0, "0"):
                ts = v
                break
        if ts:
            break
    xsec = _first(card, "xsec_token") or _first(item, "xsec_token")
    return nid, title, desc, liked, ts, xsec


def _cover_url(card: dict):
    """Pick the cover image URL (signed, time-limited; regenerated each crawl)."""
    imgs = card.get("images_list") or card.get("image_list") or []
    if not imgs:
        return None
    idx = card.get("cover_image_index")
    if not isinstance(idx, int) or not 0 <= idx < len(imgs):
        idx = 0
    img = imgs[idx] if isinstance(imgs[idx], dict) else {}
    return img.get("url") or img.get("url_size_large") or img.get("url_default")


def _to_record(item: dict, keyword: str, today: date):
    nid, title, desc, liked, ts, xsec = _note_fields(item)
    title = clean_text(title or desc or "", 200)
    if not nid or not title:
        return None
    published = _ts_to_iso(ts)
    if published and (today - date.fromisoformat(published[:10])).days > MAX_NOTE_AGE_DAYS:
        return None
    desc = clean_text(desc or "")
    url = f"https://www.xiaohongshu.com/explore/{nid}"
    if xsec:
        url += f"?xsec_token={xsec}&xsec_source=pc_search"
    ds, de = extract_dates(f"{title} {desc}", today)
    cover = _cover_url(item.get("note") or item.get("note_card") or {})
    extra = json.dumps({"likes": str(liked or ""), "kw": keyword, "loc": ""},
                       ensure_ascii=False)
    return Record(
        source="xiaohongshu", source_name="小红书", kind="xhs",
        category=classify(title, desc, "", "other"),
        title=title, url=url, summary=desc,
        date_start=ds, date_end=de, published=published,
        image=cover, rid=f"xhs|{nid}", extra=extra)


def _request(api_key: str, keyword: str, page: int):
    url = f"{TIKHUB_BASE}/{TIKHUB_SEARCH_PATH}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    params = {"keyword": keyword, "page": page, "sort": "general"}
    for attempt in range(3):
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            raise RuntimeError("TikHub key 无效 — 检查 .tikhub_key 内容")
        if resp.status_code == 402:
            raise RuntimeError("TikHub 余额不足 — 到 user.tikhub.io 充值后再跑")
        if resp.status_code == 429:      # rate limited: back off and retry
            _time.sleep(2 * (attempt + 1))
            continue
        raise RuntimeError(f"TikHub HTTP {resp.status_code}: {resp.text[:180]}")
    raise RuntimeError("TikHub 持续限速(429)，稍后再试")


def scrape(api_key: str, today: date, keywords=None, pages: int | None = None) -> list[Record]:
    keywords = keywords or XHS_KEYWORDS
    pages = pages or XHS_PAGES_PER_KEYWORD
    records, seen = [], set()
    for kw in keywords:
        for page in range(1, pages + 1):
            try:
                payload = _request(api_key, kw, page)
            except RuntimeError as e:
                # out of credit / bad key: keep whatever we already gathered
                print(f"[小红书] 提前停止（{e}）— 已抓 {len(records)} 条")
                return records
            notes = _find_note_list(payload) or []
            if not notes:
                break
            for item in notes:
                rec = _to_record(item, kw, today)
                if rec and rec.id not in seen:
                    seen.add(rec.id)
                    records.append(rec)
            _time.sleep(0.5)   # be polite to the API
    return records
