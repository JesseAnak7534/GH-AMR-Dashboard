"""
Keep-alive utility to prevent system sleep and maintain Streamlit service.
This script can be run as a background service to maintain active status.
"""

import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src import db


def check_database_health():
    """Periodically check database health to ensure it remains accessible."""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM datasets")
        count = cursor.fetchone()[0]
        conn.close()
        return True, count
    except Exception as e:
        return False, str(e)


def keep_alive_loop(interval_seconds=60):
    """
    Main keep-alive loop that runs database health checks.
    
    Args:
        interval_seconds: Interval between health checks (default: 60 seconds)
    """
    print(f"[{datetime.now()}] Keep-alive service started. Checking database health every {interval_seconds} seconds...")
    
    while True:
        try:
            is_healthy, result = check_database_health()
            if is_healthy:
                print(f"[{datetime.now()}] Database health check passed. Datasets in system: {result}")
            else:
                print(f"[{datetime.now()}] WARNING: Database health check failed: {result}")
                # Attempt to reinitialize if there's an issue
                try:
                    db.init_database()
                    print(f"[{datetime.now()}] Database reinitialization attempted")
                except Exception as reinit_error:
                    print(f"[{datetime.now()}] ERROR: Failed to reinitialize database: {reinit_error}")
        except Exception as e:
            print(f"[{datetime.now()}] ERROR in keep-alive loop: {e}")
        
        # Sleep for the specified interval
        time.sleep(interval_seconds)


def prevent_system_sleep():
    """
    Attempt to prevent system sleep on Windows.
    This is a best-effort approach and requires appropriate system permissions.
    """
    import platform
    
    if platform.system() == "Windows":
        try:
            import ctypes
            # ES_SYSTEM_REQUIRED = 0x00000001
            # ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
            print(f"[{datetime.now()}] Windows sleep prevention enabled")
            return True
        except Exception as e:
            print(f"[{datetime.now()}] WARNING: Could not enable Windows sleep prevention: {e}")
            print("         System may enter sleep mode. Consider disabling sleep in Windows settings.")
            return False
    else:
        print(f"[{datetime.now()}] Non-Windows platform detected. Sleep prevention not available.")
        return False


def main():
    """Main entry point for the keep-alive service."""
    print("=" * 70)
    print("AMR Surveillance Dashboard - Keep-Alive Service")
    print("=" * 70)
    print(f"Started at: {datetime.now()}")
    print()
    
    # Initialize database
    try:
        db.init_database()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ ERROR: Failed to initialize database: {e}")
        sys.exit(1)
    
    # Attempt to prevent system sleep (best-effort)
    prevent_system_sleep()
    
    print()
    print("Running keep-alive loop...")
    print("-" * 70)
    print()
    
    try:
        keep_alive_loop(interval_seconds=60)
    except KeyboardInterrupt:
        print()
        print("-" * 70)
        print("Keep-alive service stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
