"""
Database module for AMR Surveillance Dashboard.
Handles SQLite schema creation and CRUD operations.
"""
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import pandas as pd


DB_DIR = "db"
DB_PATH = os.path.join(DB_DIR, "amr_data.db")


def ensure_db_dir():
    """Create db directory if it doesn't exist."""
    os.makedirs(DB_DIR, exist_ok=True)


def get_connection():
    """Get SQLite connection."""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            is_active BOOLEAN DEFAULT 1,
            is_admin BOOLEAN DEFAULT 0
        )
    """)

    # Add email verification columns if they don't exist (migration)
    user_migrations = [
        ("is_verified", "BOOLEAN DEFAULT 0"),
        ("verification_code", "TEXT"),
        ("verification_expires", "TEXT")
    ]
    for col_name, col_type in user_migrations:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Create datasets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id TEXT PRIMARY KEY,
            dataset_name TEXT NOT NULL,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL,
            rows_samples INTEGER,
            rows_tests INTEGER
        )
    """)

    # Add country and is_country_main columns if they don't exist
    migration_cols = [
        ("country", "TEXT"),
        ("is_country_main", "BOOLEAN DEFAULT 0")
    ]
    for col_name, col_type in migration_cols:
        try:
            cursor.execute(f"ALTER TABLE datasets ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Create samples table
    cursor.execute("""
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
            latitude REAL,
            longitude REAL,
            PRIMARY KEY (dataset_id, sample_id),
            FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
        )
    """)
    
    # Add lab_name column if it doesn't exist (migration)
    try:
        cursor.execute("ALTER TABLE samples ADD COLUMN lab_name TEXT")
    except sqlite3.OperationalError:
        pass

    # Create ast_results table
    cursor.execute("""
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
            mic_value REAL,
            zone_diameter REAL,
            auto_interpreted BOOLEAN DEFAULT FALSE,
            interpreted_result TEXT,
            interpretation_guideline TEXT,
            interpretation_confidence TEXT,
            suspected_mechanism TEXT,
            interpretation_notes TEXT,
            PRIMARY KEY (dataset_id, isolate_id, antibiotic),
            FOREIGN KEY (dataset_id, sample_id) REFERENCES samples(dataset_id, sample_id)
        )
    """)

    # Add zone_diameter column if it doesn't exist (for database migration)
    try:
        cursor.execute("ALTER TABLE ast_results ADD COLUMN zone_diameter REAL")
    except sqlite3.OperationalError:
        # Column already exists
        pass

    # Add interpretation columns if they don't exist (for database migration)
    interpretation_columns = [
        ("auto_interpreted", "BOOLEAN DEFAULT FALSE"),
        ("interpreted_result", "TEXT"),
        ("interpretation_guideline", "TEXT"),
        ("interpretation_confidence", "TEXT"),
        ("suspected_mechanism", "TEXT"),
        ("interpretation_notes", "TEXT")
    ]

    for col_name, col_type in interpretation_columns:
        try:
            cursor.execute(f"ALTER TABLE ast_results ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            # Column already exists
            pass

    # Create predictions table (future-proofing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            dataset_id TEXT,
            location_level TEXT,
            location_name TEXT,
            organism TEXT,
            antibiotic TEXT,
            predicted_risk REAL,
            confidence REAL,
            model_version TEXT,
            run_date TEXT,
            PRIMARY KEY (dataset_id, location_level, location_name, organism, antibiotic),
            FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
        )
    """)

    # Create alerts table for tracking generated alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            organism TEXT,
            antibiotic TEXT,
            lab_name TEXT,
            region TEXT,
            resistance_rate REAL,
            threshold REAL,
            affected_count INTEGER,
            detected_at TEXT NOT NULL,
            is_acknowledged INTEGER DEFAULT 0,
            acknowledged_by TEXT,
            acknowledged_at TEXT,
            notes TEXT,
            dataset_id TEXT,
            FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
        )
    """)

    # Create alert_subscriptions table for user preferences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            alert_type TEXT,
            severity_threshold TEXT DEFAULT 'MEDIUM',
            email_enabled INTEGER DEFAULT 1,
            sms_enabled INTEGER DEFAULT 0,
            lab_filter TEXT,
            organism_filter TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Create scheduled_reports table for report scheduling
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # Create report_history table for tracking report execution
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER,
            report_type TEXT,
            run_time TEXT NOT NULL,
            status TEXT NOT NULL,
            recipients TEXT,
            error_message TEXT,
            file_path TEXT,
            FOREIGN KEY (schedule_id) REFERENCES scheduled_reports(id)
        )
    """)

    # ── PPS (Point Prevalence Survey) tables ──
    cursor.execute("""
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pps_prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id TEXT NOT NULL,
            ward TEXT,
            patient_age_group TEXT,
            antibiotic_name TEXT NOT NULL,
            route TEXT,
            indication TEXT,
            indication_documented INTEGER DEFAULT 0,
            guideline_compliant INTEGER DEFAULT 0,
            duration_days REAL,
            FOREIGN KEY (survey_id) REFERENCES pps_surveys(survey_id)
        )
    """)

    # ── AMU (Antimicrobial Use) tables ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS amu_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_name TEXT NOT NULL,
            report_period TEXT NOT NULL,
            region TEXT,
            district TEXT,
            sector TEXT DEFAULT 'HUMAN',
            antibiotic_name TEXT NOT NULL,
            atc_code TEXT,
            formulation TEXT,
            unit_of_measure TEXT,
            quantity_dispensed REAL,
            ddd_per_1000 REAL,
            patient_days INTEGER,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL
        )
    """)

    # ── AMC (Antimicrobial Consumption) tables ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS amc_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_period TEXT NOT NULL,
            region TEXT,
            sector TEXT NOT NULL DEFAULT 'ANIMAL',
            species TEXT,
            production_type TEXT,
            antibiotic_class TEXT NOT NULL,
            antibiotic_name TEXT,
            atc_vet_code TEXT,
            quantity_kg REAL,
            biomass_kg REAL,
            mg_per_kg_biomass REAL,
            route TEXT,
            purpose TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_dataset(dataset_id: str, dataset_name: str, samples_df: pd.DataFrame, 
                 ast_df: pd.DataFrame, uploaded_by: str = "System"):
    """Save dataset and related data to database."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Save dataset metadata
        cursor.execute("""
            INSERT INTO datasets (dataset_id, dataset_name, uploaded_by, uploaded_at, rows_samples, rows_tests)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (dataset_id, dataset_name, uploaded_by, datetime.now().isoformat(), len(samples_df), len(ast_df)))

        # Save samples
        for _, row in samples_df.iterrows():
            cursor.execute("""
                INSERT INTO samples 
                (dataset_id, sample_id, lab_name, collection_date, region, district, site_type, 
                 source_category, source_type, food_matrix, environment_matrix, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dataset_id,
                row.get('sample_id'),
                row.get('lab_name'),
                row.get('collection_date'),
                row.get('region'),
                row.get('district'),
                row.get('site_type'),
                row.get('source_category'),
                row.get('source_type'),
                row.get('food_matrix'),
                row.get('environment_matrix'),
                row.get('latitude'),
                row.get('longitude')
            ))

        # Save AST results
        for _, row in ast_df.iterrows():
            cursor.execute("""
                INSERT INTO ast_results
                (dataset_id, sample_id, isolate_id, organism, antibiotic, result, method, guideline, test_date, mic_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dataset_id,
                row.get('sample_id'),
                row.get('isolate_id'),
                row.get('organism'),
                row.get('antibiotic'),
                row.get('result'),
                row.get('method'),
                row.get('guideline'),
                row.get('test_date'),
                row.get('mic_value')
            ))

        conn.commit()
        return True, "Data saved successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Database error: {str(e)}"
    finally:
        conn.close()


