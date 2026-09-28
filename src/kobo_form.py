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

FORM_VERSION = "3.0"

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
    "Rifampicin", "Fusidic acid",
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
    ]

    choices: List[Dict[str, str]] = []
    choices += [{"list_name": "approved_labs", "name": code, "label": name}
                for name, code in APPROVED_LABS.items()]
    choices += _choices("submission_types", ["AST / isolate data"])
    choices[-1]["name"] = "ast"
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


__all__ = [
    "FORM_VERSION", "GHANA_REGIONS", "COMMON_ORGANISMS", "COMMON_ANTIBIOTICS",
    "BREAKPOINT_EDITIONS", "ANIMAL_SPECIES", "FOOD_COMMODITIES",
    "TREATMENT_STAGES", "build_survey", "submissions_to_frames",
]
