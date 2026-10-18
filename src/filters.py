"""
Sidebar filter masks.

One function, kept out of the Streamlit entrypoint so it can be tested without
booting the app or opening a database connection.

The rule it encodes: a filter that cannot narrow anything must not narrow
anything. Each sidebar control used to contribute
``frame[column].astype(str).isin(selected)``, and the controls are combined with
AND, so a column no record populated produced an empty option list, an empty
selection, and ``isin([])`` -- false for every row. One unpopulated optional
column therefore emptied an entire page, and the page blamed the user's filter
choices for it.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd


def filter_mask(frame: pd.DataFrame, column: str, selected: Iterable) -> pd.Series:
    """A boolean mask for one filter, permissive when it has nothing to say.

    Returns all-True when the column is absent from the frame, or when the
    selection is empty -- both meaning the control could not offer a real
    choice.

    When the selection covers every value actually present, rows holding a null
    are kept as well. A filter the user has not narrowed should not quietly drop
    records for being blank in a column they never touched; narrowing it
    deliberately does exclude them, which is what narrowing means.
    """
    if column not in frame.columns:
        return pd.Series(True, index=frame.index)
    chosen = list(selected or [])
    if not chosen:
        return pd.Series(True, index=frame.index)

    values = frame[column]
    mask = values.astype(str).isin(chosen)
    present = set(values.dropna().astype(str).unique())
    if present and present.issubset(set(chosen)):
        mask = mask | values.isna()
    return mask


__all__ = ["filter_mask"]
