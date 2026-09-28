"""Upload validation.

The cases here are the defects the rewrite fixed, so a regression on any of them
would restore a bug that reached production.
"""

import pandas as pd
import pytest

from src import validate
from src.upload_schema import clean_text, is_blank, parse_bool, parse_list


# ---------------------------------------------------------------------------
# Blank handling
#
# The original validator cast every object column to str before testing for
# missing values. After that cast a blank cell holds the string "nan", which is
# not null, so the required-field check could never fire and empty identifiers
# were stored as the literal text "nan".
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    None, "", "   ", "nan", "NaN", "NONE", "null", "NA", "n/a", "-", float("nan"),
])
def test_blank_spellings_are_all_blank(value):
    assert is_blank(value) is True


@pytest.mark.parametrize("value", ["Blood", 0, 0.0, "0", "Unknown"])
def test_real_values_are_not_blank(value):
    assert is_blank(value) is False


def test_zero_is_a_value_not_a_blank():
    """Latitude 0 and an age of 0 are real. Treating them as missing would drop
    every specimen on the equator."""
    assert is_blank(0) is False
    assert clean_text(0) == "0"


@pytest.mark.parametrize("value,expected", [
    ("Yes", True), ("yes", True), ("Y", True), ("1", True), ("true", True),
    ("No", False), ("n", False), ("0", False), ("false", False),
    ("", None), (None, None), ("Unknown", None), ("maybe", None),
])
def test_boolean_parsing(value, expected):
    assert parse_bool(value) is expected


def test_list_parsing_strips_and_drops_empties():
    assert parse_list("blaCTX-M-15; qnrS1 ;") == ["blaCTX-M-15", "qnrS1"]
    assert parse_list("") == []
    assert parse_list(None) == []


# ---------------------------------------------------------------------------
# Isolate derivation
#
# The old format issued isolate_id per susceptibility test, so one culture
# tested against six drugs became six isolates.
# ---------------------------------------------------------------------------

def test_isolates_are_derived_per_specimen_and_organism():
    ast = pd.DataFrame([
        {"sample_id": "S1", "organism": "Escherichia coli", "antibiotic": "Ampicillin"},
        {"sample_id": "S1", "organism": "Escherichia coli", "antibiotic": "Meropenem"},
        {"sample_id": "S1", "organism": "Escherichia coli", "antibiotic": "Colistin"},
        {"sample_id": "S1", "organism": "Klebsiella pneumoniae", "antibiotic": "Meropenem"},
        {"sample_id": "S2", "organism": "Escherichia coli", "antibiotic": "Ampicillin"},
    ])
    isolates, rewritten = validate.derive_isolates(ast)

    # Three organisms across two specimens, not five isolates.
    assert len(isolates) == 3
    assert set(isolates["sample_id"]) == {"S1", "S2"}
    # The three E. coli rows from S1 collapse onto one isolate.
    s1_ecoli = rewritten[(rewritten["sample_id"] == "S1")
                         & (rewritten["organism"] == "Escherichia coli")]
    assert s1_ecoli["isolate_id"].nunique() == 1
    # Two organisms from one specimen get distinct sequence numbers.
    s1 = isolates[isolates["sample_id"] == "S1"]
    assert sorted(s1["isolate_number"]) == [1, 2]


def test_derive_isolates_on_empty_frame():
    isolates, rewritten = validate.derive_isolates(pd.DataFrame())
    assert isolates.empty


# ---------------------------------------------------------------------------
# Automated interpretation
#
# The engine returns 'Unknown' when it holds no breakpoint for a pair. That was
# being written straight into result, so 'Unknown' entered the stored data and
# every downstream rate.
# ---------------------------------------------------------------------------

