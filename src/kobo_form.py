"""
The KoboToolbox survey definition, and the mapper that reads its submissions.

Why this was rebuilt
--------------------
The previous form asked for one antibiotic per submission, with ``isolate_id``
typed in by hand. That is the defect the whole traceability rebuild was about,
reproduced at the point of collection: a culture tested against six drugs became
six submissions with six different isolate identifiers, and no amount of
downstream correction can recover which of them were the same organism.

It also asked for organism, antibiotic, region, source type and ward as free
text, so "E. coli", "E.coli" and "Escherichia coli" all arrived as different
organisms, and it captured nothing about the patient, the ward or the specimen
type -- the fields that make a result clinically interpretable.

Structure
---------
One submission is one **specimen**, and nesting does the work that instructions
cannot:

    specimen
      └── isolates            (repeat: one per organism recovered)
            └── ast_results   (repeat: one per agent tested)

A laboratory physically cannot record six isolate identifiers for one culture,
because the form asks for the organism once and then the agents beneath it.
Multiple organisms from one specimen are separate entries in the isolate repeat,
which is the distinction the old format could not express at all.

Controlled vocabularies
-----------------------
Every field with a fixed answer set is a dropdown, and the options come from the
same constants the validator enforces -- ``traceability`` for the clinical
vocabularies, ``upload_schema`` for the rest. A value that a field offers is a
value the validator accepts, and it cannot drift, because there is one
definition.

Where a list cannot be exhaustive -- organisms and antibiotics -- the dropdown
carries the common entries plus an "Other" option with a free-text follow-up, so
an unusual isolate is still recordable without inviting a typo for a common one.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from src.lab_management import APPROVED_LABS
from src.traceability import (
    IDENTIFICATION_METHODS,
    PATIENT_TYPES,
    QC_STATUSES,
    SAMPLING_PURPOSES,
    SEX_VALUES,
    SPECIMEN_CONDITIONS,
    SPECIMEN_TYPES,
    WARD_TYPES,
)
from src.upload_schema import (
    AST_METHODS,
    BREAKPOINT_STANDARDS,
    MIC_OPERATORS,
    RESULT_VALUES,
    SOURCE_CATEGORIES,
)

logger = logging.getLogger(__name__)

FORM_VERSION = "3.1"

#: Ghana's sixteen administrative regions. A dropdown rather than free text
#: because a region typed three ways becomes three regions in every map and
#: regional comparison.
GHANA_REGIONS: Tuple[str, ...] = (
    "Ahafo", "Ashanti", "Bono", "Bono East", "Central", "Eastern",
    "Greater Accra", "North East", "Northern", "Oti", "Savannah",
    "Upper East", "Upper West", "Volta", "Western", "Western North",
)

#: Organisms the platform expects to see: the WHO GLASS priority pathogens plus
#: the other isolates commonly reported by Ghanaian laboratories. Not
#: exhaustive -- "Other" carries a free-text follow-up.
COMMON_ORGANISMS: Tuple[str, ...] = (
    "Escherichia coli",
    "Klebsiella pneumoniae",
    "Klebsiella oxytoca",
    "Enterobacter cloacae",
    "Serratia marcescens",
    "Citrobacter freundii",
    "Proteus mirabilis",
    "Morganella morganii",
    "Salmonella enterica",
    "Salmonella Typhi",
    "Shigella flexneri",
    "Shigella sonnei",
    "Pseudomonas aeruginosa",
    "Acinetobacter baumannii",
    "Stenotrophomonas maltophilia",
    "Burkholderia cepacia",
    "Staphylococcus aureus",
    "Staphylococcus epidermidis",
    "Coagulase-negative staphylococci",
    "Enterococcus faecalis",
    "Enterococcus faecium",
    "Streptococcus pneumoniae",
    "Streptococcus pyogenes",
    "Streptococcus agalactiae",
    "Haemophilus influenzae",
    "Neisseria gonorrhoeae",
    "Neisseria meningitidis",
    "Campylobacter jejuni",
    "Campylobacter coli",
    "Vibrio cholerae",
    "Listeria monocytogenes",
    "Candida albicans",
)

#: Agents on the panels these laboratories run.
COMMON_ANTIBIOTICS: Tuple[str, ...] = (
    "Ampicillin", "Amoxicillin", "Amoxicillin-Clavulanate",
    "Piperacillin-Tazobactam", "Ampicillin-Sulbactam",
    "Cefazolin", "Cefuroxime", "Cefoxitin", "Ceftriaxone", "Cefotaxime",
    "Ceftazidime", "Cefepime", "Ceftaroline",
    "Meropenem", "Imipenem", "Ertapenem",
    "Aztreonam",
    "Gentamicin", "Amikacin", "Tobramycin", "Streptomycin",
    "Ciprofloxacin", "Levofloxacin", "Moxifloxacin", "Norfloxacin",
    "Trimethoprim-Sulfamethoxazole",
    "Nitrofurantoin", "Fosfomycin",
    "Tetracycline", "Doxycycline", "Minocycline", "Tigecycline",
    "Chloramphenicol",
    "Azithromycin", "Erythromycin", "Clarithromycin",
    "Clindamycin",
    "Vancomycin", "Teicoplanin",
    "Linezolid", "Daptomycin",
    "Colistin", "Polymyxin B",
    "Rifampicin", "Fusidic acid", "Metronidazole",
    "Penicillin", "Oxacillin", "Cefoxitin screen",
    "Quinupristin-Dalfopristin",
)

#: Breakpoint editions. The validator requires an edition wherever a result is
#: given, because breakpoints move between them, so this cannot be free text
#: that a hurried user leaves blank.
BREAKPOINT_EDITIONS: Tuple[str, ...] = (
    "CLSI M100-Ed35 (2025)",
    "CLSI M100-Ed34 (2024)",
    "CLSI M100-Ed33 (2023)",
    "EUCAST v15.0 (2025)",
    "EUCAST v14.0 (2024)",
    "EUCAST v13.1 (2023)",
)

ANIMAL_SPECIES: Tuple[str, ...] = (
    "Cattle", "Sheep", "Goat", "Pig", "Poultry (broiler)", "Poultry (layer)",
    "Guinea fowl", "Dog", "Cat", "Horse", "Donkey", "Tilapia", "Catfish",
)

PRODUCTION_TYPES: Tuple[str, ...] = (
    "Intensive commercial", "Semi-intensive", "Backyard / smallholder",
    "Free range", "Pond aquaculture", "Cage aquaculture", "Abattoir",
)

FOOD_COMMODITIES: Tuple[str, ...] = (
    "Poultry meat", "Beef", "Mutton / goat meat", "Pork", "Fish",
    "Shellfish", "Raw milk", "Dairy product", "Egg", "Leafy vegetable",
    "Other vegetable", "Fruit", "Ready-to-eat food", "Water (packaged)",
)

FOOD_STAGES: Tuple[str, ...] = (
    "Farm", "Abattoir / processing", "Wholesale", "Retail market",
    "Street vendor", "Restaurant / caterer", "Household",
)

TREATMENT_STAGES: Tuple[str, ...] = (
    "Influent (untreated)", "Mid-treatment", "Effluent (treated)",
    "Receiving water upstream", "Receiving water downstream",
    "Borehole / groundwater", "Surface water", "Drinking water supply",
)

ADMISSION_SOURCES: Tuple[str, ...] = (
    "Home / community", "Referral from another facility",
    "Referral from a clinic or health centre", "Transfer between wards",
    "Readmission within 30 days", "Unknown",
)

AGE_UNITS: Tuple[str, ...] = ("Years", "Months", "Days")

# ---------------------------------------------------------------------------
# Consumption and prescribing vocabularies
#
# The form began as a susceptibility-only instrument: every group was gated on
# submission_type = 'ast', and 'ast' was the only choice there was. A field team
# could therefore report what an organism was resistant to, but had no way to
# report how much antibiotic the facility had dispensed, or what was being
# prescribed on the ward -- the two things resistance rates most need to be read
# against. These vocabularies support the three submission types added below.
# ---------------------------------------------------------------------------

#: WHO AWaRe classification. Reported alongside each agent because the Access /
#: Watch / Reserve split is what stewardship targets are written against.
AWARE_CATEGORIES: Tuple[str, ...] = ("Access", "Watch", "Reserve",
                                     "Not classified")

AMU_FORMULATIONS: Tuple[str, ...] = (
    "Tablet", "Capsule", "Oral suspension", "Injection", "Infusion",
    "Topical", "Other",
)

#: Units a pharmacy actually counts in. Defined denominators matter more here
#: than precision: a volume with no unit cannot be converted to a DDD.
AMU_UNITS: Tuple[str, ...] = (
    "DDD", "Grams", "Vials", "Tablets or capsules", "Packs", "Millilitres",
)

#: Sectors the animal-consumption return applies to. The validator accepts only
#: these two, so the form must not offer more.
AMC_SECTORS: Tuple[str, ...] = ("Animal", "Aquaculture")

ANTIBIOTIC_CLASSES: Tuple[str, ...] = (
    "Tetracyclines", "Penicillins", "Cephalosporins", "Fluoroquinolones",
    "Macrolides", "Aminoglycosides", "Sulfonamides", "Polymyxins",
    "Amphenicols", "Lincosamides", "Pleuromutilins", "Other",
)

#: Products actually sold for food-animal and aquaculture use. Kept separate
#: from COMMON_ANTIBIOTICS, which is a clinical susceptibility panel: the two
#: overlap but neither contains the other, and offering the AST panel on a
#: consumption return sent every veterinary product through "other".
VET_ANTIBIOTICS: Tuple[str, ...] = (
    "Oxytetracycline", "Chlortetracycline", "Doxycycline", "Enrofloxacin",
    "Flumequine", "Tylosin", "Tilmicosin", "Erythromycin",
    "Sulfadiazine-Trimethoprim", "Sulfadimidine", "Amoxicillin", "Ampicillin",
    "Penicillin G", "Ceftiofur", "Colistin", "Neomycin", "Gentamicin",
    "Lincomycin", "Spectinomycin", "Florfenicol", "Tiamulin",
)

VET_ROUTES: Tuple[str, ...] = (
    "In feed", "In water", "Injection", "Oral drench", "Topical",
    "Intramammary", "Other",
)

VET_PURPOSES: Tuple[str, ...] = (
    "Therapeutic", "Metaphylaxis", "Prophylaxis", "Growth promotion",
    "Not recorded",
)

#: Age bands for the prescribing survey. Deliberately the bands used in point
#: prevalence reporting rather than the specimen age bands, which are finer.
PPS_AGE_GROUPS: Tuple[str, ...] = (
    "<1", "1-4", "5-14", "15-44", "45-64", "65+", "Unknown",
)

PPS_ROUTES: Tuple[str, ...] = ("IV", "Oral", "IM", "Other")

PPS_INDICATIONS: Tuple[str, ...] = (
    "Community-acquired pneumonia", "Hospital-acquired pneumonia",
    "Urinary tract infection", "Skin and soft tissue infection",
    "Surgical prophylaxis", "Medical prophylaxis", "Sepsis",
    "Intra-abdominal infection", "Meningitis", "Other", "Unknown",
)


# ---------------------------------------------------------------------------
# Choice list construction
# ---------------------------------------------------------------------------

def _slug(value: str) -> str:
    """A stable XLSForm choice name for a label."""
    out = []
    for ch in str(value).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -/_.+()":
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unspecified"


def _choices(list_name: str, values: Iterable[str], *,
             other: bool = False) -> List[Dict[str, str]]:
    """Build a choice list, optionally with an Other entry."""
    rows = [{"list_name": list_name, "name": _slug(v), "label": str(v)}
            for v in values]
    if other:
        rows.append({"list_name": list_name, "name": "other",
                     "label": "Other (specify)"})
    return rows


def _labels_by_slug(values: Iterable[str]) -> Dict[str, str]:
    """Reverse map, for turning a submitted choice name back into its label."""
    return {_slug(v): str(v) for v in values}


# ---------------------------------------------------------------------------
# The survey
# ---------------------------------------------------------------------------

def build_survey() -> Tuple[List[Dict[str, object]], List[Dict[str, str]]]:
    """Return (survey rows, choice rows) for the AMR surveillance form.

    Order follows the laboratory's own workflow, because a form that jumps about
    gets filled in wrongly: what the submission is, where it came from, the
    specimen, the patient, the organism, then the susceptibility results.
    """
    human = "${source_category} = 'human'"
    animal = "${source_category} = 'animal' or ${source_category} = 'aquaculture'"
    food = "${source_category} = 'food'"
    environment = ("${source_category} = 'environment' or "
                   "${source_category} = 'aquaculture'")

    survey: List[Dict[str, object]] = [
        # ── 0. What this submission is ──────────────────────────────────
        {"type": "note", "name": "intro",
         "label": ("## AMR One Health Surveillance\n"
                   f"Form version {FORM_VERSION}. One submission records **one "
                   "specimen**. Add an entry under Isolates for each organism "
                   "recovered, and an entry under Susceptibility results for "
                   "each antibiotic tested against that organism.\n\n"
                   "Do not submit the same specimen twice.")},
        {"type": "select_one submission_types", "name": "submission_type",
         "label": "What are you submitting?", "required": "true",
         "default": "ast"},

        # ── 1. Reporting laboratory and place ───────────────────────────
        {"type": "begin_group", "name": "reporting",
         "label": "1. Reporting laboratory",
         "relevant": "${submission_type} = 'ast'"},
        {"type": "select_one approved_labs", "name": "lab_name",
         "label": "Reporting laboratory", "required": "true"},
        {"type": "select_one ghana_regions", "name": "region",
         "label": "Region", "required": "true"},
        {"type": "text", "name": "district", "label": "District",
         "required": "true"},
        {"type": "text", "name": "site_type",
         "label": "Type of site sampled",
         "hint": "For example: teaching hospital, retail market, "
                 "wastewater treatment plant"},
        {"type": "end_group"},

        # ── 2. The specimen ─────────────────────────────────────────────
        {"type": "begin_group", "name": "specimen", "label": "2. Specimen",
         "relevant": "${submission_type} = 'ast'"},
        {"type": "text", "name": "sample_id",
         "label": "Specimen / sample identifier", "required": "true",
         "hint": "The laboratory's own identifier for this specimen. Must be "
                 "unique."},
        {"type": "text", "name": "accession_number",
         "label": "Laboratory accession number",
         "hint": "Only if different from the specimen identifier"},
        {"type": "select_one source_categories", "name": "source_category",
         "label": "Sector this specimen belongs to", "required": "true",
         "hint": "This decides which questions follow"},
        {"type": "date", "name": "collection_date",
         "label": "Date the specimen was collected", "required": "true"},
        {"type": "time", "name": "collection_time",
         "label": "Time of collection",
         "hint": "Leave blank if not recorded"},
        {"type": "select_one specimen_types", "name": "specimen_type",
         "label": "Specimen type", "required": "true"},
        {"type": "text", "name": "specimen_detail",
         "label": "Specimen description",
         "hint": "For example: peripheral blood culture set 1; left leg ulcer "
                 "swab"},
        {"type": "select_one sampling_purposes", "name": "sampling_purpose",
         "label": "Why was this specimen taken?", "required": "true"},
        {"type": "text", "name": "collected_by",
         "label": "Collected by (role, not name)"},
        {"type": "date", "name": "receipt_date",
         "label": "Date the laboratory received it",
         "hint": "Must not be before the collection date"},
        {"type": "time", "name": "receipt_time", "label": "Time of receipt"},
        {"type": "select_one specimen_conditions", "name": "condition_on_receipt",
         "label": "Condition on receipt"},
        {"type": "text", "name": "rejection_reason",
         "label": "Reason for rejection", "required": "true",
         "relevant": "${condition_on_receipt} = 'rejected'"},
        {"type": "geopoint", "name": "geolocation",
         "label": "GPS location of the sampling site"},
        {"type": "end_group"},

        # ── 3. Patient, for human specimens only ────────────────────────
        {"type": "begin_group", "name": "patient",
         "label": "3. Patient and care episode",
         "relevant": f"${{submission_type}} = 'ast' and ({human})"},
        {"type": "note", "name": "patient_privacy_note",
         "label": ("The patient identifier is converted to an irreversible code "
                   "when it reaches the platform and is never stored. It is "
                   "collected only so that repeat specimens from one patient can "
                   "be recognised. Do not enter a name.")},
        {"type": "text", "name": "facility_code",
         "label": "Facility code", "required": "true",
         "hint": "Short stable code for the hospital, for example KBTH"},
        {"type": "text", "name": "facility_name", "label": "Facility name"},
        {"type": "text", "name": "local_patient_id",
         "label": "Hospital patient number", "required": "true",
         "hint": "Number only. Never a name."},
        {"type": "select_one sexes", "name": "sex", "label": "Sex",
         "required": "true"},
        {"type": "integer", "name": "age_value", "label": "Age",
         "required": "true", "constraint": ". >= 0"},
        {"type": "select_one age_units", "name": "age_unit",
         "label": "Age is given in", "required": "true", "default": "years",
         "hint": "Use months or days for infants so the age band is right"},
        {"type": "select_one patient_types", "name": "patient_type",
         "label": "Care setting", "required": "true"},
        {"type": "text", "name": "ward",
         "label": "Ward the patient was admitted to"},
        {"type": "select_one ward_types", "name": "ward_type",
         "label": "Ward category", "required": "true"},
        {"type": "select_one yes_no", "name": "collected_elsewhere",
         "label": "Was the specimen taken on a different ward?",
         "default": "no"},
        {"type": "text", "name": "ward_at_collection",
         "label": "Ward where the specimen was taken",
         "relevant": "${collected_elsewhere} = 'yes'"},
        {"type": "select_one ward_types", "name": "ward_type_at_collection",
         "label": "Category of the collection ward",
         "relevant": "${collected_elsewhere} = 'yes'"},
        {"type": "date", "name": "admission_date",
         "label": "Date of admission",
         "hint": "Needed to tell community-onset from healthcare-associated "
                 "infection"},
        {"type": "date", "name": "discharge_date",
         "label": "Date of discharge", "hint": "Leave blank if still admitted"},
        {"type": "select_one admission_sources", "name": "admission_source",
         "label": "Where did the patient come from?"},
        {"type": "end_group"},

        # ── 4. Non-human source detail ──────────────────────────────────
        {"type": "begin_group", "name": "animal_source",
         "label": "3. Animal source",
         "relevant": f"${{submission_type}} = 'ast' and ({animal})"},
        {"type": "select_one animal_species", "name": "animal_species",
         "label": "Species", "required": "true"},
        {"type": "select_one production_types", "name": "production_type",
         "label": "Production system"},
        {"type": "text", "name": "herd_flock_id",
         "label": "Herd, flock or pond identifier",
         "hint": "Links repeat sampling of the same unit over time"},
        {"type": "end_group"},

        {"type": "begin_group", "name": "food_source", "label": "3. Food source",
         "relevant": f"${{submission_type}} = 'ast' and ({food})"},
        {"type": "select_one food_commodities", "name": "food_commodity",
         "label": "Commodity", "required": "true"},
        {"type": "select_one food_stages", "name": "food_stage",
         "label": "Point in the food chain", "required": "true"},
        {"type": "end_group"},

        {"type": "begin_group", "name": "environment_source",
         "label": "3. Environmental source",
         "relevant": f"${{submission_type}} = 'ast' and ({environment})"},
        {"type": "text", "name": "water_body",
         "label": "Named water body or facility"},
        {"type": "text", "name": "catchment", "label": "Catchment or basin"},
        {"type": "select_one treatment_stages", "name": "treatment_stage",
         "label": "Stage relative to treatment"},
        {"type": "text", "name": "sampling_point",
         "label": "Precise sampling point",
         "hint": "For example: outfall channel, 20 m downstream"},
        {"type": "end_group"},

        # ── 5. Isolates, and their susceptibility results ───────────────
        {"type": "note", "name": "isolate_note",
         "relevant": "${submission_type} = 'ast'",
         "label": ("### Isolates\n"
                   "Add one entry for **each organism** recovered from this "
                   "specimen. If the culture was negative, add none.\n\n"
                   "Within each organism, add one susceptibility entry per "
                   "antibiotic tested. Do not create a separate isolate for "
                   "each antibiotic.")},
        {"type": "begin_repeat", "name": "isolates", "label": "Isolate",
         "relevant": "${submission_type} = 'ast'"},
        {"type": "select_one organisms", "name": "organism",
         "label": "Organism identified", "required": "true"},
        {"type": "text", "name": "organism_other",
         "label": "Name the organism", "required": "true",
         "relevant": "${organism} = 'other'"},
        {"type": "select_one identification_methods",
         "name": "identification_method",
         "label": "How was it identified?", "required": "true"},
        {"type": "date", "name": "identification_date",
         "label": "Date of identification"},
        {"type": "select_one yes_no", "name": "is_significant",
         "label": "Judged clinically significant?",
         "hint": "No if this is likely colonisation or contamination"},
        {"type": "text", "name": "isolate_notes", "label": "Notes"},

        {"type": "begin_repeat", "name": "ast_results",
         "label": "Susceptibility result"},
        {"type": "select_one antibiotics", "name": "antibiotic",
         "label": "Antibiotic tested", "required": "true"},
        {"type": "text", "name": "antibiotic_other",
         "label": "Name the antibiotic", "required": "true",
         "relevant": "${antibiotic} = 'other'"},
        {"type": "select_one ast_methods", "name": "method",
         "label": "Method", "required": "true"},
        {"type": "decimal", "name": "zone_diameter",
         "label": "Inhibition zone (mm)", "required": "true",
         "relevant": "${method} = 'dd'", "constraint": ". >= 0 and . <= 100"},
        {"type": "select_one mic_operators", "name": "mic_operator",
         "label": "MIC operator", "relevant": "${method} = 'mic'",
         "default": "eq"},
        {"type": "decimal", "name": "mic_value", "label": "MIC (mg/L)",
         "required": "true", "relevant": "${method} = 'mic'",
         "constraint": ". > 0"},
        {"type": "select_one results", "name": "result",
         "label": "Interpretation", "required": "true"},
        {"type": "select_one breakpoint_editions", "name": "guideline_version",
         "label": "Breakpoint standard and edition used", "required": "true",
         "hint": "An interpretation without its edition cannot be reproduced"},
        {"type": "select_one qc_statuses", "name": "qc_status",
         "label": "Did the run's quality control pass?", "required": "true"},
        {"type": "text", "name": "qc_strain", "label": "QC organism used"},
        {"type": "date", "name": "test_date", "label": "Date the test was read"},
        {"type": "text", "name": "ast_instrument",
         "label": "Instrument, if automated"},
        {"type": "end_repeat"},
        {"type": "end_repeat"},

        # ── 7. Antimicrobial use, human (AMU) ───────────────────────────
        # One submission is one facility's return for one reporting period.
        # Each agent dispensed in that period is a row in the repeat, which is
        # how a pharmacy's own records are shaped.
        #
        # Field names carry an amu_ prefix throughout. XLSForm requires names to
        # be unique across the whole form, not merely within a group, so reusing
        # "region" or "antibiotic_name" here would collide with the specimen
        # sections above.
        {"type": "note", "name": "amu_intro",
         "relevant": "${submission_type} = 'amu'",
         "label": ("## Antimicrobial use (human)\n"
                   "One submission is **one facility, one reporting period**. "
                   "Add an entry under Agents for each antibiotic dispensed.\n\n"
                   "Patient-days is the denominator. Without it, use can be "
                   "reported as a volume but not compared between facilities.")},
        {"type": "begin_group", "name": "amu_report",
         "label": "Reporting facility and period",
         "relevant": "${submission_type} = 'amu'"},
        {"type": "text", "name": "amu_facility",
         "label": "Facility name", "required": "true"},
        {"type": "text", "name": "amu_period",
         "label": "Reporting period (YYYY-MM)", "required": "true",
         "hint": "For example 2026-09"},
        {"type": "select_one ghana_regions", "name": "amu_region",
         "label": "Region", "required": "true"},
        {"type": "text", "name": "amu_district", "label": "District"},
        {"type": "integer", "name": "amu_patient_days",
         "label": "Occupied bed-days in the period",
         "hint": "The denominator. Leave blank only if it is genuinely not known"},
        {"type": "end_group"},
        {"type": "begin_repeat", "name": "amu_items",
         "label": "Agents dispensed",
         "relevant": "${submission_type} = 'amu'"},
        {"type": "select_one antibiotics", "name": "amu_antibiotic",
         "label": "Antibiotic", "required": "true"},
        {"type": "text", "name": "amu_antibiotic_other",
         "label": "Name the antibiotic", "required": "true",
         "relevant": "${amu_antibiotic} = 'other'"},
        {"type": "text", "name": "amu_atc", "label": "ATC code",
         "hint": "For example J01CA04"},
        {"type": "select_one aware_categories", "name": "amu_aware",
         "label": "WHO AWaRe category"},
        {"type": "select_one amu_formulations", "name": "amu_formulation",
         "label": "Formulation"},
        {"type": "select_one amu_units", "name": "amu_unit",
         "label": "Unit of measure", "required": "true"},
        {"type": "decimal", "name": "amu_quantity",
         "label": "Quantity dispensed", "required": "true"},
        {"type": "decimal", "name": "amu_ddd",
         "label": "DDD per 1000 patient-days, if already calculated",
         "hint": "Leave blank if you have not calculated it"},
        {"type": "end_repeat"},

        # ── 8. Antimicrobial consumption, animal and aquaculture (AMC) ──
        # Biomass is collected once for the stratum rather than per agent,
        # because it is a property of the population treated, not of the drug.
        {"type": "note", "name": "amc_intro",
         "relevant": "${submission_type} = 'amc'",
         "label": ("## Antimicrobial consumption (animal / aquaculture)\n"
                   "One submission is **one production stratum, one reporting "
                   "period**. Add an entry under Agents for each product used.\n\n"
                   "Biomass is the denominator and is entered once, below.")},
        {"type": "begin_group", "name": "amc_report",
         "label": "Stratum and period",
         "relevant": "${submission_type} = 'amc'"},
        {"type": "text", "name": "amc_period",
         "label": "Reporting period (YYYY-MM)", "required": "true"},
        {"type": "select_one ghana_regions", "name": "amc_region",
         "label": "Region", "required": "true"},
        {"type": "select_one amc_sectors", "name": "amc_sector",
         "label": "Sector", "required": "true"},
        {"type": "select_one animal_species", "name": "amc_species",
         "label": "Species", "required": "true"},
        {"type": "text", "name": "amc_species_other",
         "label": "Name the species", "required": "true",
         "relevant": "${amc_species} = 'other'"},
        {"type": "select_one production_types", "name": "amc_production",
         "label": "Production type"},
        {"type": "decimal", "name": "amc_biomass",
         "label": "Biomass treated, in kilograms",
         "hint": "The denominator. Live weight of the population covered"},
        {"type": "end_group"},
        {"type": "begin_repeat", "name": "amc_items",
         "label": "Agents used",
         "relevant": "${submission_type} = 'amc'"},
        {"type": "select_one antibiotic_classes", "name": "amc_class",
         "label": "Antibiotic class", "required": "true"},
        {"type": "select_one vet_antibiotics", "name": "amc_antibiotic",
         "label": "Antibiotic or product"},
        {"type": "text", "name": "amc_antibiotic_other",
         "label": "Name the antibiotic", "required": "true",
         "relevant": "${amc_antibiotic} = 'other'"},
        {"type": "text", "name": "amc_atcvet", "label": "ATCvet code",
         "hint": "For example QJ01AA06"},
        {"type": "decimal", "name": "amc_quantity",
         "label": "Active ingredient used, in kilograms", "required": "true"},
        {"type": "select_one vet_routes", "name": "amc_route",
         "label": "Route of administration"},
        {"type": "select_one vet_purposes", "name": "amc_purpose",
         "label": "Purpose"},
        {"type": "end_repeat"},

        # ── 9. Point prevalence survey of prescribing (PPS) ─────────────
        # Survey header once, then one entry per prescription. Prescriptions
        # exceed patients on antibiotics whenever a patient is on more than one
        # agent, which is why prevalence is counted on patients and not here.
        {"type": "note", "name": "pps_intro",
         "relevant": "${submission_type} = 'pps'",
         "label": ("## Point prevalence survey\n"
                   "One submission is **one facility, surveyed on one day**. "
                   "Add an entry under Prescriptions for each antibiotic "
                   "prescribed on that day.\n\n"
                   "A patient on two agents gives two entries but is counted "
                   "once in the totals above.")},
        {"type": "begin_group", "name": "pps_header",
         "label": "Survey",
         "relevant": "${submission_type} = 'pps'"},
        {"type": "text", "name": "pps_facility",
         "label": "Facility name", "required": "true"},
        {"type": "date", "name": "pps_date",
         "label": "Date of the survey", "required": "true"},
        {"type": "select_one ghana_regions", "name": "pps_region",
         "label": "Region", "required": "true"},
        {"type": "text", "name": "pps_district", "label": "District"},
        {"type": "integer", "name": "pps_total",
         "label": "Patients surveyed", "required": "true"},
        {"type": "integer", "name": "pps_on_antibiotics",
         "label": "Of those, patients on at least one antibiotic",
         "required": "true",
         "constraint": ". <= ${pps_total}",
         "constraint_message": "Cannot exceed the number of patients surveyed"},
        {"type": "end_group"},
        {"type": "begin_repeat", "name": "pps_items",
         "label": "Prescriptions",
         "relevant": "${submission_type} = 'pps'"},
        {"type": "text", "name": "pps_ward", "label": "Ward, as named locally"},
        {"type": "select_one ward_types", "name": "pps_ward_type",
         "label": "Ward type", "required": "true"},
        {"type": "select_one pps_age_groups", "name": "pps_age_group",
         "label": "Patient age group", "required": "true"},
        {"type": "select_one antibiotics", "name": "pps_antibiotic",
         "label": "Antibiotic prescribed", "required": "true"},
        {"type": "text", "name": "pps_antibiotic_other",
         "label": "Name the antibiotic", "required": "true",
         "relevant": "${pps_antibiotic} = 'other'"},
        {"type": "select_one pps_routes", "name": "pps_route",
         "label": "Route", "required": "true"},
        {"type": "select_one pps_indications", "name": "pps_indication",
         "label": "Indication", "required": "true"},
        {"type": "select_one yes_no", "name": "pps_documented",
         "label": "Was the indication documented in the notes?",
         "required": "true"},
        {"type": "select_one yes_no", "name": "pps_compliant",
         "label": "Was the prescription compliant with guidelines?",
         "required": "true"},
        {"type": "integer", "name": "pps_duration",
         "label": "Days of therapy so far"},
        {"type": "end_repeat"},
    ]

    choices: List[Dict[str, str]] = []
    choices += [{"list_name": "approved_labs", "name": code, "label": name}
                for name, code in APPROVED_LABS.items()]
    choices += [
        {"list_name": "submission_types", "name": "ast",
         "label": "AST / isolate data"},
        {"list_name": "submission_types", "name": "amu",
         "label": "Antimicrobial use (human)"},
        {"list_name": "submission_types", "name": "amc",
         "label": "Antimicrobial consumption (animal / aquaculture)"},
        {"list_name": "submission_types", "name": "pps",
         "label": "Point prevalence survey of prescribing"},
    ]
    choices += _choices("ghana_regions", GHANA_REGIONS)
    choices += _choices("source_categories", SOURCE_CATEGORIES)
    choices += _choices("specimen_types", SPECIMEN_TYPES)
    choices += _choices("sampling_purposes", SAMPLING_PURPOSES)
    choices += _choices("specimen_conditions", SPECIMEN_CONDITIONS)
    choices += _choices("sexes", SEX_VALUES)
    choices += _choices("age_units", AGE_UNITS)
    choices += _choices("patient_types", PATIENT_TYPES)
    choices += _choices("ward_types", WARD_TYPES)
    choices += _choices("admission_sources", ADMISSION_SOURCES)
    choices += _choices("animal_species", ANIMAL_SPECIES, other=True)
    choices += _choices("production_types", PRODUCTION_TYPES, other=True)
    choices += _choices("food_commodities", FOOD_COMMODITIES, other=True)
    choices += _choices("food_stages", FOOD_STAGES)
    choices += _choices("treatment_stages", TREATMENT_STAGES)
    choices += _choices("organisms", COMMON_ORGANISMS, other=True)
    choices += _choices("identification_methods", IDENTIFICATION_METHODS)
    choices += _choices("antibiotics", COMMON_ANTIBIOTICS, other=True)
    choices += _choices("ast_methods", AST_METHODS)
    choices += _choices("results", RESULT_VALUES)
    choices += _choices("qc_statuses", QC_STATUSES)
    choices += _choices("breakpoint_editions", BREAKPOINT_EDITIONS)
    choices += _choices("aware_categories", AWARE_CATEGORIES)
    choices += _choices("amu_formulations", AMU_FORMULATIONS)
    choices += _choices("amu_units", AMU_UNITS)
    choices += _choices("amc_sectors", AMC_SECTORS)
    choices += _choices("antibiotic_classes", ANTIBIOTIC_CLASSES)
    choices += _choices("vet_antibiotics", VET_ANTIBIOTICS, other=True)
    choices += _choices("vet_routes", VET_ROUTES)
    choices += _choices("vet_purposes", VET_PURPOSES)
    choices += _choices("pps_age_groups", PPS_AGE_GROUPS)
    choices += _choices("pps_routes", PPS_ROUTES)
    choices += _choices("pps_indications", PPS_INDICATIONS)
    choices += [
        {"list_name": "mic_operators", "name": "eq", "label": "="},
        {"list_name": "mic_operators", "name": "le", "label": "<="},
        {"list_name": "mic_operators", "name": "lt", "label": "<"},
        {"list_name": "mic_operators", "name": "ge", "label": ">="},
        {"list_name": "mic_operators", "name": "gt", "label": ">"},
        {"list_name": "yes_no", "name": "yes", "label": "Yes"},
        {"list_name": "yes_no", "name": "no", "label": "No"},
    ]
    return survey, choices


# ---------------------------------------------------------------------------
# Reading submissions back
# ---------------------------------------------------------------------------

#: Choice-name to label, per field. Submissions carry the choice *name*, and the
#: validator checks the label, so every dropdown needs translating back.
_REVERSE_MAPS: Dict[str, Dict[str, str]] = {
    "region": _labels_by_slug(GHANA_REGIONS),
    "source_category": _labels_by_slug(SOURCE_CATEGORIES),
    "specimen_type": _labels_by_slug(SPECIMEN_TYPES),
    "sampling_purpose": _labels_by_slug(SAMPLING_PURPOSES),
    "condition_on_receipt": _labels_by_slug(SPECIMEN_CONDITIONS),
    "sex": _labels_by_slug(SEX_VALUES),
    "patient_type": _labels_by_slug(PATIENT_TYPES),
    "ward_type": _labels_by_slug(WARD_TYPES),
    "ward_type_at_collection": _labels_by_slug(WARD_TYPES),
    "admission_source": _labels_by_slug(ADMISSION_SOURCES),
    "animal_species": _labels_by_slug(ANIMAL_SPECIES),
    "production_type": _labels_by_slug(PRODUCTION_TYPES),
    "food_commodity": _labels_by_slug(FOOD_COMMODITIES),
    "food_stage": _labels_by_slug(FOOD_STAGES),
    "treatment_stage": _labels_by_slug(TREATMENT_STAGES),
    "organism": _labels_by_slug(COMMON_ORGANISMS),
    "identification_method": _labels_by_slug(IDENTIFICATION_METHODS),
    "antibiotic": _labels_by_slug(COMMON_ANTIBIOTICS),
    "method": _labels_by_slug(AST_METHODS),
    "result": _labels_by_slug(RESULT_VALUES),
    "qc_status": _labels_by_slug(QC_STATUSES),
    "age_unit": _labels_by_slug(AGE_UNITS),
    "lab_name": {code: name for name, code in APPROVED_LABS.items()},
    # consumption and prescribing
    "amu_region": _labels_by_slug(GHANA_REGIONS),
    "amu_antibiotic": _labels_by_slug(COMMON_ANTIBIOTICS),
    "amu_aware": _labels_by_slug(AWARE_CATEGORIES),
    "amu_formulation": _labels_by_slug(AMU_FORMULATIONS),
    "amu_unit": _labels_by_slug(AMU_UNITS),
    "amc_region": _labels_by_slug(GHANA_REGIONS),
    "amc_sector": _labels_by_slug(AMC_SECTORS),
    "amc_species": _labels_by_slug(ANIMAL_SPECIES),
    "amc_production": _labels_by_slug(PRODUCTION_TYPES),
    "amc_class": _labels_by_slug(ANTIBIOTIC_CLASSES),
    "amc_antibiotic": _labels_by_slug(VET_ANTIBIOTICS),
    "amc_route": _labels_by_slug(VET_ROUTES),
    "amc_purpose": _labels_by_slug(VET_PURPOSES),
    "pps_region": _labels_by_slug(GHANA_REGIONS),
    "pps_ward_type": _labels_by_slug(WARD_TYPES),
    "pps_age_group": _labels_by_slug(PPS_AGE_GROUPS),
    "pps_antibiotic": _labels_by_slug(COMMON_ANTIBIOTICS),
    "pps_route": _labels_by_slug(PPS_ROUTES),
    "pps_indication": _labels_by_slug(PPS_INDICATIONS),
    "pps_documented": {"yes": "Yes", "no": "No"},
    "pps_compliant": {"yes": "Yes", "no": "No"},
    "mic_operator": {"eq": "=", "le": "<=", "lt": "<", "ge": ">=", "gt": ">"},
    "is_significant": {"yes": "Yes", "no": "No"},
    "collected_elsewhere": {"yes": "Yes", "no": "No"},
}

#: Breakpoint edition label to (standard, version), since the form asks for both
#: in one dropdown -- two fields invite a CLSI standard with a EUCAST version.
_EDITION_SPLIT: Dict[str, Tuple[str, str]] = {
    _slug(label): (
        "CLSI" if label.startswith("CLSI") else "EUCAST",
        label.split(" ", 1)[1] if " " in label else label,
    )
    for label in BREAKPOINT_EDITIONS
}


def _leaf(key: str) -> str:
    """The last path segment of a Kobo field name."""
    return str(key).rsplit("/", 1)[-1]


def _flatten(record: Dict[str, object]) -> Dict[str, object]:
    """Strip group prefixes from a submission's scalar fields."""
    out: Dict[str, object] = {}
    for key, value in record.items():
        if isinstance(value, list):
            continue
        name = _leaf(key)
        if name.startswith("_") or name in ("meta", "formhub"):
            continue
        if name not in out or out[name] in (None, ""):
            out[name] = value
    return out


