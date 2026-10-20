"""
Tests for the palette and for disclosure control's display step.

Both are shared by the export that builds the public site: the palette decides
every colour the figures are drawn in, and the display step is what lets a
suppressed table reach a reader at all. A count column holding the word
"withheld" cannot be serialised to Arrow, so the table silently never arrives
and the reader sees nothing rather than a suppressed figure -- a real defect
this file exists to keep fixed.
"""

import pandas as pd
import pytest

from src import disclosure, palette


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

def test_palette_is_okabe_ito():
    assert len(set(palette.SEQUENCE)) == 8
    assert all(c.startswith("#") and len(c) == 7 for c in palette.SEQUENCE)


def test_susceptibility_avoids_the_red_green_pair():
    """S against R is the most consequential distinction on the platform, and
    red/green is the pair that disappears under deuteranopia."""
    assert palette.RESULT["S"] != palette.RESULT["R"]
    assert palette.GREEN not in (palette.RESULT["S"], palette.RESULT["R"])


def test_every_sector_has_a_fixed_colour():
    for sector in ("human", "animal", "food", "environment", "aquaculture"):
        assert sector in palette.SECTOR
    assert len(set(palette.SECTOR.values())) == len(palette.SECTOR)


def test_ramp_returns_what_was_asked_for():
    assert palette.ramp(0) == []
    assert len(palette.ramp(3)) == 3
    assert palette.ramp(3) == palette.SEQUENCE[:3]
    # Past the eight the set holds, it repeats rather than failing to draw.
    assert len(palette.ramp(11)) == 11


# ---------------------------------------------------------------------------
# Getting a suppressed table to the browser
# ---------------------------------------------------------------------------

def _suppressed():
    frame = pd.DataFrame({
        "ward": ["A", "B", "C"],
        "isolates": [40, 2, 1200],
    })
    return disclosure.apply_disclosure_control(frame, ["isolates"])[0]


def test_withheld_column_becomes_serialisable():
    """Mixed integers and a string in one column is what Arrow refuses."""
    shown = disclosure.for_display(_suppressed())
    assert shown["isolates"].map(type).nunique() == 1
    assert shown["isolates"].map(lambda v: isinstance(v, str)).all()


def test_withheld_marker_is_never_dropped():
    """A blank cell reads as zero. That is the one outcome that must not
    happen, which is why the column is turned into text rather than cleaned."""
    shown = disclosure.for_display(_suppressed())
    assert disclosure.WITHHELD in set(shown["isolates"])


def test_counts_stay_readable_as_counts():
    shown = disclosure.for_display(_suppressed())
    assert "1,200" in set(shown["isolates"])
    assert "40" in set(shown["isolates"])


def test_untouched_columns_keep_their_dtype():
    """Only a column actually holding a marker is converted, so numeric columns
    stay sortable in the widget."""
    frame = pd.DataFrame({"ward": ["A", "B"], "isolates": [40, 2],
                          "percent": [12.5, 3.0]})
    shown_source, _ = disclosure.apply_disclosure_control(frame, ["isolates"])
    shown = disclosure.for_display(shown_source)
    assert shown["percent"].dtype.kind == "f"


def test_a_table_with_nothing_withheld_is_left_alone():
    frame = pd.DataFrame({"ward": ["A", "B"], "isolates": [40, 90]})
    shown_source, report = disclosure.apply_disclosure_control(
        frame, ["isolates"])
    assert not report.withheld
    shown = disclosure.for_display(shown_source)
    assert shown["isolates"].dtype.kind in "iu"


def test_empty_frame_is_returned_unchanged():
    empty = pd.DataFrame()
    assert disclosure.for_display(empty).empty


@pytest.mark.parametrize("value,expected", [
    (None, ""),
    (float("nan"), ""),
    (1200, "1,200"),
    (1200.0, "1,200"),
    (1234.56, "1,234.6"),
    (disclosure.WITHHELD, disclosure.WITHHELD),
    ("Not recorded", "Not recorded"),
])
def test_cell_text(value, expected):
    assert disclosure.cell_text(value) == expected


def test_cell_text_separates_none_found_from_withheld():
    """Zero is a measurement; withheld is the absence of one. The two must not
    render the same way."""
    assert disclosure.cell_text(0) == "0"
    assert disclosure.cell_text(0) != disclosure.WITHHELD
    assert disclosure.cell_text(None) != disclosure.cell_text(0)
