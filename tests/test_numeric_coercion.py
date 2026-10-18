"""A blank numeric cell must reach the database as NULL.

Pandas turns a column with one blank into float64 NaN throughout, and a NaN
handed to the database is destructive in two different ways depending on the
column type. Against `amu_records.patient_days`, an integer column, PostgreSQL
raises "integer out of range" -- a message about a range problem that does not
exist -- and rejects the whole batch, so one facility omitting one field loses
every record in the upload. That is exactly what happened to a 1,780-record AMU
load. Against a double precision column it is worse: the NaN is accepted, and
every sum, mean and pooled rate computed over that column afterwards is NaN.

Missing is NULL. The consumption module's denominator_coverage() exists to
count what was not reported, and it cannot count what never arrived.
"""

import numpy as np
import pandas as pd

from src.db import _num


def test_nan_becomes_none():
    assert _num(float("nan")) is None
    assert _num(np.nan) is None
    assert _num(pd.NA) is None
    assert _num(None) is None


def test_infinities_become_none():
    assert _num(float("inf")) is None
    assert _num(float("-inf")) is None


def test_blank_and_unparseable_strings_become_none():
    assert _num("") is None
    assert _num("   ") is None
    assert _num("not a number") is None


def test_real_values_survive_unchanged():
    assert _num(0) == 0
    assert _num(43320) == 43320
    assert _num(0.25) == 0.25
    assert _num(-5) == -5
    assert _num("1234") == 1234.0


def test_a_pandas_column_with_one_blank_still_yields_numbers():
    """The realistic shape: one missing cell makes the whole column float."""
    frame = pd.DataFrame({"patient_days": [38000, None, 21000]})
    coerced = [_num(v) for v in frame["patient_days"]]
    assert coerced[1] is None
    assert coerced[0] == 38000
    assert coerced[2] == 21000
    # and nothing that survives is a NaN that would poison an aggregate
    assert all(v == v for v in coerced if v is not None)