def _repeats(record: Dict[str, object], name: str) -> List[Dict[str, object]]:
    """Every entry of a named repeat group, wherever Kobo nested it."""
    for key, value in record.items():
        if isinstance(value, list) and _leaf(key) == name:
            return [v for v in value if isinstance(v, dict)]
    return []


def _label(field: str, value) -> Optional[str]:
    """Translate a submitted choice name back to the label the validator wants."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    mapping = _REVERSE_MAPS.get(field)
    if mapping:
        return mapping.get(text.lower(), text)
    return text


def _age_in_years(value, unit: Optional[str]) -> Optional[float]:
    """Convert an age given in years, months or days into years.

    Recording an infant as "0 years" loses the <1 band that paediatric
    surveillance turns on, so the form asks for a unit and the conversion
    happens here.
    """
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    unit = (unit or "years").strip().lower()
    if unit.startswith("month"):
        return round(number / 12, 3)
    if unit.startswith("day"):
        return round(number / 365.25, 4)
    return number


def _combine_datetime(date_value, time_value) -> Optional[str]:
    date_text = str(date_value).strip()[:10] if date_value else ""
    if not date_text:
        return None
    time_text = str(time_value).strip() if time_value else ""
    if time_text:
        # Kobo sends times as HH:MM:SS.sss+ZZ:ZZ; keep the clock part.
        time_text = time_text.split(".")[0].split("+")[0][:8]
    return f"{date_text} {time_text}".strip()


def submissions_to_frames(submissions) -> Tuple[pd.DataFrame, pd.DataFrame,
                                                pd.DataFrame]:
    """Turn Kobo submissions into (samples, isolates, ast_results) frames.

    The frames match the upload contract in ``upload_schema``, so a Kobo sync
    and a spreadsheet upload go through exactly the same validator and the same
    ingestion path.

    Returns three frames rather than two because isolates are now an entity in
    their own right. The old mapper returned samples and AST only, which is why
    a Kobo import could never populate the isolate table correctly.
    """
    records: List[Dict[str, object]] = []
    if isinstance(submissions, dict):
        records = submissions.get("results", [submissions])
    elif isinstance(submissions, pd.DataFrame):
        records = submissions.to_dict("records")
    elif isinstance(submissions, list):
        records = [r for r in submissions if isinstance(r, dict)]

    if not records:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    sample_rows: List[Dict[str, object]] = []
    isolate_rows: List[Dict[str, object]] = []
    ast_rows: List[Dict[str, object]] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        flat = _flatten(record)
        # Version 3.1 added consumption and prescribing submissions to the same
        # form. They carry no specimen, so they are skipped here and read by
        # submissions_to_consumption instead.
        kind = str(flat.get("submission_type") or "ast").strip().lower()
        if kind and kind != "ast":
            continue
        sample_id = _label("sample_id", flat.get("sample_id"))
        if not sample_id:
            continue

        category = (_label("source_category", flat.get("source_category"))
                    or "").upper()

        latitude = longitude = None
        geo = flat.get("geolocation")
        if geo:
            parts = str(geo).split()
            if len(parts) >= 2:
                try:
                    latitude, longitude = float(parts[0]), float(parts[1])
                except ValueError:
                    latitude = longitude = None

        sample: Dict[str, object] = {
            "sample_id": sample_id,
            "lab_name": _label("lab_name", flat.get("lab_name")),
            "collection_date": (str(flat.get("collection_date"))[:10]
                                if flat.get("collection_date") else None),
            "collection_time": (str(flat.get("collection_time")).split(".")[0][:5]
                                if flat.get("collection_time") else None),
            "source_category": category or None,
            "site_type": _label("site_type", flat.get("site_type")),
            "region": _label("region", flat.get("region")),
            "district": _label("district", flat.get("district")),
            "latitude": latitude,
            "longitude": longitude,
            "accession_number": _label("accession_number",
                                       flat.get("accession_number")),
            "specimen_type": _label("specimen_type", flat.get("specimen_type")),
            "specimen_detail": _label("specimen_detail",
                                      flat.get("specimen_detail")),
            "collected_by": _label("collected_by", flat.get("collected_by")),
            "receipt_date": (str(flat.get("receipt_date"))[:10]
                             if flat.get("receipt_date") else None),
            "receipt_time": (str(flat.get("receipt_time")).split(".")[0][:5]
                             if flat.get("receipt_time") else None),
            "condition_on_receipt": _label("condition_on_receipt",
                                           flat.get("condition_on_receipt")),
            "rejection_reason": _label("rejection_reason",
                                       flat.get("rejection_reason")),
            "sampling_purpose": _label("sampling_purpose",
                                       flat.get("sampling_purpose")),
        }

        if category == "HUMAN":
            sample.update({
                "facility_code": _label("facility_code", flat.get("facility_code")),
                "facility_name": _label("facility_name", flat.get("facility_name")),
                "local_patient_id": _label("local_patient_id",
                                           flat.get("local_patient_id")),
                "sex": _label("sex", flat.get("sex")),
                "age_years": _age_in_years(
                    flat.get("age_value"),
                    _label("age_unit", flat.get("age_unit"))),
                "patient_type": _label("patient_type", flat.get("patient_type")),
                "ward": _label("ward", flat.get("ward")),
                "ward_type": _label("ward_type", flat.get("ward_type")),
                "ward_at_collection": _label("ward_at_collection",
                                             flat.get("ward_at_collection")),
                "ward_type_at_collection": _label(
                    "ward_type_at_collection",
                    flat.get("ward_type_at_collection")),
                "admission_date": (str(flat.get("admission_date"))[:10]
                                   if flat.get("admission_date") else None),
                "discharge_date": (str(flat.get("discharge_date"))[:10]
                                   if flat.get("discharge_date") else None),
                "admission_source": _label("admission_source",
                                           flat.get("admission_source")),
            })
        elif category in ("ANIMAL", "AQUACULTURE"):
            sample.update({
                "animal_species": _label("animal_species",
                                         flat.get("animal_species")),
                "production_type": _label("production_type",
                                          flat.get("production_type")),
                "herd_flock_id": _label("herd_flock_id", flat.get("herd_flock_id")),
                "water_body": _label("water_body", flat.get("water_body")),
                "sampling_point": _label("sampling_point",
                                         flat.get("sampling_point")),
            })
        elif category == "FOOD":
            sample.update({
                "food_commodity": _label("food_commodity",
                                         flat.get("food_commodity")),
                "food_matrix": _label("food_commodity", flat.get("food_commodity")),
                "food_stage": _label("food_stage", flat.get("food_stage")),
            })
        elif category == "ENVIRONMENT":
            sample.update({
                "water_body": _label("water_body", flat.get("water_body")),
                "catchment": _label("catchment", flat.get("catchment")),
                "treatment_stage": _label("treatment_stage",
                                          flat.get("treatment_stage")),
                "environment_matrix": _label("treatment_stage",
                                             flat.get("treatment_stage")),
                "sampling_point": _label("sampling_point",
                                         flat.get("sampling_point")),
            })

        sample_rows.append(sample)

        # ---- isolates, and their susceptibility results ----------------
        for position, entry in enumerate(_repeats(record, "isolates"), start=1):
            flat_isolate = _flatten(entry)
            organism = _label("organism", flat_isolate.get("organism"))
            if organism and organism.lower() in ("other", "other (specify)"):
                organism = _label("organism_other",
                                  flat_isolate.get("organism_other")) or organism
            if not organism:
                continue

            # The identifier is derived, not typed. A hand-entered isolate id is
            # how one culture came to be recorded as six isolates.
            isolate_id = f"{sample_id}-{position}"

            isolate_rows.append({
                "sample_id": sample_id,
                "isolate_id": isolate_id,
                "isolate_number": position,
                "organism": organism,
                "identification_method": _label(
                    "identification_method",
                    flat_isolate.get("identification_method")),
                "identification_date": (
                    str(flat_isolate.get("identification_date"))[:10]
                    if flat_isolate.get("identification_date") else None),
                "is_significant": _label("is_significant",
                                         flat_isolate.get("is_significant")),
                "notes": _label("isolate_notes", flat_isolate.get("isolate_notes")),
            })

            for result_entry in _repeats(entry, "ast_results"):
                flat_result = _flatten(result_entry)
                antibiotic = _label("antibiotic", flat_result.get("antibiotic"))
                if antibiotic and antibiotic.lower() in ("other", "other (specify)"):
                    antibiotic = _label(
                        "antibiotic_other",
                        flat_result.get("antibiotic_other")) or antibiotic
                if not antibiotic:
                    continue

                edition = str(flat_result.get("guideline_version") or "").lower()
                standard, version = _EDITION_SPLIT.get(edition, (None, None))

                ast_rows.append({
                    "sample_id": sample_id,
                    "isolate_id": isolate_id,
                    "organism": organism,
                    "antibiotic": antibiotic,
                    "method": _label("method", flat_result.get("method")),
                    "ast_instrument": _label("ast_instrument",
                                             flat_result.get("ast_instrument")),
                    "mic_operator": _label("mic_operator",
                                           flat_result.get("mic_operator")),
                    "mic_value": flat_result.get("mic_value"),
                    "zone_diameter": flat_result.get("zone_diameter"),
                    "result": _label("result", flat_result.get("result")),
                    "guideline": standard,
                    "guideline_version": version,
                    "qc_status": _label("qc_status", flat_result.get("qc_status")),
                    "qc_strain": _label("qc_strain", flat_result.get("qc_strain")),
                    "test_date": (str(flat_result.get("test_date"))[:10]
                                  if flat_result.get("test_date") else None),
                })

    return (pd.DataFrame(sample_rows), pd.DataFrame(isolate_rows),
            pd.DataFrame(ast_rows))



def _records(submissions) -> List[Dict[str, object]]:
    """Normalise whatever the API or the caller handed us into a list of dicts."""
    if isinstance(submissions, dict):
        return [r for r in submissions.get("results", [submissions])
                if isinstance(r, dict)]
    if isinstance(submissions, pd.DataFrame):
        return submissions.to_dict("records")
    if isinstance(submissions, list):
        return [r for r in submissions if isinstance(r, dict)]
    return []


def _named(flat: Dict[str, object], field: str, other_field: str) -> Optional[str]:
    """A dropdown answer, or the free-text the respondent typed when they chose
    'other'. Without this the stored value is the literal word 'other'."""
    value = _label(field, flat.get(field))
    if value and str(value).strip().lower() == "other":
        typed = flat.get(other_field)
        if typed and str(typed).strip():
            return str(typed).strip()
    return value


def _number(value) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def submissions_to_consumption(submissions) -> Tuple[pd.DataFrame, pd.DataFrame,
                                                     pd.DataFrame, pd.DataFrame]:
    """Turn Kobo submissions into (amu, amc, pps_survey, pps_prescriptions).

    The counterpart to ``submissions_to_frames``, for the three submission types
    the form gained in version 3.1. Each frame carries the column names the
    corresponding ``src.db.save_*`` function reads and that
    ``src.validate_onehealth`` checks, so a mobile submission and a workbook
    sheet reach the database by the same route.

    Prescriptions carry their survey's facility and date, because that is the
    key the upload page attributes them by -- never row position.
    """
    amu_rows: List[Dict[str, object]] = []
    amc_rows: List[Dict[str, object]] = []
    survey_rows: List[Dict[str, object]] = []
    rx_rows: List[Dict[str, object]] = []

    for record in _records(submissions):
        flat = _flatten(record)
        kind = str(flat.get("submission_type") or "").strip().lower()

        # -- antimicrobial use, human -------------------------------------
        if kind == "amu":
            facility = _label("amu_facility", flat.get("amu_facility"))
            period = _label("amu_period", flat.get("amu_period"))
            if not facility or not period:
                continue
            patient_days = _number(flat.get("amu_patient_days"))
            for item in _repeats(record, "amu_items"):
                line = _flatten(item)
                quantity = _number(line.get("amu_quantity"))
                if quantity is None:
                    continue
                amu_rows.append({
                    "facility_name": facility,
                    "report_period": period,
                    "region": _label("amu_region", flat.get("amu_region")),
                    "district": _label("amu_district", flat.get("amu_district")),
                    "sector": "HUMAN",
                    "antibiotic_name": _named(line, "amu_antibiotic",
                                              "amu_antibiotic_other"),
                    "atc_code": _label("amu_atc", line.get("amu_atc")),
                    "aware_category": _label("amu_aware", line.get("amu_aware")),
                    "formulation": _label("amu_formulation",
                                          line.get("amu_formulation")),
                    "unit_of_measure": _label("amu_unit", line.get("amu_unit")),
                    "quantity_dispensed": quantity,
                    "ddd_per_1000": _number(line.get("amu_ddd")),
                    "patient_days": patient_days,
                })

        # -- antimicrobial consumption, animal and aquaculture -------------
        elif kind == "amc":
            period = _label("amc_period", flat.get("amc_period"))
            if not period:
                continue
            # The validator accepts only these two, in upper case.
            sector = (_label("amc_sector", flat.get("amc_sector")) or "").upper()
            if sector not in ("ANIMAL", "AQUACULTURE"):
                sector = "ANIMAL"
            biomass = _number(flat.get("amc_biomass"))
            species = _named(flat, "amc_species", "amc_species_other")
            for item in _repeats(record, "amc_items"):
                line = _flatten(item)
                quantity = _number(line.get("amc_quantity"))
                if quantity is None:
                    continue
                # mg/kg is derived rather than collected: asking for it as well
                # invites a figure that disagrees with the two it comes from.
                ratio = (quantity * 1_000_000.0 / biomass) if biomass else None
                amc_rows.append({
                    "report_period": period,
                    "region": _label("amc_region", flat.get("amc_region")),
                    "sector": sector,
                    "species": species,
                    "production_type": _label("amc_production",
                                              flat.get("amc_production")),
                    "antibiotic_class": _label("amc_class", line.get("amc_class")),
                    "antibiotic_name": _named(line, "amc_antibiotic",
                                              "amc_antibiotic_other"),
                    "atc_vet_code": _label("amc_atcvet", line.get("amc_atcvet")),
                    "quantity_kg": quantity,
                    "biomass_kg": biomass,
                    "mg_per_kg_biomass": ratio,
                    "route": _label("amc_route", line.get("amc_route")),
                    "purpose": _label("amc_purpose", line.get("amc_purpose")),
                })

        # -- point prevalence survey ---------------------------------------
        elif kind == "pps":
            facility = _label("pps_facility", flat.get("pps_facility"))
            survey_date = (str(flat.get("pps_date"))[:10]
                           if flat.get("pps_date") else None)
            if not facility or not survey_date:
                continue
            survey_rows.append({
                "facility_name": facility,
                "survey_date": survey_date,
                "region": _label("pps_region", flat.get("pps_region")),
                "district": _label("pps_district", flat.get("pps_district")),
                "total_patients": _number(flat.get("pps_total")),
                "patients_on_antibiotics": _number(flat.get("pps_on_antibiotics")),
            })
            for item in _repeats(record, "pps_items"):
                line = _flatten(item)
                agent = _named(line, "pps_antibiotic", "pps_antibiotic_other")
                if not agent:
                    continue
                rx_rows.append({
                    # the attribution key, carried on every prescription
                    "facility_name": facility,
                    "survey_date": survey_date,
                    "ward": _label("pps_ward", line.get("pps_ward")),
                    "ward_type": _label("pps_ward_type", line.get("pps_ward_type")),
                    "patient_age_group": _label("pps_age_group",
                                                line.get("pps_age_group")),
                    "antibiotic_name": agent,
                    "route": _label("pps_route", line.get("pps_route")),
                    "indication": _label("pps_indication",
                                         line.get("pps_indication")),
                    "indication_documented": _label("pps_documented",
                                                    line.get("pps_documented")),
                    "guideline_compliant": _label("pps_compliant",
                                                  line.get("pps_compliant")),
                    "duration_days": _number(line.get("pps_duration")),
                })

    return (pd.DataFrame(amu_rows), pd.DataFrame(amc_rows),
            pd.DataFrame(survey_rows), pd.DataFrame(rx_rows))


__all__ = [
    "FORM_VERSION", "GHANA_REGIONS", "COMMON_ORGANISMS", "COMMON_ANTIBIOTICS",
    "BREAKPOINT_EDITIONS", "ANIMAL_SPECIES", "FOOD_COMMODITIES",
    "TREATMENT_STAGES", "build_survey", "submissions_to_frames",
    "submissions_to_consumption",
]