def get_all_datasets() -> List[Dict]:
    """Get all datasets."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets ORDER BY uploaded_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def set_dataset_main(dataset_id: str, is_main: bool = True, country: Optional[str] = None) -> Tuple[bool, str]:
    """Mark a dataset as the main country dataset and optionally set country."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if is_main and country:
            cursor.execute(
                "UPDATE datasets SET is_country_main = 1, country = ? WHERE dataset_id = ?",
                (country, dataset_id)
            )
        else:
            cursor.execute(
                "UPDATE datasets SET is_country_main = ?, country = COALESCE(country, ?) WHERE dataset_id = ?",
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
    """Retrieve all datasets marked as main, optionally filtered by country."""
    conn = get_connection()
    cursor = conn.cursor()
    if country:
        cursor.execute("SELECT * FROM datasets WHERE is_country_main = 1 AND country = ? ORDER BY uploaded_at DESC", (country,))
    else:
        cursor.execute("SELECT * FROM datasets WHERE is_country_main = 1 ORDER BY uploaded_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_datasets_by_uploader(email: str) -> List[Dict]:
    """Retrieve datasets uploaded by a specific email."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasets WHERE uploaded_by = ? ORDER BY uploaded_at DESC", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def merge_dataset_into_main(source_dataset_id: str, main_dataset_id: str) -> Tuple[bool, str]:
    """Physically merge source dataset rows into the main dataset.
    Safeguards: prefix sample_id and isolate_id with source dataset id to avoid key conflicts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        samples_df = get_dataset_samples(source_dataset_id)
        ast_df = get_dataset_ast(source_dataset_id)
        if samples_df.empty and ast_df.empty:
            return False, "Source dataset is empty"

        # Build mapping for sample_id prefixes
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
            cursor.execute(
                """
                INSERT OR REPLACE INTO samples
                (dataset_id, sample_id, lab_name, collection_date, region, district, site_type,
                 source_category, source_type, food_matrix, environment_matrix, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    main_dataset_id,
                    new_sid,
                    row.get('lab_name'),
                    row.get('collection_date'),
                    row.get('region'),
                    row.get('district'),
                    row.get('site_type'),
                    row.get('source_category'),
                    row.get('source_type'),
                    row.get('food_matrix'),
                    row.get('environment_matrix'),
                    row.get('latitude'),
                    row.get('longitude')
                )
            )

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
            cursor.execute(
                """
                INSERT OR REPLACE INTO ast_results
                (dataset_id, sample_id, isolate_id, organism, antibiotic, result, method, guideline, test_date, mic_value,
                 zone_diameter, auto_interpreted, interpreted_result, interpretation_guideline, interpretation_confidence,
                 suspected_mechanism, interpretation_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    main_dataset_id,
                    new_sid,
                    new_isolate,
                    row.get('organism'),
                    row.get('antibiotic'),
                    row.get('result'),
                    row.get('method'),
                    row.get('guideline'),
                    row.get('test_date'),
                    row.get('mic_value'),
                    row.get('zone_diameter'),
                    row.get('auto_interpreted'),
                    row.get('interpreted_result'),
                    row.get('interpretation_guideline'),
                    row.get('interpretation_confidence'),
                    row.get('suspected_mechanism'),
                    row.get('interpretation_notes')
                )
            )

        added_tests = len(ast_df)

        cursor.execute("UPDATE datasets SET rows_samples = COALESCE(rows_samples,0) + ?, rows_tests = COALESCE(rows_tests,0) + ? WHERE dataset_id = ?",
                       (added_samples, added_tests, main_dataset_id))

        conn.commit()
        return True, f"Merged {added_samples} samples and {added_tests} tests into main dataset"
    except Exception as e:
        conn.rollback()
        return False, f"Error during merge: {str(e)}"
    finally:
        conn.close()


def get_dataset_samples(dataset_id: str) -> pd.DataFrame:
    """Get samples for a dataset."""
    return pd.read_sql_query(
        "SELECT * FROM samples WHERE dataset_id = ?",
        get_connection(),
        params=(dataset_id,)
    )


def get_dataset_ast(dataset_id: str) -> pd.DataFrame:
    """Get AST results for a dataset."""
    return pd.read_sql_query(
        "SELECT * FROM ast_results WHERE dataset_id = ?",
        get_connection(),
        params=(dataset_id,)
    )


def get_all_ast_results() -> pd.DataFrame:
    """Get all AST results from all datasets."""
    return pd.read_sql_query(
        "SELECT * FROM ast_results",
        get_connection()
    )


def get_all_samples() -> pd.DataFrame:
    """Get all samples from all datasets."""
    return pd.read_sql_query(
        "SELECT * FROM samples",
        get_connection()
    )


def get_resistance_stats(dataset_id: Optional[str] = None) -> pd.DataFrame:
    """Get resistance statistics."""
    query = """
        SELECT 
            organism,
            antibiotic,
            result,
            COUNT(*) as count
        FROM ast_results
    """
    params = []
    if dataset_id:
        query += " WHERE dataset_id = ?"
        params.append(dataset_id)
    query += " GROUP BY organism, antibiotic, result"

    return pd.read_sql_query(
        query,
        get_connection(),
        params=params if params else None
    )


def delete_dataset(dataset_id: str) -> Tuple[bool, str]:
    """Delete a dataset and all associated data."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ast_results WHERE dataset_id = ?", (dataset_id,))
        cursor.execute("DELETE FROM samples WHERE dataset_id = ?", (dataset_id,))
        cursor.execute("DELETE FROM datasets WHERE dataset_id = ?", (dataset_id,))
        conn.commit()
        return True, "Dataset deleted successfully"
    except Exception as e:
        conn.rollback()
        return False, f"Error deleting dataset: {str(e)}"
    finally:
        conn.close()


# ============================================================================
# USER AUTHENTICATION FUNCTIONS
# ============================================================================

def create_user(email: str, password_hash: str, is_admin: bool = False) -> Tuple[bool, str]:
    """Create a new user account."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (email, password_hash, created_at, is_active, is_admin, is_verified)
            VALUES (?, ?, ?, 1, ?, 1)
        """, (email, password_hash, datetime.now().isoformat(), 1 if is_admin else 0))
        conn.commit()
        return True, "User created successfully"
    except sqlite3.IntegrityError:
        return False, "Email already registered"
    except Exception as e:
        return False, f"Error creating user: {str(e)}"
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user by email."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> List[Dict]:
    """Get all users for admin panel."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, email, created_at, last_login, is_active, is_admin 
        FROM users 
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_last_login(email: str) -> bool:
    """Update user's last login timestamp."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE email = ?",
            (datetime.now().isoformat(), email)
        )
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()


def update_user_status(user_id: int, is_active: bool) -> Tuple[bool, str]:
    """Activate or deactivate a user account."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?",
            (1 if is_active else 0, user_id)
        )
        conn.commit()
        status = "activated" if is_active else "deactivated"
        return True, f"User {status} successfully"
    except Exception as e:
        return False, f"Error updating user: {str(e)}"
    finally:
        conn.close()


def update_user_password(email: str, new_password_hash: str) -> Tuple[bool, str]:
    """Update user's password hash."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (new_password_hash, email)
        )
        conn.commit()
        return True, "Password updated successfully"
    except Exception as e:
        return False, f"Error updating password: {str(e)}"
    finally:
        conn.close()


def set_verification_code(email: str, code: str, expires_at: str) -> Tuple[bool, str]:
    """Set a verification code and expiry for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET verification_code = ?, verification_expires = ? WHERE email = ?",
            (code, expires_at, email)
        )
        conn.commit()
        return True, "Verification code set"
    except Exception as e:
        return False, f"Error setting verification code: {str(e)}"
    finally:
        conn.close()


