"""SG Radar pipeline: scrape -> track history -> score -> render site."""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import config, normalize, sitegen
from .authenticity import assess
from .dates import extract_dates
from .scrapers import eventbrite, peatix, rss, xhs, xhs_api
from .store import Store


def reextract(store: Store, today: date) -> None:
    """Re-run date extraction over stored rows after a parser improvement."""
    rows = store.db.execute(
        "SELECT id, kind, title, summary, published FROM records WHERE kind != 'event'"
    ).fetchall()
    for row in rows:
        # anchor year-resolution to when the post was written, not today
        try:
            ref = date.fromisoformat((row["published"] or "")[:10])
        except ValueError:
            ref = today
        ds, de = extract_dates(f"{row['title']} {row['summary']}", ref)
        if row["kind"] == "deal" and ds and not de:
            de = ds
        store.db.execute("UPDATE records SET date_start=?, date_end=? WHERE id=?",
                         (ds, de, row["id"]))
    store.commit()
    print(f"[maint] re-extracted dates for {len(rows)} rows")


def seen_days(row: dict) -> int:
    try:
        return (date.fromisoformat(row["last_seen"])
                - date.fromisoformat(row["first_seen"])).days
    except (KeyError, ValueError):
        return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    now = datetime.now(ZoneInfo(config.TZ))
    today = now.date()
    store = Store(config.DB_PATH)
    if "--reextract" in sys.argv:
        reextract(store, today)
    rss_pages = 6 if store.is_empty() else 2

    jobs = [(s["name"], lambda s=s: rss.scrape(s, today, pages=rss_pages))
            for s in config.RSS_SOURCES]
    jobs += [
        ("Eventbrite", lambda: eventbrite.scrape(today, pages=3)),
        ("Peatix", lambda: peatix.scrape(today, pages=3)),
    ]
    tikhub_key = config.load_tikhub_key()
    if tikhub_key:  # paid API preferred — no account/IP risk
        jobs.append(("小红书", lambda: xhs_api.scrape(tikhub_key, today)))
    elif xhs.XHS_DATA_DIR.exists():  # fall back to self-hosted MediaCrawler dump
        jobs.append(("小红书", lambda: xhs.scrape(today)))
    else:
        print("[--]   小红书: 未启用 — 填 .tikhub_key 用付费API，或跑 update_xhs.bat 扫码自建")

    ok_sources = 0
    for name, job in jobs:
        try:
            recs = job()
            new = sum(store.upsert(r, today.isoformat()) for r in recs)
            store.log_run(now.isoformat(), name, len(recs), new, None)
            store.commit()
            ok_sources += 1
            print(f"[ok]   {name}: {len(recs)} fetched, {new} new")
        except Exception as e:
            store.log_run(now.isoformat(), name, 0, 0, str(e))
            store.commit()
            print(f"[fail] {name}: {e}")
            traceback.print_exc()

    recurrence = store.recurrence_map()
    active = store.select_active(today)
    for r in active:
        r["seen_days"] = seen_days(r)
        if r["kind"] == "deal":
            r["auth"] = assess(r, today, recurrence.get(r["fingerprint"]))

    # normalize messy sources (deal/xhs) into merchant·offer·price so every
    # row reads the same shape. Rule-based always; LLM enhances when available.
    def needs_norm(r):
        if r["kind"] not in ("deal", "xhs"):
            return False
        if not r.get("norm"):
            return True
        try:                       # retry LLM on rows that only got rule-based
            return json.loads(r["norm"]).get("method") == "rule"
        except (TypeError, ValueError):
            return True
    todo = [r for r in active if needs_norm(r)]
    if todo:
        norms = normalize.normalize(todo, config.load_openrouter_key() or None)
        for r in todo:
            n = norms.get(r["id"])
            if n:
                r["norm"] = json.dumps(n, ensure_ascii=False)
                store.save_norm(r["id"], r["norm"])
        store.commit()
    for r in active:               # parse norm onto records for rendering
        if r.get("norm"):
            try:
                r["norm_obj"] = json.loads(r["norm"])
            except (TypeError, ValueError):
                r["norm_obj"] = None

    sitegen.render(active, now, config.SITE_PATH)

    n_event = sum(1 for r in active if r["kind"] == "event")
    n_deal = sum(1 for r in active if r["kind"] == "deal")
    n_ever = sum(1 for r in active
                 if r.get("auth", {}).get("label") == "evergreen")
    print(f"\nSite: {config.SITE_PATH}")
    print(f"Active: {len(active)} ({n_event} events, {n_deal} deals, "
          f"{n_ever} flagged evergreen) from {ok_sources}/{len(jobs)} sources")
    store.close()
    return 0 if ok_sources else 1


if __name__ == "__main__":
    sys.exit(main())
