"""Expert rules: combinations that must never be reported.

These exist because the platform published this row, with a confidence interval:

    Escherichia coli   Vancomycin   n=35   91.4% susceptible

Each case below is a defect that reached production or was caught during
development, so the suite is a record of them as much as a check.
"""

import pandas as pd
import pytest

from src import expert_rules as er


# ---------------------------------------------------------------------------
# Combinations that are biologically impossible
# ---------------------------------------------------------------------------

IMPOSSIBLE = [
    # Gram-negatives against Gram-positive-only agents.
    ("Escherichia coli", "Vancomycin"),
    ("Klebsiella pneumoniae", "Vancomycin"),
    ("Pseudomonas aeruginosa", "Vancomycin"),
    ("Acinetobacter baumannii", "Vancomycin"),
    ("Escherichia coli", "Linezolid"),
    ("Klebsiella pneumoniae", "Linezolid"),
    ("Escherichia coli", "Daptomycin"),
    # Gram-positives against Gram-negative-only agents.
    ("Staphylococcus aureus", "Colistin"),
    ("Streptococcus pneumoniae", "Aztreonam"),
    ("Enterococcus faecalis", "Colistin"),
    # Genus-specific intrinsic resistance.
    ("Klebsiella pneumoniae", "Ampicillin"),
    ("Pseudomonas aeruginosa", "Ampicillin"),
    ("Pseudomonas aeruginosa", "Ertapenem"),
    ("Acinetobacter baumannii", "Aztreonam"),
    ("Enterococcus faecalis", "Ceftriaxone"),
    ("Proteus mirabilis", "Nitrofurantoin"),
    ("Proteus mirabilis", "Colistin"),
    ("Serratia marcescens", "Colistin"),
    ("Stenotrophomonas maltophilia", "Meropenem"),
]

#: The same organisms written the way laboratories abbreviate them. These were
#: missed entirely at one point: the abbreviated form matched no organism group,
#: so every rule passed it silently.
IMPOSSIBLE_ABBREVIATED = [
    ("E. coli", "Vancomycin"),
    ("K. pneumoniae", "Vancomycin"),
    ("K. pneumoniae", "Ampicillin"),
    ("P. aeruginosa", "Ertapenem"),
    ("S. aureus", "Colistin"),
    ("S. pneumoniae", "Aztreonam"),
    ("A. baumannii", "Aztreonam"),
    ("P. mirabilis", "Nitrofurantoin"),
    ("S. maltophilia", "Meropenem"),
]

#: Pairs that are real and must not be flagged. Klebsiella with colistin is the
#: important one: an organism-matching bug once classified Klebsiella as a
#: streptococcus, which suppressed the agent that matters most against
#: carbapenem-resistant Klebsiella.
LEGITIMATE = [
    ("Klebsiella pneumoniae", "Colistin"),
    ("K. pneumoniae", "Colistin"),
    ("Klebsiella pneumoniae", "Meropenem"),
    ("Klebsiella pneumoniae", "Nitrofurantoin"),
    ("Escherichia coli", "Ciprofloxacin"),
    ("Escherichia coli", "Ampicillin"),
    ("Escherichia coli", "Colistin"),
    ("Escherichia coli", "Nitrofurantoin"),
    ("Staphylococcus aureus", "Vancomycin"),
    ("Staphylococcus aureus", "Oxacillin"),
    ("Enterococcus faecium", "Vancomycin"),
    ("Enterococcus faecalis", "Ampicillin"),
    ("Pseudomonas aeruginosa", "Ceftazidime"),
    ("Pseudomonas aeruginosa", "Colistin"),
    ("Pseudomonas aeruginosa", "Meropenem"),
    ("Acinetobacter baumannii", "Colistin"),
    ("Salmonella enterica", "Ciprofloxacin"),
    ("Salmonella enterica", "Ceftriaxone"),
    ("Streptococcus pneumoniae", "Penicillin"),
    ("Campylobacter jejuni", "Erythromycin"),
    ("Serratia marcescens", "Meropenem"),
]

#: Active in vitro but not to be reported clinically.
SUPPRESSED = [
    ("Salmonella enterica", "Gentamicin"),
    ("Salmonella enterica", "Cefazolin"),
    ("Shigella flexneri", "Cefazolin"),
]


