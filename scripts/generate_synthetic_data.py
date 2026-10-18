"""
Generate a synthetic surveillance dataset for testing the platform.

Why synthetic data, and what it is for
--------------------------------------
The platform's clinical fields -- ward, specimen type, age, sex, admission date
-- are empty for every backfilled record, because the old format never collected
them. Nothing on the ward, age or patient-linkage views can be exercised against
real data, so this generates a dataset that can.

**Every record produced here is invented.** Nothing in it is an observation about
any patient, laboratory, facility or place in Ghana. The dataset exists to prove
that the software behaves correctly, and its resistance percentages must never be
quoted as findings. It is written into its own dataset so it can be deleted in
one action, and every dataset name it creates begins with SYNTHETIC.

Design
------
The data is built to be *plausible* rather than random, because a generator that
emits uniform noise tests nothing: every rate lands near 50%, no stratum differs
from another, and a bug that flattens a real signal would not show.

So it carries structure the analytics should find:

* resistance that differs by ward -- intensive care worse than outpatients,
  which is the comparison the clinical fields were added for;
* organism mixes that differ by specimen type, so urine is dominated by E. coli
  and blood carries more Klebsiella and staphylococci;
* a resistance trend over time for one organism-agent pair, so the period
  comparison and the baseline signal rule have something real to detect;
* patients with repeat specimens, so CLSI M39 deduplication removes something;
* an outbreak-shaped cluster of one resistant clone in one ward.

And it deliberately carries the faults a surveillance system must catch:

* a small number of biologically impossible results, so the expert rules fire;
* missing fields at realistic rates, so the completeness report has something to
  report;
* failed quality control, rejected specimens, and culture-negative specimens.

Usage
-----
    python scripts/generate_synthetic_data.py --specimens 2500
    python scripts/generate_synthetic_data.py --specimens 2500 --workbook out.xlsx
    python scripts/generate_synthetic_data.py --delete

The default path validates and ingests through the application's own upload
pipeline, so a successful run is also a test that the pipeline works.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from src.kobo_form import (  # noqa: E402
    ANIMAL_SPECIES, FOOD_COMMODITIES, FOOD_STAGES, GHANA_REGIONS,
    PRODUCTION_TYPES, TREATMENT_STAGES,
)
from src.lab_management import APPROVED_LABS  # noqa: E402
from src.traceability import (  # noqa: E402
    IDENTIFICATION_METHODS, PATIENT_TYPES, SAMPLING_PURPOSES, SPECIMEN_TYPES,
    WARD_TYPES,
)

DATASET_PREFIX = "SYNTHETIC"

#: Fixed so a run is reproducible and two runs can be compared.
DEFAULT_SEED = 20260928

# ---------------------------------------------------------------------------
# Clinical structure
# ---------------------------------------------------------------------------

#: Organism mix by specimen type. Urine is overwhelmingly E. coli; blood carries
#: more Klebsiella and staphylococci. A flat mix would make specimen-type
#: stratification meaningless.
ORGANISM_BY_SPECIMEN: Dict[str, List[Tuple[str, float]]] = {
    "Urine": [("Escherichia coli", 0.55), ("Klebsiella pneumoniae", 0.15),
              ("Enterococcus faecalis", 0.10), ("Proteus mirabilis", 0.08),
              ("Pseudomonas aeruginosa", 0.06), ("Staphylococcus aureus", 0.06)],
    "Blood": [("Klebsiella pneumoniae", 0.22), ("Staphylococcus aureus", 0.20),
              ("Escherichia coli", 0.18), ("Salmonella enterica", 0.12),
              ("Acinetobacter baumannii", 0.10),
              ("Streptococcus pneumoniae", 0.10),
              ("Pseudomonas aeruginosa", 0.08)],
    "Wound/Pus": [("Staphylococcus aureus", 0.38), ("Pseudomonas aeruginosa", 0.18),
                  ("Escherichia coli", 0.14), ("Klebsiella pneumoniae", 0.12),
                  ("Proteus mirabilis", 0.10), ("Enterococcus faecalis", 0.08)],
    "Respiratory": [("Klebsiella pneumoniae", 0.26),
                    ("Streptococcus pneumoniae", 0.22),
                    ("Pseudomonas aeruginosa", 0.18),
                    ("Acinetobacter baumannii", 0.16),
                    ("Staphylococcus aureus", 0.10),
                    ("Haemophilus influenzae", 0.08)],
    "Stool": [("Salmonella enterica", 0.40), ("Shigella flexneri", 0.24),
              ("Campylobacter jejuni", 0.22), ("Escherichia coli", 0.14)],
    "CSF": [("Streptococcus pneumoniae", 0.44),
            ("Neisseria meningitidis", 0.24),
            ("Klebsiella pneumoniae", 0.18), ("Escherichia coli", 0.14)],
    "Sterile fluid": [("Staphylococcus aureus", 0.32),
                      ("Escherichia coli", 0.26),
                      ("Klebsiella pneumoniae", 0.24),
                      ("Enterococcus faecalis", 0.18)],
    "Device tip": [("Staphylococcus aureus", 0.36),
                   ("Acinetobacter baumannii", 0.26),
                   ("Klebsiella pneumoniae", 0.22),
                   ("Pseudomonas aeruginosa", 0.16)],
}

#: Specimen mix by ward type. Intensive care draws blood and respiratory
#: specimens; outpatients are mostly urine.
SPECIMEN_BY_WARD: Dict[str, List[Tuple[str, float]]] = {
    "ICU": [("Blood", 0.34), ("Respiratory", 0.30), ("Device tip", 0.14),
            ("Urine", 0.12), ("Wound/Pus", 0.10)],
    "Neonatal": [("Blood", 0.52), ("CSF", 0.18), ("Respiratory", 0.16),
                 ("Urine", 0.14)],
    "Surgical": [("Wound/Pus", 0.46), ("Blood", 0.18), ("Urine", 0.18),
                 ("Sterile fluid", 0.18)],
    "Medical": [("Urine", 0.34), ("Blood", 0.26), ("Respiratory", 0.22),
                ("Stool", 0.18)],
    "Paediatric": [("Blood", 0.30), ("Stool", 0.26), ("Urine", 0.24),
                   ("CSF", 0.10), ("Respiratory", 0.10)],
    "Obstetric/Gynaecology": [("Urine", 0.52), ("Wound/Pus", 0.26),
                              ("Blood", 0.22)],
    "Emergency": [("Blood", 0.36), ("Urine", 0.32), ("Wound/Pus", 0.18),
                  ("Stool", 0.14)],
    "Oncology/Haematology": [("Blood", 0.54), ("Urine", 0.20),
                             ("Respiratory", 0.14), ("Device tip", 0.12)],
    "Burns": [("Wound/Pus", 0.62), ("Blood", 0.24), ("Device tip", 0.14)],
    "Outpatient": [("Urine", 0.56), ("Stool", 0.22), ("Wound/Pus", 0.16),
                   ("Respiratory", 0.06)],
}

#: Ward mix. Outpatients and medical wards dominate volume, as they do in
#: practice; intensive care is a small share with the worst resistance.
WARD_MIX: List[Tuple[str, float]] = [
    ("Outpatient", 0.26), ("Medical", 0.20), ("Paediatric", 0.13),
    ("Surgical", 0.12), ("Emergency", 0.09), ("Obstetric/Gynaecology", 0.07),
    ("ICU", 0.06), ("Neonatal", 0.04), ("Oncology/Haematology", 0.02),
    ("Burns", 0.01),
]

#: Multiplier on baseline resistance by ward. The signal the clinical fields
#: exist to reveal: intensive care and burns are materially worse than
#: outpatients.
WARD_RESISTANCE_FACTOR: Dict[str, float] = {
    "ICU": 1.95, "Burns": 1.85, "Neonatal": 1.55,
    "Oncology/Haematology": 1.50, "Surgical": 1.25, "Emergency": 1.10,
    "Medical": 1.00, "Obstetric/Gynaecology": 0.85, "Paediatric": 0.85,
    "Outpatient": 0.60,
}

#: Baseline probability that an isolate is non-susceptible, per organism and
#: agent, before the ward factor is applied. Shaped to resemble published
#: Ghanaian and West African patterns: very high aminopenicillin resistance in
#: Enterobacterales, carbapenems still largely active, colistin nearly always
#: active.
BASE_RESISTANCE: Dict[str, Dict[str, float]] = {
    "Escherichia coli": {
        "Ampicillin": 0.88, "Amoxicillin-Clavulanate": 0.52,
        "Ceftriaxone": 0.46, "Cefepime": 0.38, "Ceftazidime": 0.40,
        "Ciprofloxacin": 0.58, "Levofloxacin": 0.50, "Gentamicin": 0.36,
        "Amikacin": 0.10, "Meropenem": 0.05, "Ertapenem": 0.06,
        "Piperacillin-Tazobactam": 0.22, "Trimethoprim-Sulfamethoxazole": 0.74,
        "Nitrofurantoin": 0.12, "Colistin": 0.02, "Tigecycline": 0.04,
    },
    "Klebsiella pneumoniae": {
        "Amoxicillin-Clavulanate": 0.62, "Ceftriaxone": 0.58, "Cefepime": 0.48,
        "Ceftazidime": 0.52, "Ciprofloxacin": 0.52, "Levofloxacin": 0.46,
        "Gentamicin": 0.44, "Amikacin": 0.16, "Meropenem": 0.14,
        "Ertapenem": 0.18, "Piperacillin-Tazobactam": 0.36,
        "Trimethoprim-Sulfamethoxazole": 0.68, "Colistin": 0.04,
        "Tigecycline": 0.08,
    },
    "Staphylococcus aureus": {
        "Penicillin": 0.92, "Oxacillin": 0.34, "Cefoxitin": 0.34,
        "Erythromycin": 0.44, "Clindamycin": 0.30, "Ciprofloxacin": 0.36,
        "Gentamicin": 0.24, "Trimethoprim-Sulfamethoxazole": 0.28,
        "Tetracycline": 0.38, "Vancomycin": 0.01, "Linezolid": 0.01,
        "Rifampicin": 0.08,
    },
    "Pseudomonas aeruginosa": {
        "Ceftazidime": 0.34, "Cefepime": 0.32, "Meropenem": 0.26,
        "Imipenem": 0.28, "Ciprofloxacin": 0.38, "Levofloxacin": 0.36,
        "Gentamicin": 0.34, "Amikacin": 0.18,
        "Piperacillin-Tazobactam": 0.30, "Colistin": 0.03,
    },
    "Acinetobacter baumannii": {
        "Ceftazidime": 0.72, "Cefepime": 0.70, "Meropenem": 0.62,
        "Imipenem": 0.60, "Ciprofloxacin": 0.74, "Levofloxacin": 0.70,
        "Gentamicin": 0.66, "Amikacin": 0.52,
        "Trimethoprim-Sulfamethoxazole": 0.68, "Colistin": 0.05,
        "Tigecycline": 0.22,
    },
    "Enterococcus faecalis": {
        "Ampicillin": 0.12, "Penicillin": 0.16, "Vancomycin": 0.04,
        "Linezolid": 0.02, "Tetracycline": 0.58, "Ciprofloxacin": 0.44,
        "Levofloxacin": 0.42,
    },
    "Streptococcus pneumoniae": {
        "Penicillin": 0.28, "Ceftriaxone": 0.12, "Erythromycin": 0.34,
        "Clindamycin": 0.22, "Levofloxacin": 0.06, "Vancomycin": 0.00,
        "Trimethoprim-Sulfamethoxazole": 0.52, "Tetracycline": 0.40,
    },
    "Salmonella enterica": {
        "Ampicillin": 0.54, "Ceftriaxone": 0.18, "Ciprofloxacin": 0.26,
        "Trimethoprim-Sulfamethoxazole": 0.48, "Chloramphenicol": 0.30,
        "Azithromycin": 0.10, "Meropenem": 0.02,
    },
    "Shigella flexneri": {
        "Ampicillin": 0.72, "Ceftriaxone": 0.22, "Ciprofloxacin": 0.30,
        "Trimethoprim-Sulfamethoxazole": 0.80, "Azithromycin": 0.18,
    },
    "Campylobacter jejuni": {
        "Ciprofloxacin": 0.62, "Erythromycin": 0.14, "Tetracycline": 0.48,
        "Azithromycin": 0.16, "Gentamicin": 0.06,
    },
    "Proteus mirabilis": {
        "Ampicillin": 0.58, "Amoxicillin-Clavulanate": 0.30, "Ceftriaxone": 0.26,
        "Ciprofloxacin": 0.40, "Gentamicin": 0.32, "Meropenem": 0.04,
        "Trimethoprim-Sulfamethoxazole": 0.62,
    },
    "Neisseria meningitidis": {
        "Penicillin": 0.14, "Ceftriaxone": 0.02, "Ciprofloxacin": 0.08,
        "Chloramphenicol": 0.06,
    },
    "Haemophilus influenzae": {
        "Ampicillin": 0.42, "Amoxicillin-Clavulanate": 0.14, "Ceftriaxone": 0.02,
        "Azithromycin": 0.12, "Trimethoprim-Sulfamethoxazole": 0.46,
    },
}

#: Agents a laboratory would report for each organism, as a realistic panel.
PANEL: Dict[str, List[str]] = {
    organism: list(agents) for organism, agents in BASE_RESISTANCE.items()
}

#: Organism-agent pairs that must never be reported. A handful are injected on
#: purpose so the expert rules have something to catch and the data-quality page
#: has something to show.
IMPLAUSIBLE_PAIRS: List[Tuple[str, str]] = [
    ("Escherichia coli", "Vancomycin"),
    ("Klebsiella pneumoniae", "Linezolid"),
    ("Pseudomonas aeruginosa", "Ampicillin"),
    ("Acinetobacter baumannii", "Vancomycin"),
    ("Staphylococcus aureus", "Colistin"),
    ("Klebsiella pneumoniae", "Ampicillin"),
]

NON_HUMAN_ORGANISMS: Dict[str, List[Tuple[str, float]]] = {
    "animal": [("Escherichia coli", 0.42), ("Salmonella enterica", 0.24),
               ("Campylobacter jejuni", 0.18), ("Staphylococcus aureus", 0.16)],
    "food": [("Escherichia coli", 0.36), ("Salmonella enterica", 0.32),
             ("Campylobacter jejuni", 0.18), ("Staphylococcus aureus", 0.14)],
    "environment": [("Escherichia coli", 0.52), ("Klebsiella pneumoniae", 0.22),
                    ("Pseudomonas aeruginosa", 0.16),
                    ("Acinetobacter baumannii", 0.10)],
    "aquaculture": [("Escherichia coli", 0.44), ("Salmonella enterica", 0.28),
                    ("Pseudomonas aeruginosa", 0.28)],
}

BREAKPOINT_EDITIONS = [("CLSI", "M100-Ed35 (2025)"), ("CLSI", "M100-Ed34 (2024)"),
                       ("EUCAST", "v15.0 (2025)")]


# ---------------------------------------------------------------------------
# Consumption and prescribing structure (AMU, AMC, PPS)
#
# These three sheets exist to exercise src.consumption, which was rewritten to
# pool rates -- sum(numerator) / sum(denominator) -- instead of averaging
# row-level rates. A mean of rates and a pooled rate are the same number only
# when every denominator is equal, so data with equal denominators would let the
# old arithmetic pass unnoticed. The structure below therefore makes the
# denominators deliberately unequal, and correlates small denominators with high
# rates, which is the shape that makes mean-of-rates overstate consumption.
# ---------------------------------------------------------------------------

#: Human facilities reporting antimicrobial use: name, region, district, typical
#: monthly occupied-bed-days, and the DDD/1000 band they report in.
#:
#: Korle-Bu records roughly twenty times the patient-days of Eikwe while
#: reporting a third of its rate. Averaging the facility rates therefore gives a
#: national figure pulled towards the smallest hospitals; pooling gives one
#: dominated by the largest, which is the correct answer and a visibly different
#: number.
AMU_FACILITIES: List[Tuple[str, str, str, int, float, float]] = [
    ("Korle-Bu Teaching Hospital",             "Greater Accra", "Ablekuma South", 38000, 280, 430),
    ("Komfo Anokye Teaching Hospital",         "Ashanti",       "Kumasi Metro",   32000, 310, 460),
    ("Tamale Teaching Hospital",               "Northern",      "Tamale Metro",   21000, 350, 520),
    ("Ho Teaching Hospital",                   "Volta",         "Ho Municipal",   14000, 390, 560),
    ("Cape Coast Teaching Hospital",           "Central",       "Cape Coast",     13000, 400, 580),
    ("Sunyani Teaching Hospital",              "Bono",          "Sunyani Munic.",  9000, 470, 660),
    ("Eastern Regional Hospital",              "Eastern",       "New Juaben",      7000, 520, 720),
    ("Lekma Hospital",                         "Greater Accra", "Ledzokuku",       3000, 880, 1180),
    ("St. Martin De Porres Hospital Eikwe",    "Western",       "Ellembelle",      1800, 950, 1400),
]

#: Antibiotic, ATC code, WHO AWaRe category, formulation.
AMU_AGENTS: List[Tuple[str, str, str, str]] = [
    ("Amoxicillin",              "J01CA04", "Access",  "Capsule"),
    ("Amoxicillin/Clavulanate",  "J01CR02", "Access",  "Tablet"),
    ("Metronidazole",            "J01XD01", "Access",  "Infusion"),
    ("Gentamicin",               "J01GB03", "Access",  "Injection"),
    ("Ceftriaxone",              "J01DD04", "Watch",   "Injection"),
    ("Ciprofloxacin",            "J01MA02", "Watch",   "Tablet"),
    ("Azithromycin",             "J01FA10", "Watch",   "Tablet"),
    ("Vancomycin",               "J01XA01", "Watch",   "Infusion"),
    ("Meropenem",                "J01DH02", "Watch",   "Injection"),
    ("Colistin",                 "J01XB01", "Reserve", "Infusion"),
]

#: Animal and aquaculture strata: species, sector, production type, typical
#: biomass in kilograms per reporting period, and the mg/kg band.
#:
#: Biomass spans four orders of magnitude here, from broiler flocks to a handful
#: of village goats. Goats carry the highest row-level mg/kg and by far the
#: smallest biomass, so they top a table of averaged rates and fall well down a
#: pooled one -- the reordering that showed the original calculation was wrong.
AMC_STRATA: List[Tuple[str, str, str, int, float, float]] = [
    ("Poultry (broiler)", "ANIMAL",      "Intensive commercial",    2400000,  70, 110),
    ("Poultry (layer)",   "ANIMAL",      "Intensive commercial",    1100000,  60,  95),
    ("Cattle",            "ANIMAL",      "Semi-intensive",          1800000,  30,  60),
    ("Pig",               "ANIMAL",      "Intensive commercial",     600000, 110, 175),
    ("Sheep",             "ANIMAL",      "Backyard / smallholder",   120000,  95, 150),
    ("Goat",              "ANIMAL",      "Backyard / smallholder",    90000, 640, 1150),
    ("Tilapia",           "AQUACULTURE", "Cage aquaculture",         300000, 140, 230),
    ("Catfish",           "AQUACULTURE", "Pond aquaculture",          80000, 200, 320),
]

#: Veterinary agents: name, class, ATCvet code, route, purpose.
AMC_AGENTS: List[Tuple[str, str, str, str, str]] = [
    ("Oxytetracycline", "Tetracyclines",   "QJ01AA06", "In water", "Therapeutic"),
    ("Doxycycline",     "Tetracyclines",   "QJ01AA02", "In feed",  "Therapeutic"),
    ("Enrofloxacin",    "Fluoroquinolones","QJ01MA90", "In water", "Therapeutic"),
    ("Tylosin",         "Macrolides",      "QJ01FA90", "In feed",  "Growth promotion"),
    ("Sulfadiazine/Trimethoprim", "Sulfonamides", "QJ01EW10", "In water", "Therapeutic"),
    ("Amoxicillin",     "Penicillins",     "QJ01CA04", "In feed",  "Metaphylaxis"),
    ("Colistin",        "Polymyxins",      "QJ01XB01", "In water", "Metaphylaxis"),
    ("Florfenicol",     "Amphenicols",     "QJ01BA90", "In feed",  "Therapeutic"),
]

#: Ward, share of prescriptions, documented-indication rate, guideline-compliance
#: rate. Compliance differs by ward so the PPS stratification has something real
#: to separate -- surgical prophylaxis is the classic weak point.
PPS_WARDS: List[Tuple[str, float, float, float]] = [
    ("Medical",                0.30, 0.78, 0.72),
    ("Surgical",               0.26, 0.61, 0.48),
    ("Paediatric",             0.18, 0.82, 0.75),
    ("Obstetric/Gynaecology",  0.14, 0.70, 0.64),
    ("ICU",                    0.12, 0.86, 0.55),
]

PPS_AGE_GROUPS: List[Tuple[str, float]] = [
    ("<1", 0.08), ("1-4", 0.10), ("5-14", 0.09), ("15-44", 0.33),
    ("45-64", 0.24), ("65+", 0.16),
]

PPS_INDICATIONS: List[Tuple[str, float]] = [
    ("Community-acquired pneumonia", 0.17),
    ("Hospital-acquired pneumonia",  0.09),
    ("Urinary tract infection",      0.16),
    ("Skin and soft tissue infection", 0.12),
    ("Surgical prophylaxis",         0.20),
    ("Sepsis",                       0.11),
    ("Intra-abdominal infection",    0.09),
    ("Meningitis",                   0.06),
]

PPS_ROUTES: List[Tuple[str, float]] = [("IV", 0.56), ("Oral", 0.36), ("IM", 0.08)]


def _pick(rng: random.Random, weighted: Sequence[Tuple[str, float]]) -> str:
    values = [v for v, _ in weighted]
    weights = [w for _, w in weighted]
    return rng.choices(values, weights=weights, k=1)[0]


class Generator:
    """Builds the dataset. Seeded, so a run is reproducible."""

    def __init__(self, specimens: int, seed: int = DEFAULT_SEED,
                 months: int = 30):
        self.n = specimens
        self.rng = random.Random(seed)
        self.months = months
        self.end = date(2026, 9, 1)
        self.start = self.end - timedelta(days=int(30.44 * months))
        self.labs = sorted(APPROVED_LABS.keys())
        self.samples: List[Dict] = []
        self.isolates: List[Dict] = []
        self.ast: List[Dict] = []
        self.genomics: List[Dict] = []
        #: Consumption and prescribing, built after run().
        self.amu: List[Dict] = []
        self.amc: List[Dict] = []
        self.pps_surveys: List[Dict] = []
        self.pps_prescriptions: List[Dict] = []
        #: Patients who will contribute more than one specimen, so that
        #: deduplication has something to remove.
        self.repeat_patients: List[Tuple[str, str]] = []
        self.stats: Dict[str, int] = {
            "implausible_results": 0, "qc_failures": 0, "rejected": 0,
            "culture_negative": 0, "repeat_specimens": 0, "outbreak_isolates": 0,
            "amu_missing_denominator": 0, "amc_small_denominator": 0,
            "pps_surveys": 0,
        }

    # -- helpers ---------------------------------------------------------
    def _date(self) -> date:
        span = (self.end - self.start).days
        return self.start + timedelta(days=self.rng.randint(0, span))

    def _resistance_probability(self, organism: str, agent: str,
                                ward: Optional[str], when: date) -> float:
        base = BASE_RESISTANCE.get(organism, {}).get(agent, 0.3)
        factor = WARD_RESISTANCE_FACTOR.get(ward or "", 1.0)
        # A rising trend for one pair, so the period comparison and the
        # above-baseline signal rule have a real change to find.
        if organism == "Klebsiella pneumoniae" and agent == "Meropenem":
            elapsed = (when - self.start).days / max((self.end - self.start).days, 1)
            factor *= 1.0 + 1.8 * elapsed
        return max(0.0, min(0.97, base * factor))

    def _result(self, probability: float) -> str:
        roll = self.rng.random()
        if roll < probability:
            return "R"
        if roll < probability + 0.07:
            return "I"
        return "S"

    def _measurement(self, result: str) -> Tuple[str, Optional[float], Optional[float]]:
        """A measurement consistent with the interpretation."""
        if self.rng.random() < 0.55:
            zone = {"R": self.rng.randint(6, 13), "I": self.rng.randint(14, 17),
                    "S": self.rng.randint(18, 34)}[result]
            return "DD", None, float(zone)
        mic = {"R": self.rng.choice([16, 32, 64, 128]),
               "I": self.rng.choice([2, 4, 8]),
               "S": self.rng.choice([0.03, 0.06, 0.125, 0.25, 0.5, 1])}[result]
        return "MIC", float(mic), None

    # -- generation ------------------------------------------------------
    def run(self) -> None:
        sector_mix = [("human", 0.62), ("animal", 0.13), ("food", 0.12),
                      ("environment", 0.09), ("aquaculture", 0.04)]
        for index in range(self.n):
            sector = _pick(self.rng, sector_mix)
            if sector == "human":
                self._human_specimen(index)
            else:
                self._non_human_specimen(index, sector)
        self._outbreak_cluster()

    def _human_specimen(self, index: int, *, patient: Optional[Tuple[str, str]] = None,
                        forced_ward: Optional[str] = None,
                        forced_date: Optional[date] = None) -> None:
        lab = self.rng.choice(self.labs)
        region = self.rng.choice(GHANA_REGIONS)
        when = forced_date or self._date()
        ward = forced_ward or _pick(self.rng, WARD_MIX)
        specimen_type = _pick(self.rng, SPECIMEN_BY_WARD[ward])

        if patient is None:
            facility = f"FAC{self.rng.randint(1, 18):02d}"
            patient_id = f"MRN-{self.rng.randint(100000, 999999)}"
            # A tenth of patients are remembered so they can return later with
            # a second specimen, which is what deduplication acts on.
            if self.rng.random() < 0.10:
                self.repeat_patients.append((facility, patient_id))
        else:
            facility, patient_id = patient
            self.stats["repeat_specimens"] += 1

        if ward == "Neonatal":
            age_years = round(self.rng.uniform(0, 0.08), 3)
        elif ward == "Paediatric":
            age_years = float(self.rng.randint(1, 14))
        elif ward == "Obstetric/Gynaecology":
            age_years = float(self.rng.randint(16, 44))
        else:
            age_years = float(self.rng.randint(16, 92))

        admission = when - timedelta(days=self.rng.randint(0, 12))
        sample_id = f"SYN-H-{index:06d}"

        # Receipt must never precede collection: the schema enforces it, and an
        # earlier version generated a collection time against a midnight receipt
        # on the same day, which the CHECK constraint correctly refused. Receipt
        # is therefore derived forward from collection.
        collection_hour = self.rng.randint(6, 19)
        collection_minute = self.rng.choice(["00", "15", "30", "45"])
        transit_hours = self.rng.choice([1, 2, 2, 3, 4, 6, 20, 30])
        total_hour = collection_hour + transit_hours
        receipt_day = when + timedelta(days=total_hour // 24)
        receipt_hour = total_hour % 24
        receipt_minute = self.rng.choice(["00", "15", "30", "45"])

        rejected = self.rng.random() < 0.02
        condition = "Rejected" if rejected else self.rng.choices(
            ["Acceptable", "Suboptimal"], weights=[0.94, 0.06], k=1)[0]
        if rejected:
            self.stats["rejected"] += 1

        row = {
            "sample_id": sample_id, "lab_name": lab,
            "collection_date": when.isoformat(),
            "collection_time": f"{collection_hour:02d}:{collection_minute}",
            "source_category": "HUMAN", "source_type": "clinical_specimen",
            "site_type": "Hospital", "region": region,
            "district": f"{region} district {self.rng.randint(1, 6)}",
            "specimen_type": specimen_type,
            "sampling_purpose": self.rng.choices(
                ["Routine diagnostic", "Surveillance", "Screening"],
                weights=[0.86, 0.09, 0.05], k=1)[0],
            "receipt_date": receipt_day.isoformat(),
            "receipt_time": f"{receipt_hour:02d}:{receipt_minute}",
            "condition_on_receipt": condition,
            "rejection_reason": "Leaked in transit" if rejected else None,
            "facility_code": facility, "facility_name": f"Facility {facility}",
            "local_patient_id": patient_id,
            "sex": self.rng.choices(["F", "M"], weights=[0.53, 0.47], k=1)[0],
            "age_years": age_years,
            "patient_type": "Inpatient" if ward != "Outpatient" else "Outpatient",
            "ward": f"{ward} ward {self.rng.randint(1, 4)}",
            "ward_type": ward,
            "admission_date": admission.isoformat(),
        }

        # Realistic missingness, so the completeness report has something to
        # say. Only optional fields: district is required, and blanking it made
        # the validator reject the batch -- correctly, which is itself a useful
        # confirmation that generated data is held to the same rules as real
        # submissions.
        for field, rate in (("collection_time", 0.18), ("receipt_date", 0.12),
                            ("admission_date", 0.09), ("sex", 0.02),
                            ("ward", 0.03)):
            if self.rng.random() < rate:
                row[field] = None

        self.samples.append(row)
        if rejected:
            self.stats["culture_negative"] += 1
            return
        self._isolates_for(sample_id, specimen_type, ward, when)

        if patient is None and self.repeat_patients and self.rng.random() < 0.06:
            returning = self.rng.choice(self.repeat_patients)
            later = when + timedelta(days=self.rng.randint(3, 40))
            if later <= self.end:
                self._human_specimen(index + 500_000, patient=returning,
                                     forced_ward=ward, forced_date=later)

    def _non_human_specimen(self, index: int, sector: str) -> None:
        lab = self.rng.choice(self.labs)
        region = self.rng.choice(GHANA_REGIONS)
        when = self._date()
        sample_id = f"SYN-{sector[:1].upper()}-{index:06d}"

        row = {
            "sample_id": sample_id, "lab_name": lab,
            "collection_date": when.isoformat(),
            "source_category": sector.upper(),
            "site_type": {"animal": "Farm", "food": "Retail market",
                          "environment": "Wastewater treatment plant",
                          "aquaculture": "Fish farm"}[sector],
            "region": region,
            "district": f"{region} district {self.rng.randint(1, 6)}",
            "specimen_type": "Other",
            "sampling_purpose": "Surveillance",
            "receipt_date": (when + timedelta(days=self.rng.choice([0, 1, 2]))).isoformat(),
            "condition_on_receipt": "Acceptable",
        }
        if sector in ("animal", "aquaculture"):
            row["animal_species"] = self.rng.choice(ANIMAL_SPECIES)
            row["production_type"] = self.rng.choice(PRODUCTION_TYPES)
            row["herd_flock_id"] = f"HERD-{self.rng.randint(1, 120):03d}"
            row["source_type"] = row["animal_species"]
        elif sector == "food":
            row["food_commodity"] = self.rng.choice(FOOD_COMMODITIES)
            row["food_matrix"] = row["food_commodity"]
            row["food_stage"] = self.rng.choice(FOOD_STAGES)
            row["source_type"] = row["food_commodity"]
        else:
            row["water_body"] = self.rng.choice(
                ["Densu", "Pra", "Ankobra", "Volta", "Oti", "Tano"])
            row["catchment"] = f"{row['water_body']} basin"
            row["treatment_stage"] = self.rng.choice(TREATMENT_STAGES)
            row["environment_matrix"] = row["treatment_stage"]
            row["sampling_point"] = f"Point {self.rng.randint(1, 30)}"
            row["source_type"] = "water"

        self.samples.append(row)
        self._isolates_for(sample_id, "Other", None, when,
                           mix=NON_HUMAN_ORGANISMS[sector])

    def _isolates_for(self, sample_id: str, specimen_type: str,
                      ward: Optional[str], when: date,
                      mix: Optional[List[Tuple[str, float]]] = None) -> None:
        # A tenth of cultures grow nothing. A surveillance system needs those to
        # compute a positivity rate at all.
        if self.rng.random() < 0.10:
            self.stats["culture_negative"] += 1
            return

        weighted = mix or ORGANISM_BY_SPECIMEN.get(specimen_type,
                                                   ORGANISM_BY_SPECIMEN["Blood"])
        count = 1 if self.rng.random() < 0.90 else 2
        chosen: List[str] = []
        for _ in range(count):
            organism = _pick(self.rng, weighted)
            if organism not in chosen:
                chosen.append(organism)

        for position, organism in enumerate(chosen, start=1):
            isolate_id = f"{sample_id}-{position}"
            self.isolates.append({
                "sample_id": sample_id, "isolate_id": isolate_id,
                "isolate_number": position, "organism": organism,
                "identification_method": self.rng.choices(
                    list(IDENTIFICATION_METHODS[:5]),
                    weights=[0.30, 0.34, 0.20, 0.10, 0.06], k=1)[0],
                "identification_date": (when + timedelta(days=2)).isoformat(),
                "is_significant": "Yes" if self.rng.random() < 0.88 else "No",
            })
            self._results_for(isolate_id, organism, ward, when)
            if self.rng.random() < 0.04:
                self._genomic_for(isolate_id, organism, when)

    def _results_for(self, isolate_id: str, organism: str,
                     ward: Optional[str], when: date) -> None:
        panel = PANEL.get(organism, [])
        if not panel:
            return
        # A laboratory reports a subset of the panel. Short panels -- Neisseria
        # has four agents -- must not ask for a sample larger than they hold.
        lowest = min(4, len(panel))
        tested = self.rng.sample(
            panel, k=self.rng.randint(lowest, len(panel)))
        standard, edition = self.rng.choice(BREAKPOINT_EDITIONS)

        for agent in tested:
            probability = self._resistance_probability(organism, agent, ward, when)
            result = self._result(probability)
            method, mic, zone = self._measurement(result)
            qc_failed = self.rng.random() < 0.015
            if qc_failed:
                self.stats["qc_failures"] += 1
            self.ast.append({
                "sample_id": isolate_id.rsplit("-", 1)[0],
                "isolate_id": isolate_id, "organism": organism,
                "antibiotic": agent, "method": method,
                "mic_operator": "<=" if method == "MIC" and result == "S" else
                                (">=" if method == "MIC" and result == "R" else None),
                "mic_value": mic, "zone_diameter": zone, "result": result,
                "guideline": standard, "guideline_version": edition,
                "qc_status": "Fail" if qc_failed else "Pass",
                "qc_strain": "ATCC 25922",
                "test_date": (when + timedelta(days=3)).isoformat(),
            })

        # Inject an impossible combination occasionally, so the expert rules and
        # the data-quality page have real findings to report.
        if self.rng.random() < 0.012:
            for bad_organism, bad_agent in IMPLAUSIBLE_PAIRS:
                if bad_organism == organism:
                    self.ast.append({
                        "sample_id": isolate_id.rsplit("-", 1)[0],
                        "isolate_id": isolate_id, "organism": organism,
                        "antibiotic": bad_agent, "method": "DD",
                        "mic_operator": None, "mic_value": None,
                        "zone_diameter": float(self.rng.randint(18, 30)),
                        "result": "S", "guideline": standard,
                        "guideline_version": edition, "qc_status": "Pass",
                        "qc_strain": "ATCC 25922",
                        "test_date": (when + timedelta(days=3)).isoformat(),
                    })
                    self.stats["implausible_results"] += 1
                    break

    def _genomic_for(self, isolate_id: str, organism: str, when: date) -> None:
        genes = {
            "Escherichia coli": ["blaCTX-M-15", "qnrS1", "sul1", "tet(A)"],
            "Klebsiella pneumoniae": ["blaCTX-M-15", "blaOXA-1", "blaNDM-1",
                                      "qnrB1"],
            "Staphylococcus aureus": ["mecA", "blaZ", "ermC"],
            "Acinetobacter baumannii": ["blaOXA-23", "blaOXA-51", "armA"],
        }.get(organism, ["sul1"])
        picked = self.rng.sample(genes, k=self.rng.randint(1, len(genes)))
        self.genomics.append({
            "genomic_id": f"SEQ-{isolate_id}", "isolate_id": isolate_id,
            "run_id": f"RUN-{when.year}-{self.rng.randint(1, 40):02d}",
            "platform": self.rng.choice(["Illumina MiSeq", "Illumina NextSeq",
                                         "Oxford Nanopore MinION"]),
            "run_date": (when + timedelta(days=self.rng.randint(20, 90))).isoformat(),
            "mean_depth": round(self.rng.uniform(35, 120), 1),
            "coverage_breadth": round(self.rng.uniform(95, 99.9), 1),
            "contamination_pct": round(self.rng.uniform(0.1, 2.4), 2),
            "contig_count": self.rng.randint(45, 240),
            "qc_status": "Pass",
            "assembler": "SPAdes", "assembler_version": "3.15.5",
            "pipeline_name": "bactopia", "pipeline_version": "3.0.1",
            "amr_db_name": "ResFinder", "amr_db_version": "2025-06-01",
            "species_confirmed": organism,
            "sequence_type": f"ST{self.rng.choice([131, 147, 307, 15, 39, 258])}",
            "amr_genes": ";".join(picked),
            "cluster_method": "cgMLST",
            "cluster_id": f"CL-{self.rng.randint(1, 30):03d}",
            "analysis_date": (when + timedelta(days=self.rng.randint(95, 140))).isoformat(),
            "analysed_by": "Bioinformatics unit",
            "review_status": "Accepted", "reviewed_by": "Laboratory head",
        })

    def _outbreak_cluster(self) -> None:
        """A tight cluster of one resistant clone on one ward.

        Gives the signal rules and the cluster field something shaped like a real
        event rather than background noise.
        """
        lab = self.labs[0]
        region = "Greater Accra"
        base_day = self.end - timedelta(days=self.rng.randint(30, 70))
        for i in range(18):
            when = base_day + timedelta(days=self.rng.randint(0, 21))
            sample_id = f"SYN-OB-{i:04d}"
            self.samples.append({
                "sample_id": sample_id, "lab_name": lab,
                "collection_date": when.isoformat(), "source_category": "HUMAN",
                "source_type": "clinical_specimen", "site_type": "Hospital",
                "region": region, "district": "Accra Metropolitan",
                "specimen_type": "Blood", "sampling_purpose": "Outbreak investigation",
                "receipt_date": when.isoformat(),
                "condition_on_receipt": "Acceptable",
                "facility_code": "FAC01", "facility_name": "Facility FAC01",
                "local_patient_id": f"MRN-OB{i:04d}",
                "sex": self.rng.choice(["F", "M"]),
                "age_years": float(self.rng.randint(20, 70)),
                "patient_type": "Inpatient", "ward": "ICU ward 1",
                "ward_type": "ICU",
                "admission_date": (when - timedelta(days=self.rng.randint(4, 20))).isoformat(),
            })
            isolate_id = f"{sample_id}-1"
            self.isolates.append({
                "sample_id": sample_id, "isolate_id": isolate_id,
                "isolate_number": 1, "organism": "Klebsiella pneumoniae",
                "identification_method": "MALDI-TOF",
                "identification_date": (when + timedelta(days=2)).isoformat(),
                "is_significant": "Yes",
            })
            for agent in ("Meropenem", "Ertapenem", "Ceftriaxone", "Ciprofloxacin",
                          "Gentamicin", "Amikacin", "Colistin",
                          "Piperacillin-Tazobactam"):
                result = "S" if agent == "Colistin" else "R"
                method, mic, zone = self._measurement(result)
                self.ast.append({
                    "sample_id": sample_id, "isolate_id": isolate_id,
                    "organism": "Klebsiella pneumoniae", "antibiotic": agent,
                    "method": method,
                    "mic_operator": "<=" if method == "MIC" and result == "S" else
                                    (">=" if method == "MIC" else None),
                    "mic_value": mic, "zone_diameter": zone, "result": result,
                    "guideline": "CLSI", "guideline_version": "M100-Ed35 (2025)",
                    "qc_status": "Pass", "qc_strain": "ATCC 700603",
                    "test_date": (when + timedelta(days=3)).isoformat(),
                })
            self._genomic_for(isolate_id, "Klebsiella pneumoniae", when)
            self.stats["outbreak_isolates"] += 1

    # -- output ----------------------------------------------------------
    # -- consumption and prescribing -------------------------------------
    #
    # Built after run(), from the same seeded generator, so the whole workbook
    # is reproducible together.

    def _periods(self) -> List[str]:
        """Reporting periods as YYYY-MM, oldest first, over the same span as
        the specimens so consumption and resistance can be compared."""
        out: List[str] = []
        year, month = self.start.year, self.start.month
        while (year, month) <= (self.end.year, self.end.month):
            out.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return out

    def build_amu(self) -> None:
        """Human antimicrobial use, one row per facility, period and agent."""
        for period in self._periods():
            for (facility, region, district, beds,
                 low, high) in AMU_FACILITIES:
                # Occupancy moves month to month; the facility's scale does not.
                patient_days = int(beds * self.rng.uniform(0.86, 1.14))
                agents = self.rng.sample(
                    AMU_AGENTS, self.rng.randint(5, len(AMU_AGENTS)))
                for name, atc, aware, formulation in agents:
                    # Reserve agents are used sparingly, and mostly in the
                    # tertiary centres, so the AWaRe split is not uniform.
                    if aware == "Reserve" and (beds < 12000
                                               or self.rng.random() < 0.55):
                        continue
                    if aware == "Watch" and self.rng.random() < 0.10:
                        continue
                    share = {"Access": self.rng.uniform(0.22, 0.40),
                             "Watch": self.rng.uniform(0.06, 0.18),
                             "Reserve": self.rng.uniform(0.01, 0.04)}[aware]
                    rate = round(self.rng.uniform(low, high) * share, 2)

                    # One record in twelve arrives with no denominator. The
                    # coverage report exists to say so rather than quietly
                    # pooling over whatever happens to be present.
                    days: Optional[int] = patient_days
                    if self.rng.random() < 0.08:
                        days = None
                        self.stats["amu_missing_denominator"] += 1

                    # quantity_dispensed is defined units, reconstructed from
                    # the rate so the two columns cannot contradict each other.
                    quantity = round(rate * patient_days / 1000.0
                                     * self.rng.uniform(0.9, 1.1), 1)

                    self.amu.append({
                        "facility_name": facility,
                        "report_period": period,
                        "region": region,
                        "district": district,
                        "sector": "HUMAN",
                        "antibiotic_name": name,
                        "atc_code": atc,
                        "aware_category": aware,
                        "formulation": formulation,
                        "unit_of_measure": "DDD",
                        "quantity_dispensed": quantity,
                        "ddd_per_1000": rate,
                        "patient_days": days,
                    })

    def build_amc(self) -> None:
        """Animal and aquaculture consumption, one row per stratum, period and
        agent.

        A minority of goat and sheep returns cover a single smallholder cluster:
        a few hundred kilograms of biomass against a normal quantity of drug,
        which produces an enormous mg/kg for that row. Those rows are real in
        shape -- small denominators do occur -- and they are what makes a mean of
        row-level rates diverge from the pooled figure.
        """
        for period in self._periods():
            for (species, sector, production, biomass_typical,
                 low, high) in AMC_STRATA:
                region = self.rng.choice(GHANA_REGIONS)
                agents = self.rng.sample(AMC_AGENTS, self.rng.randint(3, 6))
                for name, drug_class, atcvet, route, purpose in agents:
                    biomass = biomass_typical * self.rng.uniform(0.75, 1.25)
                    rate = self.rng.uniform(low, high)

                    tiny = (species in ("Goat", "Sheep")
                            and self.rng.random() < 0.18)
                    if tiny:
                        biomass *= self.rng.uniform(0.008, 0.03)
                        rate *= self.rng.uniform(3.0, 7.0)
                        self.stats["amc_small_denominator"] += 1

                    biomass = round(biomass, 1)
                    # quantity_kg is active ingredient; mg/kg follows from it,
                    # so the stored rate and the stored masses agree.
                    quantity_kg = round(rate * biomass / 1_000_000.0, 4)
                    mg_per_kg = round(quantity_kg * 1_000_000.0 / biomass, 2) \
                        if biomass > 0 else None

                    self.amc.append({
                        "report_period": period,
                        "region": region,
                        "sector": sector,
                        "species": species,
                        "production_type": production,
                        "antibiotic_class": drug_class,
                        "antibiotic_name": name,
                        "atc_vet_code": atcvet,
                        "quantity_kg": quantity_kg,
                        "biomass_kg": biomass,
                        "mg_per_kg_biomass": mg_per_kg,
                        "route": route,
                        "purpose": purpose,
                    })

    def build_pps(self, surveys: int = 12) -> None:
        """Point prevalence surveys and the prescriptions belonging to them.

        Every prescription names its facility and survey date. The upload page
        used to split the prescriptions sheet into equal blocks by row position,
        so naming them is what proves the attribution is done by key -- and a
        multi-facility workbook is the only kind that can show the difference.
        """
        facilities = [(f, r, d) for f, r, d, *_ in AMU_FACILITIES]
        used: set = set()
        for index in range(surveys):
            facility, region, district = facilities[index % len(facilities)]
            # Distinct (facility, date) per survey: identical pairs cannot be
            # told apart, and the validator rejects them rather than guess.
            while True:
                when = self.start + timedelta(
                    days=self.rng.randint(30, max((self.end - self.start).days, 60)))
                key = (facility, when.isoformat())
                if key not in used:
                    used.add(key)
                    break

            total_patients = self.rng.randint(80, 340)
            on_antibiotics = int(total_patients
                                 * self.rng.uniform(0.38, 0.58))
            # Some patients receive more than one agent, so prescriptions
            # exceed patients on antibiotics -- which is why the prevalence
            # denominator is patients, not prescriptions.
            n_rx = max(1, int(on_antibiotics * self.rng.uniform(1.05, 1.45)))

            self.pps_surveys.append({
                "facility_name": facility,
                "survey_date": when.isoformat(),
                "region": region,
                "district": district,
                "total_patients": total_patients,
                "patients_on_antibiotics": on_antibiotics,
            })

            for _ in range(n_rx):
                ward = _pick(self.rng, [(w, s) for w, s, _, _ in PPS_WARDS])
                documented, compliant = next(
                    (doc, comp) for w, _, doc, comp in PPS_WARDS if w == ward)
                indication = _pick(self.rng, PPS_INDICATIONS)
                # Surgical prophylaxis beyond one day is the classic failure,
                # so its duration is drawn long and its compliance is lower.
                if indication == "Surgical prophylaxis":
                    duration = self.rng.choice([1, 1, 2, 3, 4, 5, 7])
                    compliant *= 0.55
                else:
                    duration = self.rng.randint(3, 14)
                agent, _atc, _aware, _form = self.rng.choice(AMU_AGENTS)
                self.pps_prescriptions.append({
                    "facility_name": facility,
                    "survey_date": when.isoformat(),
                    "ward": ward,
                    "patient_age_group": _pick(self.rng, PPS_AGE_GROUPS),
                    "antibiotic_name": agent,
                    "route": _pick(self.rng, PPS_ROUTES),
                    "indication": indication,
                    "indication_documented":
                        "Yes" if self.rng.random() < documented else "No",
                    "guideline_compliant":
                        "Yes" if self.rng.random() < compliant else "No",
                    "duration_days": duration,
                })
            self.stats["pps_surveys"] += 1

    def onehealth_frames(self) -> Tuple[pd.DataFrame, pd.DataFrame,
                                        pd.DataFrame, pd.DataFrame]:
        """(pps_survey, prescriptions, amu_data, amc_data)."""
        return (pd.DataFrame(self.pps_surveys),
                pd.DataFrame(self.pps_prescriptions),
                pd.DataFrame(self.amu),
                pd.DataFrame(self.amc))

    def frames(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return (pd.DataFrame(self.samples), pd.DataFrame(self.isolates),
                pd.DataFrame(self.ast), pd.DataFrame(self.genomics))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _delete_existing() -> int:
    from src import db
    removed = 0
    for dataset in db.get_all_datasets():
        name = str(dataset.get("dataset_name") or "")
        if name.startswith(DATASET_PREFIX):
            ok, _ = db.delete_dataset(dataset["dataset_id"])
            removed += 1 if ok else 0
            print(f"  deleted {dataset['dataset_id']}  {name}")
    return removed


def _store_onehealth(pps_survey, pps_rx, amu, amc, uploaded_by: str) -> None:
    """Persist the consumption and prescribing sheets.

    These do not go through ingest_validated_upload -- they are not part of the
    specimen chain -- so they take the same three db.save_* calls the upload page
    makes, including attributing prescriptions to their survey by key rather
    than by row position.
    """
    import uuid as _uuid
    from src import db
    from src.validate_onehealth import attribute_prescriptions

    if not pps_survey.empty:
        attribution, errors = attribute_prescriptions(pps_survey, pps_rx)
        for message in errors:
            print("   PPS", message)
        stored_surveys = stored_rx = 0
        for position, (_, row) in enumerate(pps_survey.iterrows()):
            chunk = attribution.get(position)
            if chunk is None or chunk.empty:
                continue
            ok, message = db.save_pps_survey(
                f"PPS-{_uuid.uuid4().hex[:8]}",
                str(row["facility_name"]), str(row["survey_date"]),
                str(row.get("region", "")), str(row.get("district", "")),
                int(row.get("total_patients", 0)),
                int(row.get("patients_on_antibiotics", 0)),
                chunk, uploaded_by=uploaded_by)
            if ok:
                stored_surveys += 1
                stored_rx += len(chunk)
            else:
                print("   PPS save failed:", message)
        print(f"    pps_surveys          {stored_surveys:,}")
        print(f"    pps_prescriptions    {stored_rx:,}")

    if not amu.empty:
        ok, message = db.save_amu_records(amu, uploaded_by)
        print(f"    amu_records          {len(amu):,}" if ok
              else f"   AMU save failed: {message}")

    if not amc.empty:
        ok, message = db.save_amc_records(amc, uploaded_by)
        print(f"    amc_records          {len(amc):,}" if ok
              else f"   AMC save failed: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--specimens", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--months", type=int, default=30,
                        help="span of collection dates")
    parser.add_argument("--workbook", help="also write an upload workbook here")
    parser.add_argument("--delete", action="store_true",
                        help="delete previously generated synthetic datasets "
                             "and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="generate and validate, but do not store")
    args = parser.parse_args()

    if args.delete:
        print("Removing synthetic datasets:")
        print(f"removed {_delete_existing()} dataset(s)")
        return 0

    print(f"Generating {args.specimens:,} specimens over {args.months} months "
          f"(seed {args.seed}) ...")
    generator = Generator(args.specimens, seed=args.seed, months=args.months)
    generator.run()
    generator.build_amu()
    generator.build_amc()
    generator.build_pps()
    samples, isolates, ast, genomics = generator.frames()
    pps_survey, pps_rx, amu, amc = generator.onehealth_frames()

    print(f"  specimens   {len(samples):,}")
    print(f"  isolates    {len(isolates):,}")
    print(f"  AST results {len(ast):,}")
    print(f"  genomes     {len(genomics):,}")
    print(f"  PPS surveys {len(pps_survey):,}")
    print(f"  PPS scripts {len(pps_rx):,}")
    print(f"  AMU records {len(amu):,}")
    print(f"  AMC records {len(amc):,}")
    for key, value in generator.stats.items():
        print(f"  {key:22s} {value:,}")

    if args.workbook:
        from src.upload_template import build_template
        with pd.ExcelWriter(args.workbook, engine="openpyxl") as writer:
            samples.to_excel(writer, sheet_name="samples", index=False)
            isolates.to_excel(writer, sheet_name="isolates", index=False)
            ast.to_excel(writer, sheet_name="ast_results", index=False)
            genomics.to_excel(writer, sheet_name="genomics", index=False)
            # The upload page takes one workbook for everything. Sheet names
            # are what src.validate_onehealth looks for, so they are fixed.
            pps_survey.to_excel(writer, sheet_name="pps_survey", index=False)
            pps_rx.to_excel(writer, sheet_name="prescriptions", index=False)
            amu.to_excel(writer, sheet_name="amu_data", index=False)
            amc.to_excel(writer, sheet_name="amc_data", index=False)
        print(f"\nwrote workbook {args.workbook}")

    from src import ingest, validate
    print("\nValidating through the application's own validator ...")
    outcome = validate.validate_frames(samples, ast, isolates_df=isolates,
                                       genomics_df=genomics)
    print(f"  valid: {outcome.ok}  {outcome.summary}")
    for error in outcome.errors[:10]:
        print("   ERROR", error)
    for warning in outcome.warnings[:6]:
        print("   warn ", warning)
    if not outcome.ok:
        print("\nGeneration produced data the validator rejects; nothing stored.")
        return 1

    if args.dry_run:
        print("\nDry run: nothing stored.")
        return 0

    import uuid
    dataset_id = "syn-" + uuid.uuid4().hex[:6]
    name = (f"{DATASET_PREFIX} surveillance set "
            f"{datetime.now():%Y-%m-%d} ({args.specimens:,} specimens)")
    print(f"\nIngesting as {dataset_id} ...")
    result = ingest.ingest_validated_upload(dataset_id, name, outcome,
                                            uploaded_by="synthetic-generator")
    print(f"  {result.ok}: {result.message}")
    for key, value in result.counts.items():
        print(f"    {key:20s} {value:,}")
    for note in result.notes:
        print("   note:", note[:150])

    if result.ok:
        print()
        print("Storing consumption and prescribing ...")
        _store_onehealth(pps_survey, pps_rx, amu, amc, "synthetic-generator")

    print("\nEvery record in this dataset is invented. Its resistance "
          "percentages describe nothing real and must not be quoted.")
    print(f"Remove it with: python {os.path.basename(__file__)} --delete")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
