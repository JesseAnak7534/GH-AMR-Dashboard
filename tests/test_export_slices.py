"""
Tests for the pre-computed filtered views.

The site is static, so a filter can only reach a combination somebody exported.
That makes two things worth testing: that the filename a filter resolves to is
stable (a slug that changes breaks every published link to a view), and that
the priority-pathogen matcher covers the three shapes a list entry takes.

The second is not cosmetic. The WHO critical list names an order,
"Enterobacterales", and the laboratory names species. Matching by equality
alone reported the single most important entry on the list as not under
surveillance while 1,505 isolates qualified.
"""

import pandas as pd
import pytest

from scripts.export_sections import ENTEROBACTERALES, _matches
from scripts.export_slices import MIN_SLICE_ISOLATES, dimensions, slug


# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("parts,expected", [
    (("human", "period", "2024"), "human__period__2024"),
    (("human", "region", "Greater Accra"), "human__region__greater-accra"),
    (("food", "lab_name", "CSIR – Water Research"),
     "food__lab-name__csir-water-research"),
    (("human", "region", "Upper West"), "human__region__upper-west"),
])
def test_slug_is_stable_and_filename_safe(parts, expected):
    assert slug(*parts) == expected


def test_slug_never_empty():
    """An empty slug would collide with every other empty slug."""
    assert slug("") == "all"
    assert slug("", "", "") == "all"


def test_slug_has_no_characters_windows_rejects():
    produced = slug("human", "lab_name", 'A/B:C*D?E"F<G>H|I')
    assert not set(produced) & set('/\:*?"<>|')


# ---------------------------------------------------------------------------
# Dimensions offered
# ---------------------------------------------------------------------------

def _frame():
    return pd.DataFrame({
        "collection_datetime": pd.to_datetime(
            ["2024-03-02", "2025-06-01", "2026-01-15"], utc=True),
        "region": ["Greater Accra", "Ashanti", "Greater Accra"],
        "lab_name": ["Korle Bu", "KATH", "Korle Bu"],
    })


def test_dimensions_cover_period_region_and_laboratory():
    keys = [d["key"] for d in dimensions(_frame())]
    assert keys == ["period", "region", "lab_name"]


def test_period_values_are_the_years_present():
    period = dimensions(_frame())[0]
    assert period["values"] == ["2024", "2025", "2026"]


def test_dimension_values_are_deduplicated_and_sorted():
    region = dimensions(_frame())[1]
    assert region["values"] == ["Ashanti", "Greater Accra"]


def test_every_dimension_carries_a_note():
    """Each filter says what it does to the figures, because a region filter
    that returns no publishable rate needs to say so before it is used."""
    for dimension in dimensions(_frame()):
        assert dimension["note"].strip()


def test_slice_floor_is_meaningful():
    assert MIN_SLICE_ISOLATES >= 20


# ---------------------------------------------------------------------------
# Priority-list matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("listed,observed", [
    ("Escherichia coli", "Escherichia coli"),
    ("escherichia coli", "Escherichia coli"),          # case insensitive
    ("Campylobacter spp.", "Campylobacter jejuni"),
    ("Enterococcus spp.", "Enterococcus faecium"),
    ("Enterobacterales", "Escherichia coli"),
    ("Enterobacterales", "Klebsiella pneumoniae"),
    ("Enterobacterales", "Salmonella enterica"),
])
def test_priority_entry_matches(listed, observed):
    assert _matches(listed, observed)


@pytest.mark.parametrize("listed,observed", [
    ("Enterobacterales", "Pseudomonas aeruginosa"),
    ("Enterobacterales", "Acinetobacter baumannii"),
    ("Enterococcus spp.", "Staphylococcus aureus"),
    ("Escherichia coli", "Escherichia albertii"),
    ("Staphylococcus aureus", ""),
    ("", "Staphylococcus aureus"),
])
def test_priority_entry_does_not_match(listed, observed):
    assert not _matches(listed, observed)


def test_genus_suffix_is_stripped_as_a_suffix_not_a_character_set():
    """``rstrip(" spp.")`` strips characters, so "Enterococcus spp." became
    "Enterococcu" and matched nothing. The suffix has to come off whole."""
    assert _matches("Enterococcus spp.", "Enterococcus faecalis")
    assert not _matches("Enterococcus spp.", "Enterococcu something")


def test_enterobacterales_membership_covers_what_is_isolated():
    for genus in ("Escherichia", "Klebsiella", "Salmonella", "Shigella",
                  "Proteus", "Enterobacter", "Citrobacter", "Serratia"):
        assert genus in ENTEROBACTERALES
