"""SQLite persistence: every scraped record with first/last-seen tracking.

The history is the asset — recurrence detection ("this 90% off appears
every week") only works because old rows are never deleted.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  source TEXT, source_name TEXT, kind TEXT, category TEXT,
  title TEXT, url TEXT, summary TEXT, venue TEXT,
  date_start TEXT, date_end TEXT, published TEXT, image TEXT,
  fingerprint TEXT, extra TEXT, norm TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  seen_count INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_records_fp ON records(fingerprint);
CREATE TABLE IF NOT EXISTS runs (
  run_at TEXT, source TEXT, fetched INTEGER, new INTEGER, error TEXT
);
"""


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(records)")}
        if "extra" not in cols:  # migrate DBs created before the extra column
            self.db.execute("ALTER TABLE records ADD COLUMN extra TEXT")
        if "norm" not in cols:   # normalized display fields (merchant/offer/price)
            self.db.execute("ALTER TABLE records ADD COLUMN norm TEXT")

    def save_norm(self, rec_id: str, norm_json: str) -> None:
        self.db.execute("UPDATE records SET norm=? WHERE id=?", (norm_json, rec_id))

    def is_empty(self) -> bool:
        return self.db.execute("SELECT 1 FROM records LIMIT 1").fetchone() is None

    def upsert(self, rec, today_iso: str) -> bool:
        """Insert new record or refresh an existing one. Returns True if new."""
        row = self.db.execute(
            "SELECT last_seen FROM records WHERE id=?", (rec.id,)).fetchone()
        if row is None:
            self.db.execute(
                """INSERT INTO records (id, source, source_name, kind, category,
                   title, url, summary, venue, date_start, date_end, published,
                   image, fingerprint, extra, first_seen, last_seen, seen_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (rec.id, rec.source, rec.source_name, rec.kind, rec.category,
                 rec.title, rec.url, rec.summary, rec.venue, rec.date_start,
                 rec.date_end, rec.published, rec.image, rec.fingerprint,
                 rec.extra, today_iso, today_iso))
            return True
        bump = 1 if row["last_seen"] < today_iso else 0
        self.db.execute(
            """UPDATE records SET title=?, summary=?, category=?, venue=?, url=?,
               date_start=?, date_end=?, image=?, fingerprint=?, extra=?,
               last_seen=?, seen_count=seen_count+? WHERE id=?""",
            (rec.title, rec.summary, rec.category, rec.venue, rec.url,
             rec.date_start, rec.date_end, rec.image, rec.fingerprint, rec.extra,
             today_iso, bump, rec.id))
        return False

    def recurrence_map(self) -> dict:
        """fingerprint -> (distinct posts, day span) for deals seen 2+ times."""
        rows = self.db.execute(
            """SELECT fingerprint, COUNT(*) AS n,
                      CAST(julianday(MAX(COALESCE(published, first_seen))) -
                           julianday(MIN(COALESCE(published, first_seen)))
                           AS INTEGER) AS span
               FROM records
               WHERE kind='deal' AND fingerprint != ''
               GROUP BY fingerprint HAVING n >= 2""")
        return {r["fingerprint"]: (r["n"], r["span"]) for r in rows}

    def select_active(self, today: date, horizon_days=60, stale_days=14) -> list[dict]:
        params = {
            "t": today.isoformat(),
            "h": (today + timedelta(days=horizon_days)).isoformat(),
            "s": (today - timedelta(days=stale_days)).isoformat(),
        }
        rows = self.db.execute(
            """SELECT * FROM records WHERE
                 (kind = 'event' AND date_start IS NOT NULL
                    AND COALESCE(date_end, date_start) >= :t
                    AND date_start <= :h)
               OR
                 (kind != 'event'
                    AND (date_end IS NULL OR date_end >= :t)
                    AND last_seen >= :s
                    AND (date_start IS NULL OR date_start <= :h))""",
            params)
        return [dict(r) for r in rows]

    def log_run(self, run_at, source, fetched, new, error):
        self.db.execute(
            "INSERT INTO runs (run_at, source, fetched, new, error) VALUES (?,?,?,?,?)",
            (run_at, source, fetched, new, error))

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
