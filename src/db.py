"""
Database module for AMR Surveillance Dashboard.

Dual-backend: prefers PostgreSQL (psycopg2) when a reachable DATABASE_URL
is configured, falls back to SQLite at ``db/amr_data.db`` otherwise. This
makes the app work on Streamlit Cloud out-of-the-box (SQLite) while still
using the better Postgres backend locally / when a managed DB (Supabase,
Neon, RDS…) is wired up via DATABASE_URL or Streamlit secrets.

The public function surface is stable — `get_connection()` returns a
wrapper that supports ``.execute(sql).fetchone()[0]`` and dict-style row
access in both modes. SQL is written in Postgres dialect (``%s``
placeholders, ``ON CONFLICT … DO UPDATE``, ``RETURNING id``) and
translated on the fly when the active backend is SQLite.
"""
import os
import re
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import pandas as pd

# Populate env vars from .env before we read DATABASE_URL. Safe no-op if
# dotenv isn't installed or .env doesn't exist. Must happen before any
# module-level call to _resolve_backend().
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore
    _PSYCOPG2_AVAILABLE = False


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------

_SQLITE_DIR  = "db"
_SQLITE_PATH = os.path.join(_SQLITE_DIR, "amr_data.db")

_BACKEND: str = ""       # "postgres" | "sqlite" — set by _resolve_backend
_PG_DSN: Optional[str] = None


