"""Reading genomes against phenotypes.

The genomic tables were written by ingest and read by nothing, so none of this
logic had been exercised. These tests pin the decisions that are easy to get
subtly wrong and impossible to notice afterwards: what counts as agreement, what
absence of a gene is allowed to mean, and which genomes are permitted to
contribute to a published frequency.
"""

import pandas as pd
import pytest

from src import genomics as gx


def _genome(**overrides):
    row = {
        "dataset_id": "d1", "genomic_id": "SEQ-1", "isolate_id": "ISO-1",
        "organism": "Escherichia coli", "sector": "human",
        "specimen_type": "Blood", "lab_name": "Lab A",
        "amr_genes": [], "amr_mutations": [],
        "plasmid_replicons": [], "virulence_genes": [],
        "mean_depth": 80.0, "coverage_breadth": 98.0, "contamination_pct": 0.5,
        "n50": 120000, "contig_count": 60,
        "amr_db_name": "ResFinder", "amr_db_version": "2026-03-14",
        "sequence_type": "ST131", "cluster_id": None, "cluster_method": None,
        "collection_datetime": pd.Timestamp("2026-03-01", tz="UTC"),
    }
    row.update(overrides)
    return row


def _phenotype(isolate, agent, result):
    return {"dataset_id": "d1", "isolate_id": isolate,
            "antibiotic": agent, "result": result}


# ---------------------------------------------------------------------------
# Quality gating
# ---------------------------------------------------------------------------

def test_a_thin_assembly_fails():
    frame = gx.assess_quality(pd.DataFrame([_genome(mean_depth=8.0)]))
    assert frame.iloc[0]["qc_verdict"] == gx.QC_FAIL
    assert "depth" in frame.iloc[0]["qc_reason"]


def test_a_genome_with_no_metrics_is_not_a_pass():
    """Treating unmeasured as acceptable is how an unvetted assembly reaches a
    national figure."""
    bare = _genome(mean_depth=None, coverage_breadth=None,
                   contamination_pct=None, n50=None, contig_count=None)
    frame = gx.assess_quality(pd.DataFrame([bare]))
    assert frame.iloc[0]["qc_verdict"] == gx.QC_UNKNOWN
    assert frame.iloc[0]["qc_verdict"] != gx.QC_PASS


def test_failed_genomes_do_not_contribute_to_frequencies():
    """A poorly covered assembly misses genes that are present, so counting it
    understates every determinant it failed to find."""
    good = _genome(isolate_id="ISO-1", amr_genes=["blaCTX-M-15"])
    bad = _genome(isolate_id="ISO-2", genomic_id="SEQ-2", mean_depth=5.0,
                  amr_genes=[])
    frame = gx.assess_quality(pd.DataFrame([good, bad]))
    table = gx.determinant_frequency(frame)
    row = table[table["determinant"] == "blaCTX-M-15"].iloc[0]
    assert row["genomes_examined"] == 1, "the failed genome must not be a denominator"
    assert row["percent"] == 100.0


# ---------------------------------------------------------------------------
# Concordance
# ---------------------------------------------------------------------------

def test_determinant_with_resistance_is_explained():
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["blaCTX-M-15"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Ceftriaxone", "R")])
    table = gx.concordance(frame, phen)
    assert table.iloc[0]["verdict"] == gx.CONCORDANT_RESISTANT


def test_resistance_without_a_determinant_is_not_called_disagreement():
    """It is a statement about the method, not about the organism: the gene may
    be absent, absent from the database, or absent from the assembly."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=[])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Ceftriaxone", "R")])
    table = gx.concordance(frame, phen)
    assert table.iloc[0]["verdict"] == gx.PHENOTYPE_ONLY
    assert "no determinant identified" in gx.PHENOTYPE_ONLY


def test_intermediate_counts_as_non_susceptible():
    """For a mechanism question the split that matters is whether the drug
    reliably works, so I sits with R."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["blaCTX-M-15"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Ceftriaxone", "I")])
    table = gx.concordance(frame, phen)
    assert table.iloc[0]["verdict"] == gx.CONCORDANT_RESISTANT


