"""
One-shot migration: copy all rows from the legacy SQLite database
(db/amr_data.db) into the Postgres database pointed to by DATABASE_URL.

Usage (from project root, with venv active):
    python scripts/migrate_sqlite_to_postgres.py

Idempotent in practice: uses INSERT ... ON CONFLICT DO NOTHING so re-runs
are safe. Serial-key tables are migrated without their old ids where those
ids are app-internal (alerts, pps_prescriptions, amu_records, amc_records).
"""
import os
import sqlite3
import sys
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from src import db as pgdb  # noqa: E402

SQLITE_PATH = ROOT / "db" / "amr_data.db"


TABLES = [
    # (table, primary-key cols for ON CONFLICT, columns to copy)
    ("users",
     ["email"],
     ["email", "password_hash", "created_at", "last_login",
      "is_active", "is_admin", "is_verified",
      "verification_code", "verification_expires"]),
    ("datasets",
     ["dataset_id"],
     ["dataset_id", "dataset_name", "uploaded_by", "uploaded_at",
      "rows_samples", "rows_tests", "country", "is_country_main"]),
    ("samples",
     ["dataset_id", "sample_id"],
     ["dataset_id", "sample_id", "lab_name", "collection_date", "region",
      "district", "site_type", "source_category", "source_type",
      "food_matrix", "environment_matrix", "latitude", "longitude"]),
    ("ast_results",
     ["dataset_id", "isolate_id", "antibiotic"],
     ["dataset_id", "sample_id", "isolate_id", "organism", "antibiotic",
      "result", "method", "guideline", "test_date", "mic_value",
      "zone_diameter", "auto_interpreted", "interpreted_result",
      "interpretation_guideline", "interpretation_confidence",
      "suspected_mechanism", "interpretation_notes"]),
    ("predictions",
     ["dataset_id", "location_level", "location_name", "organism", "antibiotic"],
     ["dataset_id", "location_level", "location_name", "organism",
      "antibiotic", "predicted_risk", "confidence", "model_version", "run_date"]),
    ("pps_surveys",
     ["survey_id"],
     ["survey_id", "facility_name", "survey_date", "region", "district",
      "total_patients", "patients_on_antibiotics", "uploaded_by",
      "uploaded_at", "dataset_id"]),
]


def _sqlite_has_table(scur, name: str) -> bool:
    scur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return scur.fetchone() is not None


def _sqlite_table_columns(scur, name: str):
    scur.execute(f"PRAGMA table_info({name})")
    return {row[1] for row in scur.fetchall()}


def migrate_fixed_key_tables(sconn, pconn):
    scur = sconn.cursor()
    pcur = pconn.cursor()

    for table, conflict_keys, cols in TABLES:
        if not _sqlite_has_table(scur, table):
            print(f"  - {table}: skipped (no SQLite table)")
            continue
        have = _sqlite_table_columns(scur, table)
        use_cols = [c for c in cols if c in have]
        if not use_cols:
            print(f"  - {table}: skipped (no overlapping columns)")
            continue

        scur.execute(f"SELECT {', '.join(use_cols)} FROM {table}")
        rows = scur.fetchall()
        if not rows:
            print(f"  - {table}: 0 rows")
            continue

        placeholders = ", ".join(["%s"] * len(use_cols))
        conflict_cols = ", ".join(conflict_keys)
        pcur.executemany(
            f"INSERT INTO {table} ({', '.join(use_cols)}) "
            f"VALUES ({placeholders}) ON CONFLICT ({conflict_cols}) DO NOTHING",
            rows,
        )
        pconn.commit()
        print(f"  - {table}: {len(rows)} rows -> inserted (conflicts ignored)")


def migrate_append_tables(sconn, pconn):
    """Tables with auto-generated PKs where old ids don't matter."""
    scur = sconn.cursor()
    pcur = pconn.cursor()

    append_specs = [
        ("alerts",
         ["alert_type", "severity", "title", "description", "organism",
          "antibiotic", "lab_name", "region", "resistance_rate", "threshold",
          "affected_count", "detected_at", "is_acknowledged",
          "acknowledged_by", "acknowledged_at", "notes", "dataset_id"]),
        ("alert_subscriptions",
         ["user_id", "alert_type", "severity_threshold", "email_enabled",
          "sms_enabled", "lab_filter", "organism_filter", "created_at"]),
        ("scheduled_reports",
         ["name", "report_type", "frequency", "recipients", "filters",
          "day_of_week", "day_of_month", "hour", "minute", "is_active",
          "last_run", "next_run", "created_at", "created_by"]),
        ("report_history",
         ["schedule_id", "report_type", "run_time", "status", "recipients",
          "error_message", "file_path"]),
        ("pps_prescriptions",
         ["survey_id", "ward", "patient_age_group", "antibiotic_name",
          "route", "indication", "indication_documented",
          "guideline_compliant", "duration_days"]),
        ("amu_records",
         ["facility_name", "report_period", "region", "district", "sector",
          "antibiotic_name", "atc_code", "formulation", "unit_of_measure",
          "quantity_dispensed", "ddd_per_1000", "patient_days",
          "uploaded_by", "uploaded_at"]),
        ("amc_records",
         ["report_period", "region", "sector", "species", "production_type",
          "antibiotic_class", "antibiotic_name", "atc_vet_code",
          "quantity_kg", "biomass_kg", "mg_per_kg_biomass", "route",
          "purpose", "uploaded_by", "uploaded_at"]),
    ]

    for table, cols in append_specs:
        if not _sqlite_has_table(scur, table):
            print(f"  - {table}: skipped (no SQLite table)")
            continue
        # Skip append-tables that already have rows on the Postgres side to
        # avoid duplicating them on re-runs.
        pcur.execute(f"SELECT COUNT(*) FROM {table}")
        existing = pcur.fetchone()[0]
        if existing:
            print(f"  - {table}: skipped (already has {existing} rows)")
            continue

        have = _sqlite_table_columns(scur, table)
        use_cols = [c for c in cols if c in have]
        if not use_cols:
            print(f"  - {table}: skipped (no overlapping columns)")
            continue
        scur.execute(f"SELECT {', '.join(use_cols)} FROM {table}")
        rows = scur.fetchall()
        if not rows:
            print(f"  - {table}: 0 rows")
            continue
        placeholders = ", ".join(["%s"] * len(use_cols))
        pcur.executemany(
            f"INSERT INTO {table} ({', '.join(use_cols)}) VALUES ({placeholders})",
            rows,
        )
        pconn.commit()
        print(f"  - {table}: {len(rows)} rows -> appended")


def main():
    if not SQLITE_PATH.exists():
        print(f"No SQLite database found at {SQLITE_PATH}; nothing to migrate.")
        return

    print(f"Source: {SQLITE_PATH}")
    print("Ensuring Postgres schema exists...")
    pgdb.init_database()

    sconn = sqlite3.connect(str(SQLITE_PATH))
    pgwrap = pgdb.get_connection()
    pconn = pgwrap.raw

    try:
        print("Migrating tables with stable primary keys (ON CONFLICT DO NOTHING):")
        migrate_fixed_key_tables(sconn, pconn)

        print("Migrating append-style tables (first-run only):")
        migrate_append_tables(sconn, pconn)

        print("Done.")
    finally:
        sconn.close()
        pgwrap.close()


if __name__ == "__main__":
    main()
