"""Emptiness detection.

``is_blank`` decides, for every cell of every sheet, whether the author wrote
anything. It is the most-called function in the upload path -- roughly 1.5
million calls for a 2,500-specimen workbook -- so it was rewritten with type
fast paths and pandas hoisted out of the call. These tests pin the behaviour
that rewrite had to preserve, because getting it wrong in either direction is
silently destructive: treat a real value as blank and data vanishes; treat a
blank as real and "nan" is stored as though someone typed it.
"""

import numpy as np
import pandas as pd
import pytest

from src.upload_schema import NULL_TOKENS, clean_text, is_blank


@pytest.mark.parametrize("value", [
    None, float("nan"), np.nan, pd.NA, pd.NaT, np.float64("nan"),
    "", "   ", "\t\n",
])
def test_missing_values_are_blank(value):
    assert is_blank(value) is True


@pytest.mark.parametrize("text", ["nan", "NaN", "NAN", "none", "None", "null",
                                  "NULL", "na", "NA", "n/a", "N/A", "#N/A", "-"])
def test_spelled_out_emptiness_is_blank(text):
    """A NaN through str() leaves the literal 'nan'; storing that as a value is
    how 'Unknown' and 'nan' end up in a database column."""
    assert is_blank(text) is True
    assert is_blank(f"  {text}  ") is True, "surrounding space must not matter"


@pytest.mark.parametrize("value", [
    "Escherichia coli", "Blood", "0", "false", "S", "-1",
    0, 1, -5, 0.0, 1.5, -2.5, True, False,
    np.float64(2.5), np.int64(7), np.bool_(True),
    float("inf"), float("-inf"),
])
def test_real_values_are_not_blank(value):
    assert is_blank(value) is False


def test_zero_is_a_value_not_a_blank():
    """A zero count, a zero zone diameter and a 0.0 MIC are measurements."""
    assert is_blank(0) is False
    assert is_blank(0.0) is False
    assert is_blank("0") is False
    assert clean_text(0) == "0"


def test_false_is_a_value_not_a_blank():
    assert is_blank(False) is False


def test_every_null_token_is_treated_as_blank():
    """The declared vocabulary and the behaviour cannot drift apart."""
    for token in NULL_TOKENS:
        assert is_blank(token) is True, f"{token!r} is declared null"


def test_matches_the_reference_implementation():
    """The pre-optimisation route, kept here as the definition of correct."""
    def reference(value):
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass
        return str(value).strip().lower() in NULL_TOKENS

    cases = [None, float("nan"), np.nan, pd.NA, pd.NaT, "", "   ", "nan",
             "NaN", "None", "NULL", "na", "N/A", "#N/A", "-",
             "Escherichia coli", 0, 1, -5, 0.0, 1.5, float("inf"),
             float("-inf"), True, False, np.float64("nan"), np.float64(2.5),
             np.int64(7), np.bool_(True), "Blood", "0", "false",
             pd.Timestamp("2026-01-01"), [], {}, (1,)]
    for value in cases:
        assert is_blank(value) == reference(value), f"diverged on {value!r}"