@pytest.mark.parametrize("organism,antibiotic", IMPOSSIBLE + IMPOSSIBLE_ABBREVIATED)
def test_impossible_combinations_are_errors(organism, antibiotic):
    finding = er.check_combination(organism, antibiotic)
    assert finding is not None, f"{organism} + {antibiotic} was not flagged"
    assert finding.is_error, f"{organism} + {antibiotic} should be an error"
    assert finding.reason, "a finding must explain itself"


@pytest.mark.parametrize("organism,antibiotic", LEGITIMATE)
def test_legitimate_combinations_pass(organism, antibiotic):
    finding = er.check_combination(organism, antibiotic)
    assert finding is None, (
        f"{organism} + {antibiotic} was wrongly flagged: "
        f"{finding.reason if finding else ''}")


@pytest.mark.parametrize("organism,antibiotic", SUPPRESSED)
def test_clinically_unreportable_are_suppressed_not_errors(organism, antibiotic):
    finding = er.check_combination(organism, antibiotic)
    assert finding is not None
    assert finding.severity == er.SEVERITY_SUPPRESS, (
        f"{organism} + {antibiotic} is real in vitro and should be suppressed, "
        "not reported as impossible")


# ---------------------------------------------------------------------------
# Organism grouping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("organism,expected", [
    ("Escherichia coli", "Enterobacterales"),
    ("E. coli", "Enterobacterales"),
    ("Klebsiella pneumoniae", "Enterobacterales"),
    ("K. pneumoniae", "Enterobacterales"),
    ("Streptococcus pneumoniae", "Streptococcus"),
    ("S. pneumoniae", "Streptococcus"),
    ("Staphylococcus aureus", "Staphylococcus"),
    ("S. aureus", "Staphylococcus"),
    ("Pseudomonas aeruginosa", "Pseudomonas"),
    ("Acinetobacter baumannii", "Acinetobacter"),
    ("Enterococcus faecalis", "Enterococcus"),
    ("Campylobacter coli", "Campylobacter"),
    ("C. coli", "Campylobacter"),
])
def test_organism_grouping(organism, expected):
    assert expected in er.organism_groups(organism)


def test_klebsiella_is_not_a_streptococcus():
    """The regression that suppressed Klebsiella + colistin.

    A pattern of ``pneumoniae$`` for Streptococcus pneumoniae also matched
    Klebsiella pneumoniae, so a Gram-negative was treated as a Gram-positive.
    """
    groups = er.organism_groups("Klebsiella pneumoniae")
    assert "Streptococcus" not in groups
    assert "Enterobacterales" in groups


def test_unknown_organism_is_not_guessed():
    assert er.check_combination("Martian bacillus", "Vancomycin") is None


# ---------------------------------------------------------------------------
# Frame-level screening
# ---------------------------------------------------------------------------

def test_screen_frame_counts_susceptible_results():
    frame = pd.DataFrame([
        {"organism": "Escherichia coli", "antibiotic": "Vancomycin", "result": "S"},
        {"organism": "Escherichia coli", "antibiotic": "Vancomycin", "result": "S"},
        {"organism": "Escherichia coli", "antibiotic": "Vancomycin", "result": "R"},
        {"organism": "Escherichia coli", "antibiotic": "Ciprofloxacin", "result": "S"},
    ])
    findings = er.screen_frame(frame)
    assert len(findings) == 1
    row = findings.iloc[0]
    assert row["antibiotic"] == "Vancomycin"
    assert row["observations"] == 3
    assert row["reported_susceptible"] == 2


def test_drop_unreportable_removes_only_the_offending_pair():
    frame = pd.DataFrame([
        {"organism": "Escherichia coli", "antibiotic": "Vancomycin", "result": "S"},
        {"organism": "Escherichia coli", "antibiotic": "Ciprofloxacin", "result": "S"},
    ])
    kept, findings = er.drop_unreportable(frame)
    assert len(kept) == 1
    assert kept.iloc[0]["antibiotic"] == "Ciprofloxacin"
    assert not findings.empty


def test_screen_frame_on_empty_input():
    assert er.screen_frame(pd.DataFrame()).empty
