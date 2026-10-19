"""
Tests for the public surface: the landing registry, the palette, and the step
between disclosure control and a table widget.

The page bodies themselves are not unit-tested here -- they are Streamlit
rendering, and testing them means testing Streamlit. What is tested is
everything a page body depends on being true: that every card leads somewhere,
that no card number crashes on an empty platform, that colour is never the only
signal, and that a withheld cell survives the trip to the browser. The last one
is a real defect this file exists to keep fixed: a count column holding the
word "withheld" cannot be serialised to Arrow, so the table silently never
arrives, and the reader sees nothing rather than a suppressed figure.
"""

import pandas as pd
import pytest

from src import disclosure, palette
from src.page_public import PREFIX, RENDERERS, SECTIONS


# ---------------------------------------------------------------------------
# The landing registry
# ---------------------------------------------------------------------------

def test_every_card_has_a_page():
    for section in SECTIONS:
        assert section.key in RENDERERS, f"{section.title} leads nowhere"


def test_no_orphan_pages():
    """A page with no card is unreachable by a visitor."""
    assert set(RENDERERS) == {s.key for s in SECTIONS}


def test_keys_are_prefixed_and_unique():
    keys = [s.key for s in SECTIONS]
    assert len(keys) == len(set(keys))
    assert all(k.startswith(PREFIX) for k in keys)


def test_keys_cannot_collide_with_a_sidebar_page():
    """The router tells the two apart by prefix, so the prefix must be unusable
    as a sidebar page name."""
    assert ":" in PREFIX
    for section in SECTIONS:
        assert section.key != section.title


def test_card_numbers_survive_an_empty_platform():
    """The landing page renders before any data is loaded, so every card stat
    has to cope with the counts query returning nothing at all."""
    for section in SECTIONS:
        value, unit = section.stat({})
        assert value == "0"
        assert unit and not unit.endswith(".")


def test_card_numbers_are_formatted_for_a_reader():
    counts = {"results": 20826, "organisms": 13, "sectors": 5,
              "genomes": 1860, "amu": 2186, "amc": 1370, "pps": 18,
              "labs": 19}
    values = {s.title: s.stat(counts)[0] for s in SECTIONS}
    assert values["Resistance"] == "20,826"
    assert values["Genomics"] == "1,860"
    # Use pools three sources, because a reader does not care which table a
    # consumption record landed in.
    assert values["Antimicrobial use"] == "3,574"


def test_every_card_carries_a_non_colour_cue():
    """Colour may repeat a distinction; it may never be the only thing carrying
    one. Each card therefore has a badge and a title as well as a colour."""
    for section in SECTIONS:
        assert section.icon.strip()
        assert section.title.strip()
        assert section.blurb.strip()


def test_card_colours_are_from_the_palette():
    allowed = set(palette.SEQUENCE)
    for section in SECTIONS:
        assert section.colour in allowed, section.title


def test_card_colours_are_distinct():
    colours = [s.colour for s in SECTIONS]
    assert len(colours) == len(set(colours))


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
