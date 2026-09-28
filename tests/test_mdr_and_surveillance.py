"""MDR classification, deduplication, reporting thresholds and consumption.

Each test corresponds to a defect the review named or that surfaced while
fixing one.
"""

import numpy as np
import pandas as pd
import pytest

from src import consumption, mdr
from src import surveillance as sv


# ---------------------------------------------------------------------------
# MDR classification
# ---------------------------------------------------------------------------

def test_category_sets_are_organism_specific():
    """One generic class map was applied to every organism. The agreed
    definitions list different categories per organism group."""
    groups = {}
    for organism in ("Escherichia coli", "Staphylococcus aureus",
                     "Enterococcus faecalis", "Pseudomonas aeruginosa",
                     "Acinetobacter baumannii"):
        name, categories = mdr.category_set_for(organism)
        assert name is not None, organism
        groups[name] = len(categories)
    # The sets genuinely differ in size, so they are not one list reused.
    assert len(set(groups.values())) > 1, groups


def test_intrinsic_resistance_does_not_count_towards_mdr():
    """Klebsiella is resistant to ampicillin by its own biology. Scoring that
    gave every Klebsiella a free category."""
    result = mdr.classify_isolate("Klebsiella pneumoniae", [
        ("Ampicillin", "R"),       # intrinsic
        ("Ciprofloxacin", "S"),
        ("Gentamicin", "S"),
        ("Meropenem", "S"),
    ])
    assert "Ampicillin" in result.agents_excluded_intrinsic
    assert result.classification == mdr.CLASS_NOT_MDR
    assert result.n_non_susceptible == 0


def test_intermediate_counts_as_non_susceptible():
    """The definitions use non-susceptible, which is I or R. Counting only R
    understated resistance."""
    result = mdr.classify_isolate("Escherichia coli", [
        ("Ciprofloxacin", "I"), ("Gentamicin", "I"), ("Ceftriaxone", "I"),
        ("Meropenem", "S"),
    ])
    assert result.classification == mdr.CLASS_MDR
    assert result.n_non_susceptible == 3


def test_a_narrow_panel_is_not_reported_as_not_mdr():
    """An isolate tested against two agents cannot be shown not to be multidrug
    resistant; saying so would describe the panel, not the organism."""
    result = mdr.classify_isolate("Escherichia coli", [
        ("Ampicillin", "R"), ("Ciprofloxacin", "R"),
    ])
    assert result.classification == mdr.CLASS_INSUFFICIENT


def test_genuine_mdr_is_identified_with_its_categories():
    result = mdr.classify_isolate("Escherichia coli", [
        ("Ampicillin", "R"), ("Ciprofloxacin", "R"), ("Gentamicin", "R"),
        ("Ceftriaxone", "R"), ("Meropenem", "S"), ("Colistin", "S"),
    ])
    assert result.classification == mdr.CLASS_MDR
    assert result.n_non_susceptible >= 3
    assert "Carbapenems" in result.categories_susceptible
    assert result.reason


def test_xdr_leaves_at_most_two_categories_susceptible():
    result = mdr.classify_isolate("Pseudomonas aeruginosa", [
        ("Gentamicin", "R"), ("Amikacin", "R"), ("Meropenem", "R"),
        ("Imipenem", "R"), ("Ceftazidime", "R"), ("Cefepime", "R"),
        ("Ciprofloxacin", "R"), ("Piperacillin-Tazobactam", "R"),
        ("Aztreonam", "R"), ("Colistin", "S"),
    ])
    assert result.classification == mdr.CLASS_XDR
    assert len(result.categories_susceptible) <= 2


def test_unclassifiable_isolates_leave_both_numerator_and_denominator():
    """Otherwise a laboratory could lower its MDR rate by testing fewer
    agents."""
    classified = pd.DataFrame([
        {"classification": mdr.CLASS_MDR},
        {"classification": mdr.CLASS_NOT_MDR},
        {"classification": mdr.CLASS_INSUFFICIENT},
        {"classification": mdr.CLASS_INSUFFICIENT},
    ])
    summary = mdr.summarise(classified)
    assert summary["classifiable"] == 2
    assert summary["percent_of_classifiable"][mdr.CLASS_MDR] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Wilson intervals and reporting thresholds
# ---------------------------------------------------------------------------

def test_wilson_interval_stays_inside_zero_and_one_hundred():
    """The reason for preferring Wilson: at these sample sizes a normal
    approximation runs outside the possible range."""
    low, high = sv.wilson_interval(30, 30)
    assert 0 <= low <= 100 and 0 <= high <= 100
    low, high = sv.wilson_interval(0, 30)
    assert 0 <= low <= 100 and 0 <= high <= 100


