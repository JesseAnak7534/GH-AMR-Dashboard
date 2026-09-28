"""The KoboToolbox form and mapper, and the WHONET export.

The form test matters because the old one asked for one antibiotic per
submission with a hand-typed isolate identifier, which reproduced the
per-test-isolate defect at the point of collection. The export tests matter
because unmapped values used to be given invented codes.
"""

import pandas as pd
import pytest

from src import kobo_form as kf
from src import whonet


# ---------------------------------------------------------------------------
# Form structure
# ---------------------------------------------------------------------------

def test_survey_groups_and_repeats_are_balanced():
    survey, _ = kf.build_survey()
    group = repeat = 0
    for row in survey:
        kind = row.get("type", "")
        group += (kind == "begin_group") - (kind == "end_group")
        repeat += (kind == "begin_repeat") - (kind == "end_repeat")
        assert group >= 0 and repeat >= 0, f"unbalanced at {row.get('name')}"
    assert group == 0 and repeat == 0


def test_susceptibility_results_are_nested_inside_isolates():
    """The structural fix. If ast_results sat beside isolates rather than
    inside them, a laboratory could again record one isolate per antibiotic."""
    survey, _ = kf.build_survey()
    depth = 0
    depths = {}
    for row in survey:
        kind = row.get("type", "")
        if kind == "begin_repeat":
            depth += 1
            depths[row["name"]] = depth
        elif kind == "end_repeat":
            depth -= 1
    assert depths.get("isolates") == 1
    assert depths.get("ast_results") == 2, "ast_results must nest inside isolates"


def test_every_dropdown_has_a_choice_list():
    survey, choices = kf.build_survey()
    lists = {c["list_name"] for c in choices}
    for row in survey:
        kind = str(row.get("type", ""))
        if kind.startswith(("select_one ", "select_multiple ")):
            name = kind.split(" ", 1)[1]
            assert name in lists, f"{row.get('name')} references missing list {name}"


def test_controlled_fields_are_dropdowns_not_free_text():
    """Region, organism and antibiotic were free text, so one value typed three
    ways became three values."""
    survey, _ = kf.build_survey()
    kinds = {row.get("name"): str(row.get("type", "")) for row in survey}
    for field in ("region", "organism", "antibiotic", "specimen_type",
                  "ward_type", "sex", "patient_type", "result", "method",
                  "sampling_purpose", "qc_status", "guideline_version"):
        assert kinds.get(field, "").startswith("select_one"), (
            f"{field} should be a dropdown, is {kinds.get(field)!r}")


def test_ghana_has_sixteen_regions():
    assert len(kf.GHANA_REGIONS) == 16
    assert len(set(kf.GHANA_REGIONS)) == 16


# ---------------------------------------------------------------------------
# Mapping submissions back
# ---------------------------------------------------------------------------

def _submission(sample_id="S1", organisms=None):
    organisms = organisms or [("klebsiella_pneumoniae", [("ceftriaxone", "r"),
                                                         ("meropenem", "s")])]
    return {
        "submission_type": "ast",
        "reporting/lab_name": "korle_bu_teaching_hospital",
        "reporting/region": "greater_accra",
        "reporting/district": "Accra Metropolitan",
        "specimen/sample_id": sample_id,
        "specimen/source_category": "human",
        "specimen/collection_date": "2026-09-14",
        "specimen/specimen_type": "blood",
        "specimen/sampling_purpose": "routine_diagnostic",
        "patient/facility_code": "KBTH",
        "patient/local_patient_id": "MRN-1",
        "patient/sex": "f",
        "patient/age_value": "7",
        "patient/age_unit": "months",
        "patient/ward_type": "paediatric",
        "isolates": [
            {
                "isolates/organism": organism,
                "isolates/identification_method": "maldi_tof",
                "isolates/ast_results": [
                    {"isolates/ast_results/antibiotic": ab,
                     "isolates/ast_results/method": "dd",
                     "isolates/ast_results/zone_diameter": "12",
                     "isolates/ast_results/result": res,
                     "isolates/ast_results/guideline_version": "clsi_m100_ed35_2025",
                     "isolates/ast_results/qc_status": "pass"}
                    for ab, res in results
                ],
            }
            for organism, results in organisms
        ],
    }


