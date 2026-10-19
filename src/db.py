"""
Database module for the ICBB-AMRSS surveillance platform.

PostgreSQL only. A configured, reachable ``DATABASE_URL`` is required and the
module refuses to import without one.

The platform previously fell back to a local SQLite file when Postgres was
unreachable. That was removed: a silent fallback meant the application could
come up pointing at a stale local snapshot while appearing healthy, and every
statement had to be written to the lowest common denominator of two dialects,
which ruled out foreign keys, CHECK constraints, JSONB and real timestamps.
Failing loudly on a bad connection is safer than serving stale surveillance
data, and a single dialect lets the schema enforce its own integrity.

SQL is plain Postgres: ``%s`` placeholders, ``ON CONFLICT … DO UPDATE``,
``RETURNING``.
"""
import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import pandas as pd
import psycopg2
import psycopg2.extras

# Populate env vars from .env before DATABASE_URL is read. Safe no-op when
# dotenv is absent or there is no .env file.
# Importing src.settings loads .env from the project root. A bare
# load_dotenv() searches upward from the working directory instead, so
# launching from anywhere else left every value in .env invisible.
from src import settings as _settings  # noqa: F401


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection settings
# ---------------------------------------------------------------------------

_PG_DSN: str = ""


def _redact(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def _read_database_url() -> Optional[str]:
    """Pick DATABASE_URL from the environment or Streamlit secrets."""
    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        return url.strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
            val = str(st.secrets["DATABASE_URL"]).strip()
            return val or None
    except Exception:
        pass
    return None


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


def _is_local_host(url: str) -> bool:
    try:
        from urllib.parse import urlsplit
        return (urlsplit(url).hostname or "").lower() in _LOCAL_HOSTS
    except Exception:
        return False


def _normalise_dsn(url: str) -> str:
    """Add the connection parameters a managed Postgres needs.

    Hosted providers (Neon, Supabase, Railway, RDS…) require TLS and will
    refuse or silently downgrade a plaintext connection. A local development
    server usually has no certificate, so TLS is only forced off-box.

    ``application_name`` makes this app identifiable in pg_stat_activity,
    which matters when several services share one database.
    """
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))

    if not _is_local_host(url):
        params.setdefault("sslmode", "require")
    params.setdefault("application_name", "icbb-amrss")

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment)
    )


def _resolve_dsn() -> None:
    """Validate the DSN at import time. A missing or malformed URL is fatal."""
    global _PG_DSN

    url = _read_database_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. The platform requires PostgreSQL; "
            "set DATABASE_URL in the environment, in .env, or in Streamlit "
            "secrets before starting the application."
        )
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            f"DATABASE_URL must be a PostgreSQL DSN, got {_redact(url)!r}."
        )
    _PG_DSN = _normalise_dsn(url)
    logger.info(
        "database: PostgreSQL at %s (%s)",
        _redact(_PG_DSN),
        "local" if _is_local_host(url) else "managed/remote, TLS required",
    )


_resolve_dsn()


def is_postgres() -> bool:
    """Retained for call sites that branch on backend. Always True."""
    return True


# ---------------------------------------------------------------------------
# Connection wrappers
# ---------------------------------------------------------------------------

class _CursorProxy:
    """Thin wrapper over psycopg2's DictCursor."""
    def __init__(self, raw): self._raw = raw
    def execute(self, sql, params=None):
        # psycopg2 skips placeholder interpolation only when vars is None. An
        # empty tuple still triggers it, so SQL holding a literal % -- a LIKE
        # pattern, a to_char format -- would fail with "tuple index out of
        # range" purely because it was called without parameters.
        self._raw.execute(sql, params if params else None)
        return self
    def executemany(self, sql, seq_of_params):
        self._raw.executemany(sql, seq_of_params)
        return self
    def fetchone(self): return self._raw.fetchone()
    def fetchall(self): return self._raw.fetchall()
    def fetchmany(self, size=None): return self._raw.fetchmany(size) if size else self._raw.fetchmany()
    @property
    def raw(self):
        """The underlying psycopg2 cursor.

        Needed by callers that use psycopg2 extras directly -- ``execute_values``
        for batched inserts, in particular, which the proxy does not wrap.
        """
        return self._raw
    @property
    def description(self): return self._raw.description
    @property
    def rowcount(self):    return self._raw.rowcount
    def close(self): self._raw.close()
    def __enter__(self): return self
    def __exit__(self, *exc): self.close()


