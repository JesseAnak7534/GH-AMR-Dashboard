"""Shared test configuration.

The platform refuses to import ``src.db`` without a reachable PostgreSQL
instance, which is correct for the application and inconvenient for a unit test
that never touches a database. A dummy DSN is set before any import so the pure
logic -- validation, expert rules, MDR classification, consumption arithmetic --
can be tested without one. Tests that genuinely need a database are marked
``integration`` and skipped unless one is configured.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A syntactically valid DSN so src.db imports. Nothing connects to it: the
# modules under test call the database only through functions these tests do not
# exercise.
os.environ.setdefault("DATABASE_URL",
                      "postgresql://unused:unused@localhost:5432/unused")
# Pseudonymisation refuses to run unsalted by design, so the test salt is set
# here rather than each test remembering to.
os.environ.setdefault("AMRSS_PATIENT_SALT", "test-salt-not-for-production")

import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: needs a reachable PostgreSQL database")


@pytest.fixture(scope="session")
def lab_name():
    """An approved laboratory name, since validation rejects unknown ones."""
    from src.lab_management import get_lab_names
    names = get_lab_names()
    return names[0] if names else "Test Laboratory"