def verify_user_email(email: str, code: str) -> Tuple[bool, str]:
    """Verify user email if code matches and not expired."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT verification_code, verification_expires FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if not row:
            return False, "User not found"
        saved_code = row[0]
        expires = row[1]
        if not saved_code:
            return False, "No verification code set"
        if str(saved_code) != str(code):
            return False, "Invalid verification code"
        # Expiry check
        try:
            if expires and datetime.fromisoformat(expires) < datetime.now():
                return False, "Verification code expired"
        except Exception:
            pass
        cursor.execute(
            "UPDATE users SET is_verified = 1, verification_code = NULL, verification_expires = NULL WHERE email = ?",
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
    """Force set a user's verified flag (used for admin bootstrap)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_verified = ? WHERE email = ?",
            (1 if is_verified else 0, email)
        )
        conn.commit()
        return True, "User verification flag updated"
    except Exception as e:
        return False, f"Error updating verification flag: {str(e)}"
    finally:
        conn.close()


def delete_user(user_id: int) -> Tuple[bool, str]:
    """Delete a user account."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        return True, "User deleted successfully"
    except Exception as e:
        return False, f"Error deleting user: {str(e)}"
    finally:
        conn.close()


def set_user_admin(email: str, is_admin: bool) -> Tuple[bool, str]:
    """Update user's admin flag by email."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_admin = ? WHERE email = ?",
            (1 if is_admin else 0, email)
        )
        conn.commit()
        status = "granted" if is_admin else "revoked"
        return True, f"Admin privileges {status}"
    except Exception as e:
        return False, f"Error updating admin flag: {str(e)}"
    finally:
        conn.close()


