"""
Disclosure control for anything shown publicly.

The platform already suppresses a *rate* below thirty isolates, because a
percentage computed on a handful of results is not a measurement. That is a
statistical rule, and it deliberately keeps the counts: internally, knowing a
stratum holds four isolates is useful.

Published, the same behaviour is the wrong way round. The count is the
disclosive part. "Neonatal ward, this hospital, March, two isolates" describes
a person, and a patient pseudonym does nothing about it -- pseudonymisation
protects the identifier, not the combination of attributes around it. The risk
is also not in the default view but in the *filtering*: an interactive page
lets a visitor narrow until a cell contains one person, and every additional
filter is another attribute attached to them.

So this module withholds small counts rather than small rates, and it is the
layer that has to sit between the analysis and any public view.

Two kinds of suppression, because one is not enough:

**Primary** withholds any cell below the threshold.

**Secondary** withholds a second cell when the first could be recovered by
subtraction. If a table shows a total and five categories, and exactly one
category is suppressed, its value is the total minus the other four. Suppressing
it alone achieves nothing, which is the usual way a disclosure-control pass
fails: it looks applied, and the number is still there for anyone who subtracts.

What this module does not attempt is protection against an attacker who
accumulates many overlapping queries, or who brings outside knowledge about a
particular patient. Those need query auditing and a stated data-sharing
agreement, which are governance rather than code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

#: Smallest count that may be published.
#:
#: Five is the common floor in published health statistics. It is a convention
#: rather than a guarantee, and it is a floor rather than a target: a cell of
#: five in a rare organism at a single small facility can still be identifying,
#: which is why the threshold is an argument and not a constant buried in a
#: query.
MIN_PUBLIC_CELL = 5

#: A frame holding any of these columns describes individual records rather than
#: an aggregate, and must never reach a public view. Testing the data beats
#: remembering to gate each call site: a table added later is covered without
#: anyone having to think about it.
RECORD_ID_COLUMNS = frozenset({
    "sample_id", "specimen_id", "isolate_id", "subject_id", "encounter_id",
    "genomic_id", "patient_pseudonym", "accession_number", "local_patient_id",
    "email", "password_hash",
})


def is_record_level(data) -> bool:
    """Whether a frame describes individual records."""
    columns = getattr(data, "columns", None)
    if columns is None:
        return False
    return bool(RECORD_ID_COLUMNS
                & {str(c).strip().lower() for c in columns})

#: What a withheld cell shows. Not zero, and not blank: a reader has to be able
#: to tell "too few to publish" from "none found", because treating the first as
#: the second is how a suppressed table becomes a misleading one.
WITHHELD = "withheld"

PRIMARY = "below the threshold"
SECONDARY = "withheld so another cell cannot be recovered by subtraction"


@dataclass
class SuppressionReport:
    """What was withheld, and why.

    Published alongside the table it describes. A table with silent gaps invites
    the reader to assume zero, and a reader who knows how much was withheld can
    judge how much of the picture they are being shown.
    """
    threshold: int
    cells_total: int = 0
    primary: int = 0
    secondary: int = 0
    columns: List[str] = field(default_factory=list)

    @property
    def withheld(self) -> int:
        return self.primary + self.secondary

    @property
    def summary(self) -> str:
        if not self.cells_total:
            return "Nothing to publish."
        if not self.withheld:
            return (f"No cell was withheld. Every value shown rests on at least "
                    f"{self.threshold} records.")
        share = 100.0 * self.withheld / self.cells_total
        text = (f"{self.withheld:,} of {self.cells_total:,} values ({share:.1f}%) "
                f"are withheld because fewer than {self.threshold} records stand "
                f"behind them.")
        if self.secondary:
            text += (f" {self.secondary:,} of those are withheld not for being "
                     "small themselves but because they would otherwise be "
                     "recoverable by subtracting the rest from the total.")
        text += " Withheld is not zero."
        return text


def _suppressible(value) -> bool:
    """Whether a value is a count that could identify someone.

    Zero is left visible. It describes nobody, and hiding it would remove the
    reader's ability to tell "we looked and found none" from "we did not look"
    -- a distinction this platform works hard elsewhere to preserve.
    """
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if number != number:                       # NaN
        return False
    return 0 < number


def apply_disclosure_control(frame: pd.DataFrame,
                             count_columns: Sequence[str],
                             *,
                             group_by: Optional[str] = None,
                             threshold: int = MIN_PUBLIC_CELL,
                             also_blank: Optional[Sequence[str]] = None
                             ) -> tuple:
    """Withhold small counts. Returns ``(frame, SuppressionReport)``.

    ``count_columns`` are the columns holding counts of people, specimens or
    isolates. ``also_blank`` names columns -- rates, intervals -- that must be
    blanked on any row whose count was withheld, since a percentage over a
    withheld denominator gives the denominator away as surely as printing it.

    ``group_by`` enables secondary suppression within each group. Without it
    only primary suppression is applied, which is weaker and said so in the
    report rather than left implied.
    """
    report = SuppressionReport(threshold=threshold,
                               columns=[c for c in count_columns
                                        if c in frame.columns])
    if frame.empty or not report.columns:
        return frame.copy(), report

    out = frame.copy()
    also_blank = [c for c in (also_blank or []) if c in out.columns]

    for column in report.columns:
        values = out[column]
        report.cells_total += int(values.notna().sum())

        small = values.map(lambda v: _suppressible(v) and float(v) < threshold)
        report.primary += int(small.sum())

        if group_by and group_by in out.columns:
            # Secondary suppression. One withheld cell in a group is no
            # suppression at all when a total is published beside it: the value
            # is whatever the total minus the others comes to.
            for index in out.groupby(group_by, dropna=False).groups.values():
                if int(small.loc[index].sum()) != 1:
                    continue
                block = out.loc[index, column]
                candidates = block[~small.loc[index] & block.map(_suppressible)]
                if candidates.empty:
                    continue
                small.loc[candidates.astype(float).idxmin()] = True
                report.secondary += 1

        # The column has to hold text once a cell is withheld, and pandas will
        # not place a string into an integer column without being told.
        if small.any():
            out[column] = out[column].astype(object)
            out.loc[small, column] = WITHHELD
            for other in also_blank:
                out.loc[small, other] = None

    return out, report


def cell_text(value) -> str:
    """One cell, as a reader should see it.

    Counts keep their thousands separators, a missing value becomes an empty
    string rather than the word "nan", and a withheld marker passes through
    untouched.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number:                            # NaN
        return ""
    if float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:,.1f}"


