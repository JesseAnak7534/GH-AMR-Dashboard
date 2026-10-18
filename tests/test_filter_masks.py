"""Sidebar filters must not exclude everything when they cannot filter.

The Resistance Overview page reported "No data matches the selected filters"
against a dataset of 152 specimens. The filters are combined with AND, and each
was built as ``frame[column].astype(str).isin(selected)``. KoboToolbox
submissions carried no source_type, so that column's option list was empty, its
selection was empty, and ``isin([])`` is false for every row -- one unpopulated
optional column silently emptied the page, and the message blamed the user's
filter choices.
"""

import pandas as pd
import pytest

from src.filters import filter_mask


FRAME = pd.DataFrame({
    "region": ["Ashanti", "Volta", "Ashanti", None],
    "source_type": [None, None, None, None],
    "organism": ["Escherichia coli", "Klebsiella pneumoniae",
                 "Escherichia coli", "Proteus mirabilis"],
})


def test_an_empty_selection_does_not_filter_anything_out():
    """The defect: a column nobody populated must mean 'no constraint'."""
    mask = filter_mask(FRAME, "source_type", [])
    assert mask.all(), "an empty option list must not exclude every row"


def test_a_missing_column_does_not_filter_anything_out():
    mask = filter_mask(FRAME, "not_a_column", ["anything"])
    assert mask.all()


def test_a_narrowed_selection_still_filters():
    mask = filter_mask(FRAME, "region", ["Ashanti"])
    assert list(mask) == [True, False, True, False]


def test_selecting_everything_keeps_rows_with_a_blank():
    """A filter the user has not narrowed should not quietly drop records for
    being blank in a column they never touched."""
    mask = filter_mask(FRAME, "region", ["Ashanti", "Volta"])
    assert mask.all(), "the null-region row must survive an unnarrowed filter"


def test_a_narrowed_selection_still_drops_blanks():
    mask = filter_mask(FRAME, "region", ["Volta"])
    assert list(mask) == [False, True, False, False]


def test_combining_filters_with_and_survives_one_empty_column():
    """The exact shape of the bug: several filters ANDed, one of them empty."""
    combined = (
        filter_mask(FRAME, "region", ["Ashanti", "Volta"])
        & filter_mask(FRAME, "source_type", [])
        & filter_mask(FRAME, "organism",
                                   sorted(FRAME["organism"].unique()))
    )
    assert combined.any(), "one unpopulated column must not empty the page"
    assert int(combined.sum()) == len(FRAME)