def delete_non_admin_users(admin_email: Optional[str] = None) -> Tuple[int, str]:
    """Delete all users except the admin(s).
    If admin_email is provided, keep only that email and delete all others.
    Otherwise, delete users where is_admin = 0 and keep admins.
    Returns (deleted_count, message).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if admin_email:
            cursor.execute("DELETE FROM users WHERE email <> ?", (admin_email,))
        else:
            cursor.execute("DELETE FROM users WHERE IFNULL(is_admin, 0) = 0")
        deleted = cursor.rowcount or 0
        conn.commit()
        return deleted, f"Deleted {deleted} non-admin user(s)"
    except Exception as e:
        conn.rollback()
        return 0, f"Error deleting non-admin users: {str(e)}"
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════════════════
# PPS CRUD
# ════════════════════════════════════════════════════════════════════════════

def save_pps_survey(survey_id, facility_name, survey_date, region, district,
                    total_patients, patients_on_antibiotics,
                    prescriptions_df, uploaded_by="System"):
    """Save a PPS survey and its prescription rows."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO pps_surveys
            (survey_id, facility_name, survey_date, region, district,
             total_patients, patients_on_antibiotics, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (survey_id, facility_name, survey_date, region, district,
              total_patients, patients_on_antibiotics, uploaded_by,
              datetime.now().isoformat()))

        for _, row in prescriptions_df.iterrows():
            cursor.execute("""
                INSERT INTO pps_prescriptions
                (survey_id, ward, patient_age_group, antibiotic_name,
                 route, indication, indication_documented,
                 guideline_compliant, duration_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM pps_surveys ORDER BY survey_date DESC", conn)
    conn.close()
    return df


def get_pps_prescriptions(survey_id=None):
    conn = get_connection()
    if survey_id:
        df = pd.read_sql_query(
            "SELECT * FROM pps_prescriptions WHERE survey_id = ?", conn, params=(survey_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM pps_prescriptions", conn)
    conn.close()
    return df


# ════════════════════════════════════════════════════════════════════════════
# AMU CRUD
# ════════════════════════════════════════════════════════════════════════════

def save_amu_records(records_df, uploaded_by="System"):
    """Bulk insert AMU records from a DataFrame."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        for _, row in records_df.iterrows():
            cursor.execute("""
                INSERT INTO amu_records
                (facility_name, report_period, region, district, sector,
                 antibiotic_name, atc_code, formulation, unit_of_measure,
                 quantity_dispensed, ddd_per_1000, patient_days,
                 uploaded_by, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM amu_records ORDER BY report_period DESC", conn)
    conn.close()
    return df


# ════════════════════════════════════════════════════════════════════════════
# AMC CRUD
# ════════════════════════════════════════════════════════════════════════════

def save_amc_records(records_df, uploaded_by="System"):
    """Bulk insert AMC records from a DataFrame."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        for _, row in records_df.iterrows():
            cursor.execute("""
                INSERT INTO amc_records
                (report_period, region, sector, species, production_type,
                 antibiotic_class, antibiotic_name, atc_vet_code,
                 quantity_kg, biomass_kg, mg_per_kg_biomass,
                 route, purpose, uploaded_by, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM amc_records ORDER BY report_period DESC", conn)
    conn.close()
    return df