def for_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Make a suppressed frame safe to hand to a table widget.

    A column holding both integers and the word "withheld" has object dtype,
    and Arrow -- which Streamlit uses to ship a table to the browser -- refuses
    it: it infers an integer column from the first values and then fails on the
    string, so the table silently does not arrive. The frame itself is correct;
    it simply cannot be transmitted in that shape.

    The fix is to render the whole column as text rather than to drop the
    marker, because dropping it is the one thing that must not happen. A blank
    reads as zero, and the distinction between "too few to publish" and "none
    found" is what the rest of this module exists to preserve. Thousands
    separators are kept so a count still reads as a count.

    Only columns that actually hold a withheld marker are touched. Everything
    else keeps its dtype, so numeric columns stay sortable in the widget.
    """
    if frame.empty:
        return frame
    out = frame.copy()
    for column in out.columns:
        if out[column].dtype != object:
            continue
        values = out[column]
        if not bool((values == WITHHELD).any()):
            continue
        out[column] = values.map(cell_text)
    return out


def safe_to_publish(frame: pd.DataFrame, count_column: str,
                    threshold: int = MIN_PUBLIC_CELL) -> bool:
    """Whether a frame can be shown at all.

    A table in which almost every cell is withheld is not a safe publication --
    it is an admission that the question was asked at too fine a grain, and
    showing it invites the reader to combine it with the next one.
    """
    if frame.empty or count_column not in frame.columns:
        return False
    counts = frame[count_column].map(
        lambda v: float(v) if _suppressible(v) else 0.0)
    publishable = int((counts >= threshold).sum())
    return publishable > 0 and publishable >= len(counts) * 0.5


__all__ = [
    "MIN_PUBLIC_CELL", "RECORD_ID_COLUMNS", "is_record_level", "WITHHELD", "PRIMARY", "SECONDARY",
    "SuppressionReport", "apply_disclosure_control", "for_display",
    "cell_text",
    "safe_to_publish",
]
