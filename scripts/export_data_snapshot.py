"""
Export the data tables from the currently-active database (local Postgres
or SQLite) to a single gzip-compressed JSON snapshot at
``db/cloud_snapshot.json.gz``.  The snapshot is small enough to commit
to the repository (~2 MB for 1k samples + 5k AST results), and the
Streamlit Cloud app loads it on first startup when the cloud Postgres
tables are still empty -- this is how we seed Supabase without having
to open an outbound connection from the maintainer's network (which is
firewalled off from Supabase's pooler).

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
TABLES = [
    "users",
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
    print(f"Backend in use: {db._BACKEND}")
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
