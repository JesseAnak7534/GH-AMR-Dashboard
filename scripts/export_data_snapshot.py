"""
Export the data tables from the currently-active database to a single
gzip-compressed JSON snapshot at ``db/cloud_snapshot.json.gz``.

This is a backup tool. It used to be half of a seeding mechanism: the snapshot
was committed to the repository and the Streamlit app replayed it on startup
whenever it found the `samples` table empty, which was how data reached Supabase
from a network that could not open a connection to the pooler.

That seed has been removed, and this script no longer feeds anything. The reason
is worth recording: an empty `samples` table is a deliberate state -- it is what
the database looks like once it has been cleared to load a fresh dataset -- and
the seed treated it as damage to repair, restoring the rows that had just been
deleted. A wipe therefore could not stick, and demo data reappeared on the
dashboard looking current.

The output path is gitignored for the same reason. Keep the snapshot as a local
backup; do not commit it, and do not wire it back into application startup. Data
belongs in the database, not compiled into the app that reads it.

Usage (from project root):
    python scripts/export_data_snapshot.py
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import db  # noqa: E402

SNAPSHOT_PATH = ROOT / "db" / "cloud_snapshot.json.gz"

# Order matters: parents (datasets, users, pps_surveys) before children
# (samples, ast_results, pps_prescriptions, predictions).
# `users` is deliberately absent. This snapshot is committed to a public
# repository, and the table holds email addresses and bcrypt password hashes.
# There is no lab-login bootstrap any more: per-laboratory accounts were
# retired, and the administrator account comes from ADMIN_EMAIL /
# ADMIN_PASSWORD.
TABLES = [
    "datasets",
    "samples",
    "ast_results",
    "predictions",
    "pps_surveys",
    "pps_prescriptions",
    "amu_records",
    "amc_records",
]


def _json_default(obj):
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


def main():
    print("Backend in use: PostgreSQL")
    conn = db.get_connection()
    cur = conn.cursor()

    snapshot = {"created_at": dt.datetime.utcnow().isoformat(), "tables": {}}
    total_rows = 0
    for table in TABLES:
        try:
            cur.execute(f"SELECT * FROM {table}")
        except Exception as e:
            print(f"  - {table}: skipped ({type(e).__name__})")
            continue
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        snapshot["tables"][table] = {"columns": cols, "rows": rows}
        total_rows += len(rows)
        print(f"  - {table}: {len(rows)} rows")

    conn.close()

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(SNAPSHOT_PATH, "wt", encoding="utf-8") as f:
        json.dump(snapshot, f, default=_json_default, separators=(",", ":"))

    size_mb = SNAPSHOT_PATH.stat().st_size / (1024 * 1024)
    print(f"\nWrote {SNAPSHOT_PATH}  ({size_mb:.2f} MB, {total_rows} total rows)")


if __name__ == "__main__":
    main()