def test_wilson_interval_narrows_as_the_sample_grows():
    narrow = sv.wilson_interval(500, 1000)
    wide = sv.wilson_interval(5, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_interval_on_no_data():
    assert sv.wilson_interval(0, 0) == (None, None)


def _observations(n, organism="Escherichia coli", antibiotic="Ciprofloxacin",
                  result="R", sector="human", start_day=1):
    return pd.DataFrame([{
        "dataset_id": "d1",
        "isolate_id": f"iso-{i}",
        "subject_id": f"subj-{i}",
        "organism": organism,
        "antibiotic": antibiotic,
        "result": result,
        "sector": sector,
        "specimen_type": "Blood",
        "collection_datetime": pd.Timestamp("2026-01-01", tz="UTC")
                               + pd.Timedelta(days=start_day + i),
        "qc_status": "Pass",
        "breakpoint_standard": "CLSI",
        "breakpoint_version": "M100-Ed34",
    } for i in range(n)])


def test_percentage_is_withheld_below_the_reporting_threshold():
    table, _ = sv.cumulative_antibiogram(_observations(10), period_months=None)
    row = table.iloc[0]
    assert row["status"] == sv.STATUS_SUPPRESSED
    assert row["percent_susceptible"] is None
    assert row["tested"] == 10, "the count is still reported"


def test_percentage_is_reported_at_the_threshold():
    table, _ = sv.cumulative_antibiogram(_observations(30), period_months=None)
    row = table.iloc[0]
    assert row["status"] == sv.STATUS_REPORTED
    assert row["percent_susceptible"] is not None


def test_sectors_are_not_pooled_without_saying_so():
    frame = pd.concat([_observations(5, sector="human"),
                       _observations(5, sector="animal")])
    with pytest.raises(ValueError, match="pool"):
        sv.pathogen_distribution(frame)
    # Explicitly allowed, it proceeds.
    assert not sv.pathogen_distribution(frame, allow_cross_sector=True).empty


def test_pathogen_distribution_counts_isolates_not_tests():
    """An organism tested against more agents must not outrank one tested
    against fewer."""
    frame = pd.concat([
        _observations(1, organism="Escherichia coli", antibiotic="A"),
        _observations(1, organism="Escherichia coli", antibiotic="B"),
        _observations(1, organism="Escherichia coli", antibiotic="C"),
    ])
    frame["isolate_id"] = "same-isolate"
    table = sv.pathogen_distribution(frame)
    assert table.iloc[0]["isolates"] == 1, "three tests on one isolate is one isolate"


# ---------------------------------------------------------------------------
# CLSI M39 deduplication
# ---------------------------------------------------------------------------

def test_first_isolate_per_subject_per_organism_is_kept():
    """Repeat testing of one patient's persistent infection must contribute
    once, not weight the antibiogram towards the most-cultured patients."""
    frame = _observations(4)
    frame["subject_id"] = "one-patient"
    frame["organism"] = "Escherichia coli"
    deduplicated, report = sv.select_first_isolates(frame, period_months=None)
    assert report.isolates_before == 4
    assert report.isolates_after == 1
    assert report.removed == 3
    assert "M39" in report.rule


def test_different_subjects_are_all_kept():
    frame = _observations(4)          # four distinct subject ids
    _, report = sv.select_first_isolates(frame, period_months=None)
    assert report.isolates_after == 4


def test_isolates_without_a_subject_key_are_not_merged():
    """Without a key, repeat sampling cannot be detected, so each isolate stands
    alone rather than being silently merged with another subject's."""
    frame = _observations(3)
    frame["subject_id"] = None
    _, report = sv.select_first_isolates(frame, period_months=None)
    assert report.isolates_after == 3
    assert report.unkeyed_isolates == 3


def test_failed_quality_control_is_excluded_and_counted():
    frame = _observations(5)
    frame.loc[frame.index[:2], "qc_status"] = "Fail"
    kept, dropped = sv.exclude_failed_qc(frame)
    assert dropped == 2
    assert len(kept) == 3


# ---------------------------------------------------------------------------
# Consumption denominators
# ---------------------------------------------------------------------------

def test_pooled_rate_is_not_the_mean_of_rates():
    """The defect the review named: a large facility and a tiny one counted
    equally when their rates were averaged."""
    amu = pd.DataFrame([
        {"region": "A", "ddd_per_1000": 100.0, "patient_days": 100,
         "quantity_dispensed": 10},     # 10 DDD over 100 patient-days
        {"region": "A", "ddd_per_1000": 10.0, "patient_days": 10000,
         "quantity_dispensed": 100},    # 100 DDD over 10,000 patient-days
    ])
    pooled = consumption.pooled_ddd(amu, by="region")
    rate = pooled.table.iloc[0]["ddd_per_1000_patient_days"]

    naive = amu["ddd_per_1000"].mean()          # 55.0
    expected = (10 + 100) / (100 + 10000) * 1000  # about 10.9

    assert rate == pytest.approx(expected, rel=1e-6)
    assert abs(naive - rate) > 40, "the two methods must visibly differ here"


def test_records_without_a_denominator_are_excluded_not_zeroed():
    amu = pd.DataFrame([
        {"ddd_per_1000": 50.0, "patient_days": 1000},
        {"ddd_per_1000": 50.0, "patient_days": None},
        {"ddd_per_1000": None, "patient_days": 1000},
    ])
    pooled = consumption.pooled_ddd(amu)
    assert pooled.records_total == 3
    assert pooled.records_used == 1
    assert pooled.coverage == pytest.approx(100 / 3)
    assert "excluded from the rate" in pooled.caveat


def test_amc_pooled_ratio_uses_summed_biomass():
    amc = pd.DataFrame([
        {"species": "Poultry", "quantity_kg": 1.0, "biomass_kg": 1000.0},
        {"species": "Poultry", "quantity_kg": 1.0, "biomass_kg": 100000.0},
    ])
    pooled = consumption.pooled_mg_per_kg(amc, by="species")
    value = pooled.table.iloc[0]["mg_per_kg_biomass"]
    expected = (2 * consumption.MG_PER_KG) / (1000.0 + 100000.0)
    assert value == pytest.approx(expected, rel=1e-6)


def test_zero_denominator_does_not_divide():
    amu = pd.DataFrame([{"ddd_per_1000": 50.0, "patient_days": 0}])
    pooled = consumption.pooled_ddd(amu)
    assert pooled.records_used == 0
    assert not pooled.usable