def test_strong_determinant_against_susceptible_is_flagged():
    frame = gx.assess_quality(pd.DataFrame([_genome(
        organism="Staphylococcus aureus", amr_genes=["mecA"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Oxacillin", "S")])
    table = gx.concordance(frame, phen)
    assert table.iloc[0]["verdict"] == gx.GENOTYPE_ONLY
    assert bool(table.iloc[0]["notable"]), "mecA versus susceptible must be flagged"
    assert not gx.contradictions(table).empty


def test_a_weak_determinant_against_susceptible_is_not_flagged():
    """qnr genes raise an MIC without usually crossing the breakpoint. Flagging
    them would bury the contradictions that matter."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["qnrB1"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Ciprofloxacin", "S")])
    table = gx.concordance(frame, phen)
    assert table.iloc[0]["verdict"] == gx.GENOTYPE_ONLY
    assert not bool(table.iloc[0]["notable"])
    assert gx.contradictions(table).empty


def test_narrow_spectrum_beta_lactamase_does_not_explain_cephalosporins():
    """blaTEM-1 is a penicillinase. Letting it explain ceftriaxone resistance
    would hide genuinely unexplained ESBL phenotypes."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["blaTEM-1"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Ceftriaxone", "R")])
    table = gx.concordance(frame, phen)
    assert table.iloc[0]["verdict"] == gx.PHENOTYPE_ONLY


def test_agents_no_determinant_speaks_to_are_left_out():
    """Scoring the panel against an agent nothing predicts would mark every
    resistant result unexplained and say nothing about the data."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["blaCTX-M-15"])]))
    phen = pd.DataFrame([
        _phenotype("ISO-1", "Ceftriaxone", "R"),
        _phenotype("ISO-1", "Nitrofurantoin", "R"),   # nothing predicts it
    ])
    table = gx.concordance(frame, phen)
    assert set(table["antibiotic"]) == {"Ceftriaxone"}


def test_failed_genomes_are_excluded_from_concordance():
    """Their absent genes cannot be told from genes the assembly missed, so
    scoring them manufactures discrepancies out of sequencing depth."""
    frame = gx.assess_quality(pd.DataFrame([_genome(mean_depth=4.0, amr_genes=[])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Ceftriaxone", "R")])
    assert gx.concordance(frame, phen).empty


def test_summary_reports_both_kinds_of_disagreement():
    rows = [
        _genome(isolate_id="A", genomic_id="S1", amr_genes=["blaCTX-M-15"]),
        _genome(isolate_id="B", genomic_id="S2", amr_genes=[]),
    ]
    phen = pd.DataFrame([_phenotype("A", "Ceftriaxone", "R"),
                         _phenotype("B", "Ceftriaxone", "R")])
    table = gx.concordance(gx.assess_quality(pd.DataFrame(rows)), phen)
    summary = gx.concordance_summary(table)
    assert summary["explained_resistance"] == 1
    assert summary["resistance_unexplained"] == 1
    assert summary["agreement_percent"] is not None


# ---------------------------------------------------------------------------
# Determinants and clusters
# ---------------------------------------------------------------------------

def test_frequency_denominator_is_genomes_not_gene_calls():
    rows = [
        _genome(isolate_id="A", genomic_id="S1",
                amr_genes=["blaCTX-M-15", "sul1", "tet(A)"]),
        _genome(isolate_id="B", genomic_id="S2", amr_genes=["blaCTX-M-15"]),
    ]
    table = gx.determinant_frequency(gx.assess_quality(pd.DataFrame(rows)))
    row = table[table["determinant"] == "blaCTX-M-15"].iloc[0]
    assert row["isolates"] == 2 and row["genomes_examined"] == 2
    assert row["percent"] == 100.0


def test_frequency_carries_the_database_version():
    """A gene call is a statement about what a database contained on a day."""
    table = gx.determinant_frequency(
        gx.assess_quality(pd.DataFrame([_genome(amr_genes=["mcr-1"])])))
    assert "2026-03-14" in table.iloc[0]["database"]


def test_unmapped_determinants_are_listed_not_silently_dropped():
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["blaFOO-99"])]))
    assert gx.determinants_not_in_rules(frame) == ["blaFOO-99"]


def test_clusters_group_shared_ids_and_count_sectors():
    rows = [
        _genome(isolate_id="A", genomic_id="S1", cluster_id="CL-1",
                cluster_method="SNP", sector="human"),
        _genome(isolate_id="B", genomic_id="S2", cluster_id="CL-1",
                cluster_method="SNP", sector="environment"),
        _genome(isolate_id="C", genomic_id="S3", cluster_id=None),
    ]
    report = gx.clusters(gx.assess_quality(pd.DataFrame(rows)))
    assert len(report.clusters) == 1
    assert report.clusters.iloc[0]["isolates"] == 2
    assert report.clusters.iloc[0]["sectors"] == 2
    assert report.unclustered == 1


def test_cluster_summary_does_not_claim_direction():
    """Cluster membership is symmetric. Reading direction into it is the
    difference between a correct and an incorrect outbreak response."""
    rows = [
        _genome(isolate_id="A", genomic_id="S1", cluster_id="CL-1",
                cluster_method="SNP", sector="human"),
        _genome(isolate_id="B", genomic_id="S2", cluster_id="CL-1",
                cluster_method="SNP", sector="environment"),
    ]
    summary = gx.clusters(gx.assess_quality(pd.DataFrame(rows))).summary
    assert "not direction" in summary


def test_no_clusters_says_so_rather_than_showing_an_empty_table():
    frame = gx.assess_quality(pd.DataFrame([_genome(cluster_id=None)]))
    report = gx.clusters(frame)
    assert report.clusters.empty
    assert "No clusters" in report.summary


def test_every_determinant_rule_names_a_mechanism():
    for determinant in gx.DETERMINANTS:
        assert determinant.gene and determinant.agents and determinant.mechanism


# ---------------------------------------------------------------------------
# The extended rule set
#
# Added after running at scale showed five of the six most common determinants
# in the data had no rule, so they explained nothing and some "unexplained
# resistance" was simply an unmapped gene.
# ---------------------------------------------------------------------------

def test_oxacillinase_explains_the_inhibitor_combinations_only():
    """blaOXA-1 is poorly inhibited by clavulanate and tazobactam, so it
    accounts for those combinations. Reading it as a general beta-lactamase
    would explain away cephalosporin resistance it has nothing to do with."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["blaOXA-1"])]))
    phen = pd.DataFrame([
        _phenotype("ISO-1", "Amoxicillin-Clavulanate", "R"),
        _phenotype("ISO-1", "Ceftriaxone", "R"),
        _phenotype("ISO-1", "Meropenem", "R"),
    ])
    table = gx.concordance(frame, phen).set_index("antibiotic")
    assert table.loc["Amoxicillin-Clavulanate", "verdict"] == gx.CONCORDANT_RESISTANT
    assert table.loc["Ceftriaxone", "verdict"] == gx.PHENOTYPE_ONLY
    assert table.loc["Meropenem", "verdict"] == gx.PHENOTYPE_ONLY


def test_streptomycin_enzymes_do_not_explain_gentamicin():
    """strA and strB act on streptomycin. Treating them as general
    aminoglycoside resistance would hide a real 16S methylase."""
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["aph(3'')-Ib",
                                                               "aph(6)-Id"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Streptomycin", "R"),
                         _phenotype("ISO-1", "Gentamicin", "R")])
    table = gx.concordance(frame, phen).set_index("antibiotic")
    assert table.loc["Streptomycin", "verdict"] == gx.CONCORDANT_RESISTANT
    assert table.loc["Gentamicin", "verdict"] == gx.PHENOTYPE_ONLY


def test_staphylococcal_penicillinase_does_not_explain_oxacillin():
    """blaZ gives penicillin resistance; oxacillin resistance needs mec."""
    frame = gx.assess_quality(pd.DataFrame([_genome(
        organism="Staphylococcus aureus", amr_genes=["blaZ"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Penicillin", "R"),
                         _phenotype("ISO-1", "Oxacillin", "R")])
    table = gx.concordance(frame, phen).set_index("antibiotic")
    assert table.loc["Penicillin", "verdict"] == gx.CONCORDANT_RESISTANT
    assert table.loc["Oxacillin", "verdict"] == gx.PHENOTYPE_ONLY


def test_intrinsic_oxacillinase_is_not_treated_as_carbapenem_resistance():
    """blaOXA-51 identifies A. baumannii. On its own it gives little or no
    carbapenem resistance, so a susceptible result is expected."""
    frame = gx.assess_quality(pd.DataFrame([_genome(
        organism="Acinetobacter baumannii", amr_genes=["blaOXA-51"])]))
    phen = pd.DataFrame([_phenotype("ISO-1", "Meropenem", "S")])
    table = gx.concordance(frame, phen)
    assert not bool(table.iloc[0]["notable"]), "an intrinsic marker must not be flagged"


def test_markers_that_confer_no_resistance_are_named_not_left_unmapped():
    """qacE is disinfectant tolerance and an integron marker. Listing it as a
    determinant with no rule implies the rule set is incomplete when it is not."""
    frame = gx.assess_quality(pd.DataFrame([_genome(
        amr_genes=["qacE", "intI1", "sitABCD"])]))
    assert gx.determinants_not_in_rules(frame) == []
    found = gx.non_resistance_markers_found(frame)
    assert set(found) == {"qacE", "intI1", "sitABCD"}
    assert all(text for text in found.values()), "each must carry an explanation"


def test_non_resistance_markers_are_labelled_in_the_frequency_table():
    frame = gx.assess_quality(pd.DataFrame([_genome(amr_genes=["qacE"])]))
    table = gx.determinant_frequency(frame)
    assert table.iloc[0]["mechanism"] == "not a resistance determinant"


def test_a_genuinely_unknown_gene_is_still_reported_as_unmapped():
    """The two categories must stay distinct: classifying something as
    not-resistance is a decision, not a way of emptying the list."""
    frame = gx.assess_quality(pd.DataFrame([_genome(
        amr_genes=["qacE", "blaNEW-1"])]))
    assert gx.determinants_not_in_rules(frame) == ["blaNEW-1"]