class _ConnectionWrapper:
    """Connection surface used across the application."""

    def __init__(self, raw):
        self._raw = raw

    def cursor(self, *args, **kwargs):
        kwargs.setdefault("cursor_factory", psycopg2.extras.DictCursor)
        return _CursorProxy(self._raw.cursor(*args, **kwargs))

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):   return self._raw.commit()
    def rollback(self): return self._raw.rollback()
    def close(self):    return self._raw.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, *exc):
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()

    @property
    def raw(self): return self._raw


_TLS_FAILURE_MARKERS = (
    "ssl syscall error",
    "ssl error",
    "server closed the connection unexpectedly",
    "could not create ssl context",
)


def _explain_connection_failure(exc: Exception) -> Exception:
    """Turn a TLS connection failure into an explanation, not a puzzle.

    When a hosted database refuses TLS, psycopg2 reports "server closed the
    connection unexpectedly", which reads like an outage. It is not: the server
    is often reachable, and the obvious next move -- deleting sslmode from the
    connection string -- makes it work by sending the password and every patient
    record across the public internet in clear text.

    So when TLS fails, this probes whether an unencrypted connection *would*
    have succeeded, and if it would, says so explicitly. The platform still
    refuses to connect. The point is that the person reading the error learns
    what the quick fix would actually cost.
    """
    message = str(exc).lower()
    if not any(marker in message for marker in _TLS_FAILURE_MARKERS):
        return exc
    if _is_local_host(_PG_DSN):
        return exc

    plaintext_works = False
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(_PG_DSN)
        params = {k: v for k, v in parse_qsl(parts.query, keep_blank_values=True)
                  if k != "sslmode"}
        params["sslmode"] = "disable"
        probe = urlunsplit((parts.scheme, parts.netloc, parts.path,
                            urlencode(params), parts.fragment))
        test = psycopg2.connect(probe, connect_timeout=8)
        plaintext_works = not getattr(test.info, "ssl_in_use", False)
        test.close()
    except Exception:
        plaintext_works = False

    if not plaintext_works:
        return exc

    logger.error("database refused TLS; refusing to connect unencrypted")
    blank = ""
    return RuntimeError(nl_join([
        "The database refused an encrypted connection.",
        blank,
        "It is reachable, but only without TLS. The platform will not connect "
        "that way, because the password and every patient-derived record would "
        "cross the public internet in clear text.",
        blank,
        "Do not remove sslmode from DATABASE_URL to make this go away. Instead:",
        "  - check whether a firewall or antivirus product has begun inspecting "
        "traffic on the database port; that breaks the PostgreSQL TLS handshake "
        "specifically, while leaving ordinary HTTPS working,",
        "  - try the same connection from another network, which distinguishes a "
        "local cause from a provider one,",
        "  - check the provider's status page.",
        blank,
        f"Underlying error: {exc}",
    ]))


def nl_join(parts) -> str:
    """Join lines without embedding an escape in a source string."""
    return chr(10).join(str(p) for p in parts)