def test_unknown_interpretation_never_becomes_a_result():
    ast = pd.DataFrame([{
        "sample_id": "S1", "isolate_id": "S1-1",
        "organism": "Nonexistent organism", "antibiotic": "Nonexistent drug",
        "method": "DD", "zone_diameter": 20, "mic_value": None,
        "result": None, "guideline": "CLSI", "guideline_version": None,
    }])
    out = validate.perform_automated_interpretation(ast)
    result = out.iloc[0]["result"]
    assert result is None or pd.isna(result) or result in ("S", "I", "R", "NS"), (
        f"an uninterpretable pair produced result={result!r}")


def test_existing_result_is_marked_as_imported():
    ast = pd.DataFrame([{
        "sample_id": "S1", "isolate_id": "S1-1", "organism": "Escherichia coli",
        "antibiotic": "Ampicillin", "method": "DD", "zone_diameter": 10,
        "mic_value": None, "result": "R", "guideline": "CLSI",
        "guideline_version": "M100-Ed34",
    }])
    out = validate.perform_automated_interpretation(ast)
    assert out.iloc[0]["result"] == "R"
    assert out.iloc[0]["result_source"] == "Imported"


# ---------------------------------------------------------------------------
# Frame validation
# ---------------------------------------------------------------------------

def _samples(lab, **overrides):
    row = {
        "sample_id": "S1", "lab_name": lab, "collection_date": "2026-01-10",
        "source_category": "ENVIRONMENT", "region": "Greater Accra",
        "district": "Accra",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _ast(**overrides):
    row = {
        "sample_id": "S1", "isolate_id": "S1-1", "organism": "Escherichia coli",
        "antibiotic": "Ciprofloxacin", "method": "DD", "zone_diameter": 25,
        "result": "S", "guideline": "CLSI", "guideline_version": "M100-Ed34",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_a_clean_upload_passes(lab_name):
    outcome = validate.validate_frames(_samples(lab_name), _ast())
    assert outcome.ok, outcome.errors


def test_result_without_a_breakpoint_edition_is_rejected(lab_name):
    """Breakpoints move between editions, so an S/I/R with no edition cannot be
    reproduced -- and the database CHECK constraint refuses it anyway."""
    outcome = validate.validate_frames(_samples(lab_name),
                                       _ast(guideline_version=None))
    assert not outcome.ok
    assert any("edition" in e.lower() or "version" in e.lower()
               for e in outcome.errors), outcome.errors


def test_unknown_vocabulary_value_is_rejected(lab_name):
    outcome = validate.validate_frames(
        _samples(lab_name, source_category="HUMANS"), _ast())
    assert not outcome.ok


def test_unapproved_laboratory_is_rejected():
    outcome = validate.validate_frames(
        _samples("Some Unapproved Lab"), _ast())
    assert not outcome.ok
    assert any("laborator" in e.lower() for e in outcome.errors), outcome.errors


def test_ambiguous_date_format_is_rejected(lab_name):
    outcome = validate.validate_frames(
        _samples(lab_name, collection_date="10/01/2026"), _ast())
    assert not outcome.ok


def test_human_specimen_requires_its_clinical_fields(lab_name):
    outcome = validate.validate_frames(
        _samples(lab_name, source_category="HUMAN"), _ast())
    assert not outcome.ok
    joined = " ".join(outcome.errors).lower()
    assert "ward_type" in joined or "facility_code" in joined, outcome.errors


def test_receipt_before_collection_is_rejected(lab_name):
    outcome = validate.validate_frames(
        _samples(lab_name, receipt_date="2026-01-09"), _ast())
    assert not outcome.ok
    assert any("precede" in e.lower() for e in outcome.errors), outcome.errors


def test_out_of_range_coordinates_are_rejected(lab_name):
    outcome = validate.validate_frames(_samples(lab_name, latitude=500), _ast())
    assert not outcome.ok


def test_orphan_ast_row_is_rejected(lab_name):
    outcome = validate.validate_frames(_samples(lab_name),
                                       _ast(sample_id="DOES-NOT-EXIST"))
    assert not outcome.ok
