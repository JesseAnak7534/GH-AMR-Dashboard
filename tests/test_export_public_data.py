"""
Tests for the public export.

The export is the boundary: everything that crosses it becomes a file on a
public web server, and nothing downstream can take it back. So the tests here
are about what is allowed to cross, not about whether the numbers are right --
the numbers come from the analysis layer, which has its own tests.

The database is not touched. These exercise the serialisation and the shape of
what is written, which is where an export quietly goes wrong.
"""

import json
import math

import pandas as pd
import pytest

from scripts.export_public_data import _clean, _rows, _suppress
from src import disclosure


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def test_nan_becomes_null_not_the_literal_nan():
    """``json.dumps`` writes NaN as the bare token ``NaN``, which is not JSON.

    One missing confidence interval would make ``JSON.parse`` throw and take a
    whole page down with it, so the export refuses to emit it.
    """
    assert _clean(float("nan")) is None
    assert _clean(float("inf")) is None
    assert json.dumps({"x": _clean(float("nan"))}, allow_nan=False) == '{"x": null}'


def test_numpy_scalars_survive():
    import numpy as np
    assert _clean(np.int64(7)) == 7
    assert _clean(np.float64(1.5)) == 1.5
    assert _clean(np.bool_(True)) is True


def test_timestamps_become_iso_strings():
    value = _clean(pd.Timestamp("2026-03-02T10:00:00Z"))
    assert isinstance(value, str)
    assert value.startswith("2026-03-02")


def test_missing_timestamp_is_null():
    assert _clean(pd.NaT) is None


def test_rows_are_json_serialisable():
    frame = pd.DataFrame({
        "organism": ["Escherichia coli", "Klebsiella pneumoniae"],
        "tested": [40, 2],
        "percent": [91.5, float("nan")],
        "when": pd.to_datetime(["2026-01-01", None]),
    })
    payload = _rows(frame)
    json.dumps(payload, allow_nan=False)        # must not raise
    assert payload[1]["percent"] is None
    assert payload[1]["when"] is None


def test_rows_of_an_empty_frame_is_an_empty_list():
    assert _rows(pd.DataFrame()) == []
    assert _rows(None) == []


# ---------------------------------------------------------------------------
# What is allowed to cross the boundary
# ---------------------------------------------------------------------------

def test_suppression_runs_before_anything_is_written():
    frame = pd.DataFrame({"ward": ["A", "B", "C"], "isolates": [40, 2, 900]})
    shown, report = _suppress(frame, ["isolates"], disclosure.MIN_PUBLIC_CELL)
    assert report["withheld"] >= 1
    assert disclosure.WITHHELD in set(shown["isolates"])
    assert 2 not in set(shown["isolates"])


def test_suppression_report_carries_its_own_explanation():
    """A suppressed table published without a note invites the reader to read
    the gaps as zero."""
    frame = pd.DataFrame({"ward": ["A", "B"], "isolates": [40, 1]})
    _, report = _suppress(frame, ["isolates"], disclosure.MIN_PUBLIC_CELL)
    assert report["summary"]
    assert "withheld" in report["summary"].lower()
    assert report["threshold"] == disclosure.MIN_PUBLIC_CELL


def test_a_rate_over_a_withheld_count_goes_with_it():
    """Publishing the percentage would give the suppressed denominator away."""
    frame = pd.DataFrame({"ward": ["A", "B"], "isolates": [40, 2],
                          "percent": [50.0, 100.0]})
    shown, _ = _suppress(frame, ["isolates"], disclosure.MIN_PUBLIC_CELL,
                         blank=["percent"])
    withheld_row = shown[shown["isolates"] == disclosure.WITHHELD]
    assert withheld_row["percent"].isna().all()


@pytest.mark.parametrize("column", sorted(disclosure.RECORD_ID_COLUMNS))
def test_record_identifiers_are_recognised(column):
    """The export relies on this set to know what must never be published, so
    a column added to the schema later is caught by the same test."""
    frame = pd.DataFrame({column: ["x"], "isolates": [40]})
    assert disclosure.is_record_level(frame), column
