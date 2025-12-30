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

    # Create samples table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            dataset_id TEXT,
            sample_id TEXT,
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
                (dataset_id, sample_id, collection_date, region, district, site_type, 
                 source_category, source_type, food_matrix, environment_matrix, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dataset_id,
                row.get('sample_id'),
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
            INSERT INTO users (email, password_hash, created_at, is_active, is_admin)
            VALUES (?, ?, ?, 1, ?)
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