def get_connection() -> _ConnectionWrapper:
    """Open a fresh Postgres connection.

    A finite ``connect_timeout`` plus TCP keepalives mean a network blip or an
    idle hosted database fails fast instead of hanging the UI. Statement and
    idle-transaction timeouts stop a stuck query from locking a table and
    freezing every page load.
    """
    try:
        timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "8"))
    except ValueError:
        timeout = 8

    try:
        raw = psycopg2.connect(
            _PG_DSN,
            connect_timeout=timeout,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
    except psycopg2.OperationalError as exc:
        raise _explain_connection_failure(exc) from exc
    try:
        stmt_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000"))
        idle_tx_ms = int(os.getenv("DB_IDLE_TX_TIMEOUT_MS", "60000"))
        with raw.cursor() as _cfg:
            _cfg.execute(
                f"SET statement_timeout = {stmt_ms}; "
                f"SET idle_in_transaction_session_timeout = {idle_tx_ms};"
            )
        raw.commit()
    except Exception:
        logger.exception("failed to set session timeouts; continuing")
        try:
            raw.rollback()
        except Exception:
            pass
    return _ConnectionWrapper(raw)


def _num(value):
    """A number fit to store, or None.

    Pandas represents a blank numeric cell as NaN, and a column with one blank
    becomes float64 throughout. Passed straight to the database that NaN is
    either rejected or, worse, accepted:

      * into an integer column PostgreSQL raises "integer out of range" -- the
        message names a range problem that is not there, and the whole batch is
        lost because one facility left one field empty;
      * into a double precision column it is stored, and NaN is contagious in
        arithmetic, so every sum, mean and pooled rate computed over that column
        silently becomes NaN afterwards.

    A value nobody recorded is NULL. That is what the consumption module's
    coverage report is built to count, and it cannot count what never arrived.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):          # not a scalar pandas understands
        pass
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return value


def _fetch_df(sql: str, params=None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Stays off pandas's connection-
    detection path, which insists on SQLAlchemy engines for non-sqlite."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        cur.close()
        return pd.DataFrame([dict(r) for r in rows], columns=cols)
    finally:
        conn.close()


def _safe_add_column(cur, table: str, column: str, ddl: str):
    """Idempotent column add."""
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
    except Exception:
        logger.exception("ADD COLUMN %s.%s failed", table, column)


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

#: Tables that only exist once the schema has been created. If every one of
#: them is present, the ``CREATE TABLE IF NOT EXISTS`` run would do nothing but
#: cost round trips, so it is skipped.
_SCHEMA_SENTINELS = (
    "users", "datasets", "samples", "ast_results",
    "subjects", "specimens", "isolates", "phenotypes",
    "amu_records", "amc_records", "pps_surveys", "pps_prescriptions",
)


def schema_exists(conn=None) -> bool:
    """Whether the schema has already been created.

    One query against ``to_regclass`` rather than sixty-nine DDL statements:
    0.09 seconds instead of 3.4 against a hosted database. The DDL is
    idempotent, so running it was harmless -- it was simply the largest single
    cost in starting the application, paid on every cold start, during which
    the browser shows nothing at all.
    """
    own = conn is None
    conn = conn or get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM unnest(%s::text[]) AS t(name) "
            "WHERE to_regclass('public.' || quote_ident(t.name)) IS NOT NULL",
            (list(_SCHEMA_SENTINELS),))
        row = cur.fetchone()
        found = int(row[0] if not isinstance(row, dict) else list(row.values())[0])
        return found == len(_SCHEMA_SENTINELS)
    except Exception:                                 # noqa: BLE001
        # A probe that cannot run is not evidence the schema is there.
        logger.exception("schema probe failed; running the full migration")
        return False
    finally:
        if own:
            try:
                conn.close()
            except Exception:                         # noqa: BLE001
                pass


def init_database(force: bool = False):
    """Initialize database schema (idempotent).

    Skips the whole run when every expected table is already present, unless
    ``force`` is set or ``AMRSS_FORCE_MIGRATE`` is in the environment -- which
    is what to use after changing any of the DDL below, since a schema that
    exists but is out of date passes the probe.
    """
    if not force and not os.environ.get("AMRSS_FORCE_MIGRATE"):
        probe = get_connection()
        try:
            if schema_exists(probe):
                logger.info("schema already present; skipping migration")
                return
        finally:
            try:
                probe.close()
            except Exception:                         # noqa: BLE001
                pass

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

    # ---- traceability model ------------------------------------------------
    # subject -> encounter -> specimen -> isolate -> phenotype / genomic result,
    # plus the append-only custody log. Defined in src/traceability.py.
    from src.traceability import init_traceability_schema
    init_traceability_schema(cur)

    # ---- signals and the response lifecycle --------------------------------
    # Detected signal, its provenance, and the append-only log of who reviewed,
    # assigned, actioned and closed it. Defined in src/signals.py.
    from src.signals import init_signal_schema
    init_signal_schema(cur)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Dataset + AST CRUD
# ---------------------------------------------------------------------------

# save_dataset was removed here. It inserted a ``samples`` row and an
# ``ast_results`` row and nothing else, so anything written through it had no
# subject, encounter, specimen or isolate behind it and could not be traced to a
# ward or a patient. It also silently dropped zone_diameter and every
# interpretation column that validation had just produced.
#
# ``src.ingest.ingest_validated_upload`` replaces it: one transaction that
# writes the whole chain plus the legacy wide tables. Every write path in the
# application goes through it.

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
        # The traceability chain cascades from `subjects` through foreign keys,
        # so deleting subjects removes encounters, specimens, isolates,
        # phenotypes and genomic results with it.
        #
        # custody_events and sequencing_runs are deleted explicitly: the audit
        # log deliberately carries no foreign key (it must outlive the rows it
        # describes), and a sequencing run is shared across isolates rather
        # than owned by one.
        cur.execute("DELETE FROM custody_events WHERE dataset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM subjects WHERE dataset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM sequencing_runs WHERE dataset_id = %s", (dataset_id,))
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
    except psycopg2.IntegrityError:
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

#: Written once per row in each batched save below. Kept as module constants so
#: the column list and the tuple built for it cannot drift apart.
_PPS_RX_COLUMNS = (
    "survey_id", "ward", "patient_age_group", "antibiotic_name", "route",
    "indication", "indication_documented", "guideline_compliant",
    "duration_days",
)

_AMU_COLUMNS = (
    "facility_name", "report_period", "region", "district", "sector",
    "antibiotic_name", "atc_code", "formulation", "unit_of_measure",
    "quantity_dispensed", "ddd_per_1000", "patient_days",
    "uploaded_by", "uploaded_at",
)

_AMC_COLUMNS = (
    "report_period", "region", "sector", "species", "production_type",
    "antibiotic_class", "antibiotic_name", "atc_vet_code",
    "quantity_kg", "biomass_kg", "mg_per_kg_biomass",
    "route", "purpose", "uploaded_by", "uploaded_at",
)


def _flag(value) -> int:
    """A yes/no cell as 0 or 1."""
    return 1 if str(value).strip().lower() in ("1", "yes", "true") else 0


def _insert_rows(cur, table: str, columns, rows) -> int:
    """Insert many rows in one statement.

    These three tables were written a row at a time, which is one network round
    trip per record. A 3,000-row consumption upload therefore made 3,000 of them
    with the transaction held open throughout: slow enough to look like a hang
    against a hosted database, and long enough to block other writers. The rows
    are uniform, so they go in one execute_values call.
    """
    if not rows:
        return 0
    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s",
        rows, page_size=500)
    return len(rows)


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

        rows = [
            (survey_id, row.get('ward'), row.get('patient_age_group'),
             row.get('antibiotic_name'), row.get('route'), row.get('indication'),
             _flag(row.get('indication_documented', 0)),
             _flag(row.get('guideline_compliant', 0)),
             _num(row.get('duration_days')))
            for _, row in prescriptions_df.iterrows()
        ]
        _insert_rows(cur.raw, "pps_prescriptions", _PPS_RX_COLUMNS, rows)

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
        rows = [
            (row.get('facility_name'), row.get('report_period'),
             row.get('region'), row.get('district'),
             row.get('sector', 'HUMAN'),
             row.get('antibiotic_name'), row.get('atc_code'),
             row.get('formulation'), row.get('unit_of_measure'),
             _num(row.get('quantity_dispensed')), _num(row.get('ddd_per_1000')),
             _num(row.get('patient_days')), uploaded_by, now)
            for _, row in records_df.iterrows()
        ]
        _insert_rows(cur.raw, "amu_records", _AMU_COLUMNS, rows)
        conn.commit()
        return True, f"{len(rows)} AMU records saved"
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
        rows = [
            (row.get('report_period'), row.get('region'),
             row.get('sector', 'ANIMAL'), row.get('species'),
             row.get('production_type'),
             row.get('antibiotic_class'), row.get('antibiotic_name'),
             row.get('atc_vet_code'),
             _num(row.get('quantity_kg')), _num(row.get('biomass_kg')),
             _num(row.get('mg_per_kg_biomass')),
             row.get('route'), row.get('purpose'), uploaded_by, now)
            for _, row in records_df.iterrows()
        ]
        _insert_rows(cur.raw, "amc_records", _AMC_COLUMNS, rows)
        conn.commit()
        return True, f"{len(rows)} AMC records saved"
    except Exception as e:
        conn.rollback()
        return False, f"AMC save error: {e}"
    finally:
        conn.close()


def get_amc_records():
    return _fetch_df("SELECT * FROM amc_records ORDER BY report_period DESC")
