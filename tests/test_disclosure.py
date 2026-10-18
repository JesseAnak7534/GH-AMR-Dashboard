"""Disclosure control for anything shown publicly.

The platform already withholds a *rate* below thirty isolates, which is a
statistical rule and deliberately keeps the counts. Published, that is the wrong
way round: the count is the disclosive part. "Neonatal ward, this hospital,
March, two isolates" describes a person, and a pseudonym does nothing about it.

The risk is in the filtering rather than the default view. An interactive page
lets a visitor narrow until a cell holds one person, and each filter is another
attribute attached to them.
"""

import pandas as pd
import pytest

from src.disclosure import (MIN_PUBLIC_CELL, WITHHELD, apply_disclosure_control,
                            safe_to_publish)


def _table():
    return pd.DataFrame({
        "ward": ["ICU", "ICU", "ICU", "Medical", "Medical", "Medical"],
        "organism": ["Ec", "Kp", "Pa", "Ec", "Kp", "Pa"],
        "isolates": [40, 2, 25, 30, 18, 12],
        "percent": [50.0, 100.0, 40.0, 25.0, 33.0, 60.0],
    })


def test_a_small_cell_is_withheld():
    out, report = apply_disclosure_control(_table(), ["isolates"])
    assert out.loc[1, "isolates"] == WITHHELD
    assert report.primary == 1


def test_a_withheld_cell_is_not_shown_as_zero():
    """A reader must be able to tell 'too few to publish' from 'none found'.
    Treating the first as the second is how a suppressed table becomes a
    misleading one."""
    out, _ = apply_disclosure_control(_table(), ["isolates"])
    assert out.loc[1, "isolates"] != 0
    assert out.loc[1, "isolates"] == WITHHELD


def test_the_rate_goes_when_the_count_goes():
    """A percentage over a withheld denominator gives the denominator away as
    surely as printing it."""
    out, _ = apply_disclosure_control(_table(), ["isolates"],
                                      also_blank=["percent"])
    assert pd.isna(out.loc[1, "percent"])


def test_one_withheld_cell_in_a_group_triggers_a_second():
    """Otherwise the value is the total minus the others, and the suppression
    achieved nothing while looking as though it had."""
    out, report = apply_disclosure_control(_table(), ["isolates"],
                                           group_by="ward")
    icu = out[out["ward"] == "ICU"]["isolates"].tolist()
    assert icu.count(WITHHELD) == 2, "a lone suppression is recoverable"
    assert report.secondary == 1


def test_the_second_cell_withheld_is_the_smallest_available():
    """Hiding the largest would cost the reader more information than needed."""
    out, _ = apply_disclosure_control(_table(), ["isolates"], group_by="ward")
    icu = out[out["ward"] == "ICU"].set_index("organism")["isolates"]
    assert icu["Kp"] == WITHHELD          # primary, 2
    assert icu["Pa"] == WITHHELD          # secondary, 25 is smaller than 40
    assert icu["Ec"] == 40


def test_a_group_with_nothing_small_is_untouched():
    out, report = apply_disclosure_control(_table(), ["isolates"],
                                           group_by="ward")
    medical = out[out["ward"] == "Medical"]["isolates"].tolist()
    assert WITHHELD not in medical


def test_zero_stays_visible():
    """Zero describes nobody, and hiding it removes the reader's ability to
    tell 'we looked and found none' from 'we did not look'."""
    frame = pd.DataFrame({"g": ["a", "a"], "isolates": [0, 40]})
    out, report = apply_disclosure_control(frame, ["isolates"], group_by="g")
    assert out.loc[0, "isolates"] == 0
    assert report.withheld == 0


def test_the_report_says_how_much_was_withheld():
    """A table with silent gaps invites the reader to assume zero."""
    _, report = apply_disclosure_control(_table(), ["isolates"], group_by="ward")
    assert "withheld" in report.summary.lower()
    assert "not zero" in report.summary.lower()
    assert str(MIN_PUBLIC_CELL) in report.summary


def test_the_threshold_is_an_argument_not_a_constant():
    """A cell of five in a rare organism at one small facility can still
    identify, so the floor has to be adjustable."""
    out, _ = apply_disclosure_control(_table(), ["isolates"], threshold=20)
    shown = [v for v in out["isolates"] if v != WITHHELD]
    assert all(float(v) >= 20 for v in shown)


def test_an_empty_frame_is_handled():
    out, report = apply_disclosure_control(pd.DataFrame(), ["isolates"])
    assert out.empty and report.withheld == 0


def test_a_missing_column_is_not_an_error():
    out, report = apply_disclosure_control(_table(), ["not_a_column"])
    assert len(out) == len(_table())
    assert report.withheld == 0


def test_a_mostly_withheld_table_is_not_safe_to_publish():
    """A table where almost everything is hidden is an admission the question
    was asked at too fine a grain."""
    sparse = pd.DataFrame({"isolates": [1, 2, 1, 3, 40]})
    assert not safe_to_publish(sparse, "isolates")
    dense = pd.DataFrame({"isolates": [40, 55, 30, 2, 61]})
    assert safe_to_publish(dense, "isolates")


def test_original_frame_is_not_mutated():
    frame = _table()
    apply_disclosure_control(frame, ["isolates"], group_by="ward")
    assert frame.loc[1, "isolates"] == 2, "the caller's frame must be untouched"