def _read_database_url() -> Optional[str]:
    """Pick DATABASE_URL from env or Streamlit secrets, or None."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url.strip() or None
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            val = str(st.secrets["DATABASE_URL"]).strip()
            return val or None
    except Exception:
        pass
    return None


def _resolve_backend() -> None:
    """Decide at import time whether Postgres is reachable; else SQLite."""
    global _BACKEND, _PG_DSN

    url = _read_database_url()
    if url and _PSYCOPG2_AVAILABLE and url.startswith(("postgresql://", "postgres://")):
        try:
            test = psycopg2.connect(url, connect_timeout=3)
            test.close()
            _BACKEND = "postgres"
            _PG_DSN = url
            logger.info("db backend: PostgreSQL")
            return
        except Exception as e:
            logger.warning("db backend: Postgres at %s not reachable (%s); "
                           "falling back to SQLite", _redact(url), e.__class__.__name__)

    # Fallback
    os.makedirs(_SQLITE_DIR, exist_ok=True)
    _BACKEND = "sqlite"
    logger.info("db backend: SQLite (%s)", _SQLITE_PATH)


def _redact(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


_resolve_backend()


def is_postgres() -> bool:
    return _BACKEND == "postgres"


def is_sqlite() -> bool:
    return _BACKEND == "sqlite"


# ---------------------------------------------------------------------------
# Dialect translation — Postgres SQL is the source of truth; we rewrite it
# for SQLite on the fly so all downstream code can stay vendor-neutral.
# ---------------------------------------------------------------------------

_PG_TO_SQLITE_DDL = [
    (re.compile(r"\bBIGSERIAL\b", re.I), "INTEGER"),
    (re.compile(r"\bSERIAL\b",    re.I), "INTEGER"),
    (re.compile(r"\bDOUBLE PRECISION\b", re.I), "REAL"),
    (re.compile(r"\bSMALLINT\b",  re.I), "INTEGER"),
]


def _translate_sql(sql: str) -> str:
    """Rewrite Postgres-dialect SQL for SQLite when the active backend is
    SQLite. No-op on Postgres."""
    if _BACKEND != "sqlite":
        return sql

    # %s placeholder → ? (skip %s inside string literals — we don't build
    # SQL that needs that). Safe for our internal call sites.
    sql = sql.replace("%s", "?")

    # Type keywords that SQLite doesn't know → map to compatible types.
    for pat, repl in _PG_TO_SQLITE_DDL:
        sql = pat.sub(repl, sql)

    # INTEGER PRIMARY KEY → INTEGER PRIMARY KEY AUTOINCREMENT (for tables
    # that originally used BIGSERIAL; needed so lastrowid + RETURNING work).
    sql = re.sub(
        r"\bINTEGER PRIMARY KEY(?!\s+AUTOINCREMENT)\b",
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        sql, flags=re.I,
    )

    return sql


# ---------------------------------------------------------------------------
# Connection wrappers
# ---------------------------------------------------------------------------

class _PGCursorProxy:
    """Wraps psycopg2 DictCursor; identical behaviour."""
    def __init__(self, raw): self._raw = raw
    def execute(self, sql, params=None):
        self._raw.execute(sql, params or ())
        return self
    def executemany(self, sql, seq_of_params):
        self._raw.executemany(sql, seq_of_params)
        return self
    def fetchone(self): return self._raw.fetchone()
    def fetchall(self): return self._raw.fetchall()
    def fetchmany(self, size=None): return self._raw.fetchmany(size) if size else self._raw.fetchmany()
    @property
    def description(self): return self._raw.description
    @property
    def rowcount(self):    return self._raw.rowcount
    @property
    def lastrowid(self):   return getattr(self._raw, "lastrowid", None)
    def close(self): self._raw.close()


class _SqliteCursorProxy:
    """Wraps sqlite3.Cursor with SQL dialect translation so Postgres-style
    queries work against SQLite unchanged."""
    def __init__(self, raw): self._raw = raw
    def execute(self, sql, params=None):
        self._raw.execute(_translate_sql(sql), params or ())
        return self
    def executemany(self, sql, seq_of_params):
        self._raw.executemany(_translate_sql(sql), seq_of_params)
        return self
    def fetchone(self): return self._raw.fetchone()
    def fetchall(self): return self._raw.fetchall()
    def fetchmany(self, size=None): return self._raw.fetchmany(size) if size else self._raw.fetchmany()
    @property
    def description(self): return self._raw.description
    @property
    def rowcount(self):    return self._raw.rowcount
    @property
    def lastrowid(self):   return self._raw.lastrowid
    def close(self): self._raw.close()


class _ConnectionWrapper:
    """Uniform connection surface across both backends."""

    def __init__(self, raw, backend: str):
        self._raw = raw
        self._backend = backend

    def cursor(self, *args, **kwargs):
        if self._backend == "postgres":
            kwargs.setdefault("cursor_factory", psycopg2.extras.DictCursor)
            return _PGCursorProxy(self._raw.cursor(*args, **kwargs))
        # sqlite
        return _SqliteCursorProxy(self._raw.cursor())

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):   return self._raw.commit()
    def rollback(self): return self._raw.rollback()
    def close(self):    return self._raw.close()

    @property
    def raw(self): return self._raw


def get_connection() -> _ConnectionWrapper:
    """Open a fresh connection in the active backend."""
    if _BACKEND == "postgres":
        return _ConnectionWrapper(psycopg2.connect(_PG_DSN), "postgres")
    # SQLite
    os.makedirs(_SQLITE_DIR, exist_ok=True)
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return _ConnectionWrapper(conn, "sqlite")


def _fetch_df(sql: str, params=None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Stays off pandas's connection-
    detection path (which insists on SQLAlchemy engines for non-sqlite)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        cur.close()
        # Both DictRow (psycopg2) and sqlite3.Row support dict() conversion.
        return pd.DataFrame([dict(r) for r in rows], columns=cols)
    finally:
        conn.close()


def _safe_add_column(cur, table: str, column: str, ddl: str):
    """Idempotent column add. Postgres: IF NOT EXISTS.  SQLite: try/except
    on duplicate-column error (no IF NOT EXISTS for ALTER TABLE in SQLite)."""
    if _BACKEND == "postgres":
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        except Exception:
            logger.exception("ADD COLUMN %s.%s failed", table, column)
        return
    # SQLite
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            logger.warning("ADD COLUMN %s.%s: %s", table, column, e)


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

def init_database():
    """Initialize database schema (idempotent)."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGSERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            is_active SMALLINT DEFAULT 1,
            is_admin SMALLINT DEFAULT 0
        )
    """)
    _safe_add_column(cur, "users", "is_verified", "SMALLINT DEFAULT 0")
    _safe_add_column(cur, "users", "verification_code", "TEXT")
    _safe_add_column(cur, "users", "verification_expires", "TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id TEXT PRIMARY KEY,
            dataset_name TEXT NOT NULL,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL,
            rows_samples INTEGER,
            rows_tests INTEGER
        )
    """)
    _safe_add_column(cur, "datasets", "country", "TEXT")
    _safe_add_column(cur, "datasets", "is_country_main", "SMALLINT DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            dataset_id TEXT,
            sample_id TEXT,
            lab_name TEXT,
            collection_date TEXT,
            region TEXT,
            district TEXT,
            site_type TEXT,
            source_category TEXT,
            source_type TEXT,
            food_matrix TEXT,
            environment_matrix TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            PRIMARY KEY (dataset_id, sample_id)
        )
    """)
    _safe_add_column(cur, "samples", "lab_name", "TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ast_results (
            dataset_id TEXT,
            sample_id TEXT,
            isolate_id TEXT,
            organism TEXT,
            antibiotic TEXT,
            result TEXT,
            method TEXT,
            guideline TEXT,
            test_date TEXT,
            mic_value DOUBLE PRECISION,
            zone_diameter DOUBLE PRECISION,
            auto_interpreted SMALLINT DEFAULT 0,
            interpreted_result TEXT,
            interpretation_guideline TEXT,
            interpretation_confidence TEXT,
            suspected_mechanism TEXT,
            interpretation_notes TEXT,
            PRIMARY KEY (dataset_id, isolate_id, antibiotic)
        )
    """)
    for col, ddl in [
        ("zone_diameter", "DOUBLE PRECISION"),
        ("auto_interpreted", "SMALLINT DEFAULT 0"),
        ("interpreted_result", "TEXT"),
        ("interpretation_guideline", "TEXT"),
        ("interpretation_confidence", "TEXT"),
        ("suspected_mechanism", "TEXT"),
        ("interpretation_notes", "TEXT"),
    ]:
        _safe_add_column(cur, "ast_results", col, ddl)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            dataset_id TEXT,
            location_level TEXT,
            location_name TEXT,
            organism TEXT,
            antibiotic TEXT,
            predicted_risk DOUBLE PRECISION,
            confidence DOUBLE PRECISION,
            model_version TEXT,
            run_date TEXT,
            PRIMARY KEY (dataset_id, location_level, location_name, organism, antibiotic)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id BIGSERIAL PRIMARY KEY,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            organism TEXT,
            antibiotic TEXT,
            lab_name TEXT,
            region TEXT,
            resistance_rate DOUBLE PRECISION,
            threshold DOUBLE PRECISION,
            affected_count INTEGER,
            detected_at TEXT NOT NULL,
            is_acknowledged INTEGER DEFAULT 0,
            acknowledged_by TEXT,
            acknowledged_at TEXT,
            notes TEXT,
            dataset_id TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            subscription_id BIGSERIAL PRIMARY KEY,
            user_id INTEGER,
            alert_type TEXT,
            severity_threshold TEXT DEFAULT 'MEDIUM',
            email_enabled INTEGER DEFAULT 1,
            sms_enabled INTEGER DEFAULT 0,
            lab_filter TEXT,
            organism_filter TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reports (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            report_type TEXT NOT NULL,
            frequency TEXT NOT NULL,
            recipients TEXT NOT NULL,
            filters TEXT,
            day_of_week INTEGER DEFAULT 0,
            day_of_month INTEGER DEFAULT 1,
            hour INTEGER DEFAULT 8,
            minute INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS report_history (
            id BIGSERIAL PRIMARY KEY,
            schedule_id INTEGER,
            report_type TEXT,
            run_time TEXT NOT NULL,
            status TEXT NOT NULL,
            recipients TEXT,
            error_message TEXT,
            file_path TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pps_surveys (
            survey_id TEXT PRIMARY KEY,
            facility_name TEXT NOT NULL,
            survey_date TEXT NOT NULL,
            region TEXT,
            district TEXT,
            total_patients INTEGER,
            patients_on_antibiotics INTEGER,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL,
            dataset_id TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pps_prescriptions (
            id BIGSERIAL PRIMARY KEY,
            survey_id TEXT NOT NULL,
            ward TEXT,
            patient_age_group TEXT,
            antibiotic_name TEXT NOT NULL,
            route TEXT,
            indication TEXT,
            indication_documented INTEGER DEFAULT 0,
            guideline_compliant INTEGER DEFAULT 0,
            duration_days DOUBLE PRECISION
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS amu_records (
            id BIGSERIAL PRIMARY KEY,
            facility_name TEXT NOT NULL,
            report_period TEXT NOT NULL,
            region TEXT,
            district TEXT,
            sector TEXT DEFAULT 'HUMAN',
            antibiotic_name TEXT NOT NULL,
            atc_code TEXT,
            formulation TEXT,
            unit_of_measure TEXT,
            quantity_dispensed DOUBLE PRECISION,
            ddd_per_1000 DOUBLE PRECISION,
            patient_days INTEGER,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS amc_records (
            id BIGSERIAL PRIMARY KEY,
            report_period TEXT NOT NULL,
            region TEXT,
            sector TEXT NOT NULL DEFAULT 'ANIMAL',
            species TEXT,
            production_type TEXT,
            antibiotic_class TEXT NOT NULL,
            antibiotic_name TEXT,
            atc_vet_code TEXT,
            quantity_kg DOUBLE PRECISION,
            biomass_kg DOUBLE PRECISION,
            mg_per_kg_biomass DOUBLE PRECISION,
            route TEXT,
            purpose TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Dataset + AST CRUD
# ---------------------------------------------------------------------------

def save_dataset(dataset_id: str, dataset_name: str, samples_df: pd.DataFrame,
                 ast_df: pd.DataFrame, uploaded_by: str = "System"):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO datasets (dataset_id, dataset_name, uploaded_by, uploaded_at, rows_samples, rows_tests)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (dataset_id, dataset_name, uploaded_by, datetime.now().isoformat(),
              len(samples_df), len(ast_df)))

        for _, row in samples_df.iterrows():
            cur.execute("""
                INSERT INTO samples
                (dataset_id, sample_id, lab_name, collection_date, region, district, site_type,
                 source_category, source_type, food_matrix, environment_matrix, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                dataset_id,
                row.get('sample_id'), row.get('lab_name'), row.get('collection_date'),
                row.get('region'), row.get('district'), row.get('site_type'),
                row.get('source_category'), row.get('source_type'),
                row.get('food_matrix'), row.get('environment_matrix'),
                row.get('latitude'), row.get('longitude'),
            ))

        for _, row in ast_df.iterrows():
            cur.execute("""
                INSERT INTO ast_results
                (dataset_id, sample_id, isolate_id, organism, antibiotic, result, method, guideline, test_date, mic_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                dataset_id,
                row.get('sample_id'), row.get('isolate_id'), row.get('organism'),
                row.get('antibiotic'), row.get('result'), row.get('method'),
                row.get('guideline'), row.get('test_date'), row.get('mic_value'),
            ))

        conn.commit()
        return True, "Data saved successfully"
    except Exception as e:
        conn.rollback()
        logger.exception("save_dataset failed")
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def get_all_datasets() -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM datasets ORDER BY uploaded_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_dataset_main(dataset_id: str, is_main: bool = True, country: Optional[str] = None) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        if is_main and country:
            cur.execute(
                "UPDATE datasets SET is_country_main = 1, country = %s WHERE dataset_id = %s",
                (country, dataset_id)
            )
        else:
            cur.execute(
                "UPDATE datasets SET is_country_main = %s, country = COALESCE(country, %s) WHERE dataset_id = %s",
                (1 if is_main else 0, country, dataset_id)
            )
        conn.commit()
        return True, "Dataset main status updated"
    except Exception as e:
        conn.rollback()
        return False, f"Error updating main status: {str(e)}"
    finally:
        conn.close()


def get_main_datasets(country: Optional[str] = None) -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    if country:
        cur.execute(
            "SELECT * FROM datasets WHERE is_country_main = 1 AND country = %s ORDER BY uploaded_at DESC",
            (country,)
        )
    else:
        cur.execute("SELECT * FROM datasets WHERE is_country_main = 1 ORDER BY uploaded_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_datasets_by_uploader(email: str) -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM datasets WHERE uploaded_by = %s ORDER BY uploaded_at DESC", (email,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def merge_dataset_into_main(source_dataset_id: str, main_dataset_id: str) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        samples_df = get_dataset_samples(source_dataset_id)
        ast_df = get_dataset_ast(source_dataset_id)
        if samples_df.empty and ast_df.empty:
            return False, "Source dataset is empty"

        id_map = {}
        empty_sample_counter = 0
        for _, row in samples_df.iterrows():
            old_sid = row.get('sample_id') or ''
            if old_sid:
                new_sid = f"{source_dataset_id}-{old_sid}"
            else:
                empty_sample_counter += 1
                new_sid = f"{source_dataset_id}-sample-{empty_sample_counter}"
            id_map[old_sid] = new_sid
            cur.execute("""
                INSERT INTO samples
                (dataset_id, sample_id, lab_name, collection_date, region, district, site_type,
                 source_category, source_type, food_matrix, environment_matrix, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id, sample_id) DO UPDATE SET
                    lab_name = EXCLUDED.lab_name,
                    collection_date = EXCLUDED.collection_date,
                    region = EXCLUDED.region,
                    district = EXCLUDED.district,
                    site_type = EXCLUDED.site_type,
                    source_category = EXCLUDED.source_category,
                    source_type = EXCLUDED.source_type,
                    food_matrix = EXCLUDED.food_matrix,
                    environment_matrix = EXCLUDED.environment_matrix,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude
            """, (
                main_dataset_id, new_sid,
                row.get('lab_name'), row.get('collection_date'),
                row.get('region'), row.get('district'), row.get('site_type'),
                row.get('source_category'), row.get('source_type'),
                row.get('food_matrix'), row.get('environment_matrix'),
                row.get('latitude'), row.get('longitude'),
            ))

        added_samples = len(id_map)

        empty_isolate_counter = 0
        for _, row in ast_df.iterrows():
            old_sid = row.get('sample_id') or ''
            new_sid = id_map.get(old_sid, f"{source_dataset_id}-{old_sid}")
            old_isolate = row.get('isolate_id') or ''
            if old_isolate:
                new_isolate = f"{source_dataset_id}-{old_isolate}"
            else:
                empty_isolate_counter += 1
                new_isolate = f"{source_dataset_id}-isolate-{empty_isolate_counter}"
            cur.execute("""
                INSERT INTO ast_results
                (dataset_id, sample_id, isolate_id, organism, antibiotic, result, method, guideline, test_date, mic_value,
                 zone_diameter, auto_interpreted, interpreted_result, interpretation_guideline, interpretation_confidence,
                 suspected_mechanism, interpretation_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id, isolate_id, antibiotic) DO UPDATE SET
                    sample_id = EXCLUDED.sample_id,
                    organism = EXCLUDED.organism,
                    result = EXCLUDED.result,
                    method = EXCLUDED.method,
                    guideline = EXCLUDED.guideline,
                    test_date = EXCLUDED.test_date,
                    mic_value = EXCLUDED.mic_value,
                    zone_diameter = EXCLUDED.zone_diameter,
                    auto_interpreted = EXCLUDED.auto_interpreted,
                    interpreted_result = EXCLUDED.interpreted_result,
                    interpretation_guideline = EXCLUDED.interpretation_guideline,
                    interpretation_confidence = EXCLUDED.interpretation_confidence,
                    suspected_mechanism = EXCLUDED.suspected_mechanism,
                    interpretation_notes = EXCLUDED.interpretation_notes
            """, (
                main_dataset_id, new_sid, new_isolate,
                row.get('organism'), row.get('antibiotic'), row.get('result'),
                row.get('method'), row.get('guideline'), row.get('test_date'),
                row.get('mic_value'), row.get('zone_diameter'),
                row.get('auto_interpreted'), row.get('interpreted_result'),
                row.get('interpretation_guideline'), row.get('interpretation_confidence'),
                row.get('suspected_mechanism'), row.get('interpretation_notes'),
            ))

        added_tests = len(ast_df)

        cur.execute(
            "UPDATE datasets SET rows_samples = COALESCE(rows_samples, 0) + %s, "
            "rows_tests = COALESCE(rows_tests, 0) + %s WHERE dataset_id = %s",
            (added_samples, added_tests, main_dataset_id)
        )

        conn.commit()
        return True, f"Merged {added_samples} samples and {added_tests} tests into main dataset"
    except Exception as e:
        conn.rollback()
        logger.exception("merge_dataset_into_main failed")
        return False, f"Error during merge: {str(e)}"
    finally:
        conn.close()


def get_dataset_samples(dataset_id: str) -> pd.DataFrame:
    return _fetch_df("SELECT * FROM samples WHERE dataset_id = %s", (dataset_id,))


def get_dataset_ast(dataset_id: str) -> pd.DataFrame:
    return _fetch_df("SELECT * FROM ast_results WHERE dataset_id = %s", (dataset_id,))


def get_all_ast_results() -> pd.DataFrame:
    return _fetch_df("SELECT * FROM ast_results")


def get_all_samples() -> pd.DataFrame:
    return _fetch_df("SELECT * FROM samples")


def get_resistance_stats(dataset_id: Optional[str] = None) -> pd.DataFrame:
    query = """
        SELECT organism, antibiotic, result, COUNT(*) AS count
        FROM ast_results
    """
    params: tuple = ()
    if dataset_id:
        query += " WHERE dataset_id = %s"
        params = (dataset_id,)
    query += " GROUP BY organism, antibiotic, result"
    return _fetch_df(query, params)


def delete_dataset(dataset_id: str) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM ast_results WHERE dataset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM samples WHERE dataset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM datasets WHERE dataset_id = %s", (dataset_id,))
        conn.commit()
        return True, "Dataset deleted successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Error deleting dataset: {str(e)}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(email: str, password_hash: str, is_admin: bool = False) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (email, password_hash, created_at, is_active, is_admin, is_verified)
            VALUES (%s, %s, %s, 1, %s, 1)
        """, (email, password_hash, datetime.now().isoformat(), 1 if is_admin else 0))
        conn.commit()
        return True, "User created successfully"
    except (sqlite3.IntegrityError,
            *( (psycopg2.IntegrityError,) if _PSYCOPG2_AVAILABLE else () )):
        conn.rollback()
        return False, "Email already registered"
    except Exception as e:
        conn.rollback()
        return False, f"Error creating user: {str(e)}"
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, email, created_at, last_login, is_active, is_admin
        FROM users
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_last_login(email: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET last_login = %s WHERE email = %s",
                    (datetime.now().isoformat(), email))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_user_status(user_id: int, is_active: bool) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET is_active = %s WHERE user_id = %s",
                    (1 if is_active else 0, user_id))
        conn.commit()
        status = "activated" if is_active else "deactivated"
        return True, f"User {status} successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Error updating user: {str(e)}"
    finally:
        conn.close()


def update_user_password(email: str, new_password_hash: str) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s",
                    (new_password_hash, email))
        conn.commit()
        return True, "Password updated successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Error updating password: {str(e)}"
    finally:
        conn.close()


def set_verification_code(email: str, code: str, expires_at: str) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET verification_code = %s, verification_expires = %s WHERE email = %s",
            (code, expires_at, email)
        )
        conn.commit()
        return True, "Verification code set"
    except Exception as e:
        conn.rollback()
        return False, f"Error setting verification code: {str(e)}"
    finally:
        conn.close()


def verify_user_email(email: str, code: str) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT verification_code, verification_expires FROM users WHERE email = %s",
                    (email,))
        row = cur.fetchone()
        if not row:
            return False, "User not found"
        saved_code = row["verification_code"]
        expires = row["verification_expires"]
        if not saved_code:
            return False, "No verification code set"
        if str(saved_code) != str(code):
            return False, "Invalid verification code"
        try:
            if expires and datetime.fromisoformat(expires) < datetime.now():
                return False, "Verification code expired"
        except Exception:
            pass
        cur.execute(
            "UPDATE users SET is_verified = 1, verification_code = NULL, verification_expires = NULL WHERE email = %s",
            (email,)
        )
        conn.commit()
        return True, "Email verified"
    except Exception as e:
        conn.rollback()
        return False, f"Error verifying email: {str(e)}"
    finally:
        conn.close()


def set_user_verified(email: str, is_verified: bool = True) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET is_verified = %s WHERE email = %s",
                    (1 if is_verified else 0, email))
        conn.commit()
        return True, "User verification flag updated"
    except Exception as e:
        conn.rollback()
        return False, f"Error updating verification flag: {str(e)}"
    finally:
        conn.close()


def delete_user(user_id: int) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()
        return True, "User deleted successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Error deleting user: {str(e)}"
    finally:
        conn.close()


def set_user_admin(email: str, is_admin: bool) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET is_admin = %s WHERE email = %s",
                    (1 if is_admin else 0, email))
        conn.commit()
        status = "granted" if is_admin else "revoked"
        return True, f"Admin privileges {status}"
    except Exception as e:
        conn.rollback()
        return False, f"Error updating admin flag: {str(e)}"
    finally:
        conn.close()


def delete_non_admin_users(admin_email: Optional[str] = None) -> Tuple[int, str]:
    """Delete all users except the admin(s)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if admin_email:
            cur.execute("DELETE FROM users WHERE email <> %s", (admin_email,))
        else:
            cur.execute("DELETE FROM users WHERE COALESCE(is_admin, 0) = 0")
        deleted = cur.rowcount or 0
        conn.commit()
        return deleted, f"Deleted {deleted} non-admin user(s)"
    except Exception as e:
        conn.rollback()
        return 0, f"Error deleting non-admin users: {str(e)}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PPS CRUD
# ---------------------------------------------------------------------------

def save_pps_survey(survey_id, facility_name, survey_date, region, district,
                    total_patients, patients_on_antibiotics,
                    prescriptions_df, uploaded_by="System"):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO pps_surveys
            (survey_id, facility_name, survey_date, region, district,
             total_patients, patients_on_antibiotics, uploaded_by, uploaded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (survey_id, facility_name, survey_date, region, district,
              total_patients, patients_on_antibiotics, uploaded_by,
              datetime.now().isoformat()))

        for _, row in prescriptions_df.iterrows():
            cur.execute("""
                INSERT INTO pps_prescriptions
                (survey_id, ward, patient_age_group, antibiotic_name,
                 route, indication, indication_documented,
                 guideline_compliant, duration_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (survey_id,
                  row.get('ward'), row.get('patient_age_group'),
                  row.get('antibiotic_name'), row.get('route'),
                  row.get('indication'),
                  1 if str(row.get('indication_documented', 0)).strip().lower() in ('1', 'yes', 'true') else 0,
                  1 if str(row.get('guideline_compliant', 0)).strip().lower() in ('1', 'yes', 'true') else 0,
                  row.get('duration_days')))

        conn.commit()
        return True, "PPS survey saved"
    except Exception as e:
        conn.rollback()
        return False, f"PPS save error: {e}"
    finally:
        conn.close()


def get_pps_surveys():
    return _fetch_df("SELECT * FROM pps_surveys ORDER BY survey_date DESC")


def get_pps_prescriptions(survey_id=None):
    if survey_id:
        return _fetch_df("SELECT * FROM pps_prescriptions WHERE survey_id = %s", (survey_id,))
    return _fetch_df("SELECT * FROM pps_prescriptions")


# ---------------------------------------------------------------------------
# AMU CRUD
# ---------------------------------------------------------------------------

def save_amu_records(records_df, uploaded_by="System"):
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    try:
        for _, row in records_df.iterrows():
            cur.execute("""
                INSERT INTO amu_records
                (facility_name, report_period, region, district, sector,
                 antibiotic_name, atc_code, formulation, unit_of_measure,
                 quantity_dispensed, ddd_per_1000, patient_days,
                 uploaded_by, uploaded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row.get('facility_name'), row.get('report_period'),
                row.get('region'), row.get('district'),
                row.get('sector', 'HUMAN'),
                row.get('antibiotic_name'), row.get('atc_code'),
                row.get('formulation'), row.get('unit_of_measure'),
                row.get('quantity_dispensed'), row.get('ddd_per_1000'),
                row.get('patient_days'), uploaded_by, now))
        conn.commit()
        return True, f"{len(records_df)} AMU records saved"
    except Exception as e:
        conn.rollback()
        return False, f"AMU save error: {e}"
    finally:
        conn.close()


def get_amu_records():
    return _fetch_df("SELECT * FROM amu_records ORDER BY report_period DESC")


# ---------------------------------------------------------------------------
# AMC CRUD
# ---------------------------------------------------------------------------

def save_amc_records(records_df, uploaded_by="System"):
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    try:
        for _, row in records_df.iterrows():
            cur.execute("""
                INSERT INTO amc_records
                (report_period, region, sector, species, production_type,
                 antibiotic_class, antibiotic_name, atc_vet_code,
                 quantity_kg, biomass_kg, mg_per_kg_biomass,
                 route, purpose, uploaded_by, uploaded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row.get('report_period'), row.get('region'),
                row.get('sector', 'ANIMAL'), row.get('species'),
                row.get('production_type'),
                row.get('antibiotic_class'), row.get('antibiotic_name'),
                row.get('atc_vet_code'),
                row.get('quantity_kg'), row.get('biomass_kg'),
                row.get('mg_per_kg_biomass'),
                row.get('route'), row.get('purpose'),
                uploaded_by, now))
        conn.commit()
        return True, f"{len(records_df)} AMC records saved"
    except Exception as e:
        conn.rollback()
        return False, f"AMC save error: {e}"
    finally:
        conn.close()


def get_amc_records():
    return _fetch_df("SELECT * FROM amc_records ORDER BY report_period DESC")
