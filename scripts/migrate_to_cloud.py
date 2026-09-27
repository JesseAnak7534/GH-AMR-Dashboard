"""
Migrate the ICBB-AMRSS database from one PostgreSQL server to another.

Built for moving the local development database to a managed cloud instance
(Neon, Supabase, Railway, RDS…), but it works between any two Postgres servers.

Usage
-----
    # 1. see what would happen, touching nothing
    python scripts/migrate_to_cloud.py --target "postgresql://..." --dry-run

    # 2. do it
    python scripts/migrate_to_cloud.py --target "postgresql://..."

    # 3. check the copy matches, any time afterwards
    python scripts/migrate_to_cloud.py --target "postgresql://..." --verify-only

The source defaults to DATABASE_URL from the environment/.env. Override with
--source if you are copying between two remote servers.

What it does
------------
* Builds the schema on the target by calling the application's own
  init_database(), so the target gets exactly the tables, constraints and
  indexes the code expects -- no hand-written DDL to drift out of sync.
* Copies tables in dependency order, so foreign keys are satisfied as it goes.
* Uses execute_values for speed and a single transaction per table, so a
  failure part-way leaves that table empty rather than half-filled.
* Refuses to overwrite a target table that already holds rows unless you pass
  --truncate, so a re-run cannot silently duplicate a dataset.
* Verifies row counts per table at the end, and exits non-zero on mismatch.

Safety
------
The source is opened read-only. Nothing is written to it at any point.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


# Parent-before-child. Anything not listed is copied afterwards in
# alphabetical order, so a new table still migrates even if nobody
# remembered to add it here.
ORDERED_TABLES: Tuple[str, ...] = (
    # standalone
    "users",
    "datasets",
    # legacy flat model
    "samples",
    "ast_results",
    # One Health modules
    "pps_surveys",
    "pps_prescriptions",
    "amu_records",
    "amc_records",
    # traceability chain, parents first
    "subjects",
    "encounters",
    "specimens",
    "isolates",
    "phenotypes",
    "sequencing_runs",
    "genomic_results",
    "custody_events",
    # operational
    "alerts",
    "alert_subscriptions",
    "predictions",
    "scheduled_reports",
    "report_history",
)

# Tables whose primary key is a sequence; their sequences need resetting after
# an explicit-id copy or the next insert collides.
SERIAL_TABLES: Dict[str, str] = {
    "custody_events": "event_id",
    "pps_prescriptions": "id",
    "amu_records": "id",
    "amc_records": "id",
    "users": "user_id",
    "scheduled_reports": "id",
    "report_history": "id",
}

BATCH = 1000


def redact(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url or "")


def is_transaction_pooler(url: str) -> bool:
    """Detect a transaction-mode connection pooler.

    Supabase (port 6543) and PgBouncer in transaction mode hand each statement
    a different backend, so a named server-side cursor cannot survive between
    fetches. Callers fall back to client-side buffering, which is fine at this
    database's size.
    """
    try:
        from urllib.parse import urlsplit, parse_qsl
        parts = urlsplit(url)
        if parts.port == 6543:
            return True
        host = (parts.hostname or "").lower()
        if "pooler" in host and parts.port not in (5432, None):
            return True
        return dict(parse_qsl(parts.query)).get("pgbouncer") == "true"
    except Exception:
        return False


def normalise(url: str) -> str:
    """Add sslmode/application_name the same way the application does."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    host = (parts.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}:
        params.setdefault("sslmode", "require")
    params["application_name"] = "amrss-migrate"
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(params), parts.fragment))


def connect(url: str, *, readonly: bool = False):
    conn = psycopg2.connect(normalise(url), connect_timeout=15)
    if readonly:
        conn.set_session(readonly=True)
    return conn


def list_tables(conn) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' "
            "ORDER BY table_name"
        )
        return [r[0] for r in cur.fetchall()]


def columns_of(conn, table: str) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (table,),
        )
        return [r[0] for r in cur.fetchall()]


def row_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "%s"' % table)
        return cur.fetchone()[0]