def test_choice_names_become_labels():
    samples, _, ast = kf.submissions_to_frames([_submission()])
    row = samples.iloc[0]
    assert row["region"] == "Greater Accra"
    assert row["specimen_type"] == "Blood"
    assert row["sex"] == "F"
    assert row["ward_type"] == "Paediatric"
    assert ast.iloc[0]["organism"] == "Klebsiella pneumoniae"
    assert ast.iloc[0]["result"] == "R"


def test_age_in_months_converts_to_years():
    """Recording an infant as 0 years loses the under-one band."""
    samples, _, _ = kf.submissions_to_frames([_submission()])
    assert samples.iloc[0]["age_years"] == pytest.approx(7 / 12, abs=1e-3)


def test_one_isolate_per_organism_not_per_antibiotic():
    """Two agents against one organism is one isolate."""
    _, isolates, ast = kf.submissions_to_frames([_submission()])
    assert len(isolates) == 1
    assert len(ast) == 2
    assert ast["isolate_id"].nunique() == 1


def test_two_organisms_become_two_numbered_isolates():
    submission = _submission(organisms=[
        ("klebsiella_pneumoniae", [("meropenem", "s")]),
        ("escherichia_coli", [("ampicillin", "r")]),
    ])
    _, isolates, ast = kf.submissions_to_frames([submission])
    assert len(isolates) == 2
    assert sorted(isolates["isolate_number"]) == [1, 2]
    assert isolates["isolate_id"].nunique() == 2
    assert ast["isolate_id"].nunique() == 2


def test_breakpoint_edition_splits_into_standard_and_version():
    _, _, ast = kf.submissions_to_frames([_submission()])
    assert ast.iloc[0]["guideline"] == "CLSI"
    assert "M100" in str(ast.iloc[0]["guideline_version"])


def test_other_organism_uses_the_free_text_follow_up():
    submission = _submission()
    submission["isolates"][0]["isolates/organism"] = "other"
    submission["isolates"][0]["isolates/organism_other"] = "Raoultella ornithinolytica"
    _, isolates, _ = kf.submissions_to_frames([submission])
    assert isolates.iloc[0]["organism"] == "Raoultella ornithinolytica"


def test_empty_input_returns_empty_frames():
    samples, isolates, ast = kf.submissions_to_frames([])
    assert samples.empty and isolates.empty and ast.empty


# ---------------------------------------------------------------------------
# WHONET export
# ---------------------------------------------------------------------------

def test_known_organism_gets_its_governed_code():
    code, _ = whonet.normalize_organism("Escherichia coli")
    assert code and code != whonet.UNMAPPED_CODE


def test_unknown_organism_is_not_given_an_invented_code():
    """A made-up code produces a file that imports somewhere and is wrong,
    rather than failing and being noticed."""
    code, name = whonet.normalize_organism("Raoultella ornithinolytica")
    assert code == whonet.UNMAPPED_CODE
    assert name == "Raoultella ornithinolytica", "the name is preserved"


def test_unknown_antibiotic_is_not_given_an_invented_code():
    assert whonet.normalize_antibiotic("Some Experimental Drug") == whonet.UNMAPPED_CODE


def test_unmapped_values_are_listed_for_the_operator():
    ast = pd.DataFrame([
        {"organism": "Escherichia coli", "antibiotic": "Ciprofloxacin"},
        {"organism": "Raoultella ornithinolytica", "antibiotic": "Ciprofloxacin"},
        {"organism": "Escherichia coli", "antibiotic": "Some Experimental Drug"},
    ])
    unmapped = whonet.unmapped_values(pd.DataFrame(), ast)
    assert "Raoultella ornithinolytica" in unmapped["organisms"]
    assert "Some Experimental Drug" in unmapped["antibiotics"]
    assert "Escherichia coli" not in unmapped["organisms"]


def test_unmapped_codes_make_validation_fail():
    frame = pd.DataFrame([{
        "LABORATORY": "GH001", "SPEC_NUM": "S1", "SPEC_DATE": "2026-01-01",
        "ORGANISM": "Raoultella ornithinolytica",
        "ORG_CODE": whonet.UNMAPPED_CODE,
    }])
    validation = whonet.validate_whonet_data(frame)
    assert validation["is_valid"] is False
    assert any("governed" in e.lower() or "unmapped" in e.lower()
               for e in validation["errors"]), validation["errors"]


def test_export_schema_is_versioned():
    assert whonet.EXPORT_SCHEMA_VERSION
