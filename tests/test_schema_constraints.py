"""Constraints in the schema text itself.

These read the generated DDL rather than a live database, so they run anywhere
and catch a weakened constraint at the point it is written.

The case that prompted them: ``mic_value > 0`` looks like a complete guard and
is not. PostgreSQL orders IEEE NaN above every number, so ``NaN > 0`` is true
and a NaN MIC is stored as though it were a measurement -- after which every
mean, minimum and percentile over that column is NaN. 3,344 such values were
found in the legacy AST table, all on disc-diffusion rows that never had an MIC
to begin with.
"""

import re

from src import traceability as tr


def _schema_sql() -> str:
    """Every CREATE TABLE the module emits, as one blob of SQL."""
    statements = []

    class _Recorder:
        def execute(self, sql, *args, **kwargs):
            statements.append(sql)
        def __getattr__(self, _name):
            return lambda *a, **k: None

    tr.init_traceability_schema(_Recorder())
    return "\n".join(statements)


FLOAT_COLUMN = re.compile(
    r"^\s*(\w+)\s+DOUBLE PRECISION\b(.*?)(?=^\s*\w+\s+(?:TEXT|DOUBLE|BOOLEAN|"
    r"SMALLINT|BIGSERIAL|DATE|TIMESTAMPTZ|JSONB)\b|^\s*(?:PRIMARY|CONSTRAINT|\)))",
    re.S | re.M | re.I)


def test_one_sided_float_checks_also_exclude_nan_and_infinity():
    sql = _schema_sql()
    offenders = []
    for name, body in FLOAT_COLUMN.findall(sql):
        if "CHECK" not in body.upper():
            continue
        # A two-sided range (BETWEEN, or both < and >) rejects NaN on its own,
        # because every comparison against NaN on the upper side is false.
        two_sided = ("BETWEEN" in body.upper()
                     or (("<=" in body or "<" in body)
                         and (">=" in body or ">" in body)))
        if two_sided:
            continue
        if "NaN" not in body:
            offenders.append(name)
    assert not offenders, (
        "these float columns have a one-sided CHECK that NaN and Infinity pass: "
        + ", ".join(offenders) + " -- guard them with _finite()")


def test_finite_helper_rejects_all_three_non_numbers():
    guard = tr._finite("x")
    for value in ("'NaN'", "'Infinity'", "'-Infinity'"):
        assert value in guard, f"{value} is not excluded"
    assert guard.count("x <>") == 3