def migration_order(source_tables: List[str]) -> List[str]:
    ordered = [t for t in ORDERED_TABLES if t in source_tables]
    extra = sorted(set(source_tables) - set(ordered) - {"sqlite_sequence"})
    return ordered + extra


def copy_table(src, dst, table: str, *, truncate: bool, dry_run: bool,
               server_cursor: bool = True) -> Tuple[int, str]:
    """Copy one table. Returns (rows copied, note)."""
    src_cols = columns_of(src, table)
    dst_cols = columns_of(dst, table)
    if not dst_cols:
        return 0, "skipped: table missing on target"

    shared = [c for c in src_cols if c in dst_cols]
    if not shared:
        return 0, "skipped: no overlapping columns"

    dropped = [c for c in src_cols if c not in dst_cols]
    note_bits = []
    if dropped:
        note_bits.append("source-only cols ignored: " + ", ".join(dropped))

    total = row_count(src, table)
    existing = row_count(dst, table)

    if existing and not truncate:
        return 0, f"SKIPPED: target already holds {existing} rows (use --truncate)"

    if dry_run:
        return total, "; ".join(note_bits) or "ok"

    with dst.cursor() as dcur:
        if existing and truncate:
            dcur.execute('TRUNCATE TABLE "%s" CASCADE' % table)
            note_bits.append(f"truncated {existing} existing rows")

    collist = ", ".join('"%s"' % c for c in shared)
    insert = 'INSERT INTO "%s" (%s) VALUES %%s' % (table, collist)

    copied = 0
    try:
        # A named cursor streams the source without loading it all into memory,
        # but it needs a stable backend. Behind a transaction-mode pooler each
        # statement may land on a different connection, so buffer client-side
        # instead. At this database's size that costs a few MB.
        scur = (src.cursor(name="mig_%s" % table) if server_cursor
                else src.cursor())
        if server_cursor:
            scur.itersize = BATCH
        with scur:
            scur.execute('SELECT %s FROM "%s"' % (collist, table))
            with dst.cursor() as dcur:
                while True:
                    rows = scur.fetchmany(BATCH)
                    if not rows:
                        break
                    psycopg2.extras.execute_values(dcur, insert, rows, page_size=BATCH)
                    copied += len(rows)
    finally:
        # A named cursor holds ACCESS SHARE on the source table for as long as
        # its transaction is open. Close it per table rather than leaving one
        # transaction open across the whole migration, which would sit
        # idle-in-transaction and block any DDL on the source.
        src.rollback()   # source is read-only; nothing to commit

    # Reset the sequence so the next insert does not collide with copied ids.
    pk = SERIAL_TABLES.get(table)
    if pk and pk in shared:
        with dst.cursor() as dcur:
            dcur.execute(
                "SELECT setval(pg_get_serial_sequence(%s, %s), "
                "COALESCE((SELECT MAX(\"%s\") FROM \"%s\"), 1), true)"
                % ("%s", "%s", pk, table),
                (table, pk),
            )
        note_bits.append(f"sequence {pk} reset")

    return copied, "; ".join(note_bits) or "ok"


def build_schema_on_target(target_url: str) -> None:
    """Create the schema on the target using the application's own bootstrap."""
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target_url
    for mod in [m for m in list(sys.modules) if m in ("src.db", "src.traceability")]:
        del sys.modules[mod]
    try:
        from src import db as target_db
        target_db.init_database()
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        for mod in [m for m in list(sys.modules) if m in ("src.db", "src.traceability")]:
            del sys.modules[mod]


def verify(src, dst, tables: List[str]) -> bool:
    print("\n%-24s %10s %10s   %s" % ("table", "source", "target", "status"))
    print("-" * 62)
    ok = True
    for t in tables:
        s = row_count(src, t)
        try:
            d = row_count(dst, t)
        except Exception:
            print("%-24s %10d %10s   MISSING ON TARGET" % (t, s, "-"))
            ok = False
            continue
        status = "match" if s == d else "MISMATCH"
        if s != d:
            ok = False
        print("%-24s %10d %10d   %s" % (t, s, d, status))
    print("-" * 62)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True, help="destination Postgres DSN")
    ap.add_argument("--source", default=os.environ.get("DATABASE_URL"),
                    help="source Postgres DSN (default: DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be copied; write nothing")
    ap.add_argument("--verify-only", action="store_true",
                    help="compare row counts only; copy nothing")
    ap.add_argument("--truncate", action="store_true",
                    help="empty a non-empty target table before copying into it")
    ap.add_argument("--skip-schema", action="store_true",
                    help="assume the target schema already exists")
    ap.add_argument("--tables", default="",
                    help="comma-separated list of tables to copy. Everything "
                         "else is left alone. Use this when the target is a "
                         "live database and only some tables are being "
                         "topped up -- copying a table like scheduled_reports "
                         "into production starts it sending email.")
    ap.add_argument("--exclude", default="",
                    help="comma-separated list of tables to skip")
    args = ap.parse_args()

    if not args.source:
        print("No source DSN. Set DATABASE_URL or pass --source.", file=sys.stderr)
        return 2
    if not args.target.startswith(("postgresql://", "postgres://")):
        print("--target must be a PostgreSQL DSN.", file=sys.stderr)
        return 2

    print("source : %s" % redact(args.source))
    print("target : %s" % redact(args.target))
    print("mode   : %s" % ("verify-only" if args.verify_only
                           else "dry-run" if args.dry_run else "migrate"))

    try:
        src = connect(args.source, readonly=True)
    except Exception as e:
        print(f"\nCannot reach the source database: {e}", file=sys.stderr)
        return 1
    try:
        dst = connect(args.target)
    except Exception as e:
        print(f"\nCannot reach the target database: {e}", file=sys.stderr)
        print("Check the DSN, that the instance is awake, and that your IP is "
              "allowed if the provider restricts access.", file=sys.stderr)
        src.close()
        return 1

    try:
        tables = migration_order(list_tables(src))

        only = {t.strip() for t in args.tables.split(",") if t.strip()}
        if only:
            unknown = only - set(tables)
            if unknown:
                print("\nNot present on the source: %s"
                      % ", ".join(sorted(unknown)),
                      file=sys.stderr)
                return 2
            tables = [t for t in tables if t in only]
            print("\nlimited to: %s" % ", ".join(tables))

        excluded = {t.strip() for t in args.exclude.split(",") if t.strip()}
        if excluded:
            tables = [t for t in tables if t not in excluded]
            print("excluding : %s" % ", ".join(sorted(excluded)))

        # Streaming the source needs a stable backend; a transaction pooler
        # cannot give one.
        use_server_cursor = not is_transaction_pooler(args.source)
        if not use_server_cursor:
            print("\nnote: source looks like a transaction pooler; buffering "
                  "client-side instead of streaming")
        if is_transaction_pooler(args.target):
            print("note: target is a transaction pooler. Migration will work, "
                  "but prefer the direct or session-mode connection string for "
                  "the schema build.")

        if args.verify_only:
            return 0 if verify(src, dst, tables) else 1

        if not args.skip_schema and not args.dry_run:
            print("\nbuilding schema on target via init_database() ...")
            build_schema_on_target(args.target)
            print("schema ready")

        print("\n%-24s %10s   %s" % ("table", "rows", "note"))
        print("-" * 70)
        grand = 0
        for t in tables:
            try:
                n, note = copy_table(src, dst, t,
                                     truncate=args.truncate, dry_run=args.dry_run,
                                     server_cursor=use_server_cursor)
                if not args.dry_run:
                    dst.commit()
                grand += n
                print("%-24s %10d   %s" % (t, n, note))
            except Exception as e:
                dst.rollback()
                print("%-24s %10s   FAILED: %s" % (t, "-", e))
                return 1
        print("-" * 70)
        print("%-24s %10d" % ("TOTAL", grand))

        if args.dry_run:
            print("\nDry run only. Nothing was written.")
            return 0

        return 0 if verify(src, dst, tables) else 1
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    sys.exit(main())
