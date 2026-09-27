"""
The upload contract for the ICBB-AMRSS platform.

One declarative description of every column an upload may carry, used by three
consumers that previously each had their own idea of the format:

    * ``src.validate``   -- checks an uploaded workbook against it
    * ``build_template`` -- writes the blank workbook users download
    * ``src.ingest``     -- maps a validated workbook into the traceability chain

Keeping the three in one place is the point. The old template was written by a
function that hard-coded its own column list, so a column could be validated but
never offered, or offered but never stored.

Sheet model
-----------
``samples``      one row per **specimen**. The sheet name is kept for backward
                 compatibility with workbooks already in circulation; a row is
                 the material the laboratory received, together with the
                 subject it came from and, for human specimens, the care
                 episode around it.

``isolates``     one row per organism recovered from a specimen. This sheet is
                 the fix for the defect that made every count wrong: the old
                 format issued ``isolate_id`` per susceptibility test, so one
                 culture tested against six drugs was six isolates. Optional --
                 when absent, isolates are derived by grouping ``ast_results``
                 on specimen and organism, which is what the old files actually
                 meant.

``ast_results``  one row per isolate x antibiotic.

``genomics``     optional, one row per genomic result on an isolate. This is
                 what closes the phenotype-to-genotype link: a row here hangs
                 off the same ``isolate_id`` the AST rows do, so a sequence type
                 or a resistance gene resolves back through isolate ->
                 specimen -> ward -> patient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.traceability import (
    IDENTIFICATION_METHODS,
    PATIENT_TYPES,
    QC_STATUSES,
    REVIEW_STATUSES,
    SAMPLING_PURPOSES,
    SEX_VALUES,
    SPECIMEN_CONDITIONS,
    SPECIMEN_TYPES,
    WARD_TYPES,
)

# The legacy upload vocabulary is upper case and maps onto traceability
# sectors. Both spellings stay valid so existing workbooks keep loading.
SOURCE_CATEGORIES: Tuple[str, ...] = (
    "HUMAN", "ANIMAL", "FOOD", "ENVIRONMENT", "AQUACULTURE",
)

SECTOR_FOR_SOURCE_CATEGORY: Dict[str, str] = {
    "HUMAN": "human",
    "ANIMAL": "animal",
    "FOOD": "food",
    "ENVIRONMENT": "environment",
    "AQUACULTURE": "aquaculture",
}

AST_METHODS: Tuple[str, ...] = ("DD", "MIC")
BREAKPOINT_STANDARDS: Tuple[str, ...] = ("CLSI", "EUCAST")
RESULT_VALUES: Tuple[str, ...] = ("S", "I", "R", "NS")
MIC_OPERATORS: Tuple[str, ...] = ("=", "<", "<=", ">", ">=")
BOOLEAN_TRUE: Tuple[str, ...] = ("1", "y", "yes", "true", "t")
BOOLEAN_FALSE: Tuple[str, ...] = ("0", "n", "no", "false", "f")

# Values that mean "the cell was empty" once pandas and str() have been through
# it. Kept in one place because the old validator cast every object column to
# str and then tested isna(), which is never true for the string "nan".
NULL_TOKENS: Tuple[str, ...] = ("", "nan", "none", "null", "na", "n/a", "#n/a", "-")

# Free-text lists inside one cell are separated by this character. Chosen over
# a comma because organism and gene names contain commas.
LIST_SEPARATOR = ";"


# ---------------------------------------------------------------------------
# Column contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Column:
    """One column of one sheet.

    ``required`` means required for every row of every sector.
    ``required_for_sectors`` means required only when ``source_category`` is one
    of those values -- the mechanism that lets a single sheet serve a hospital
    blood culture and a wastewater grab without demanding patient fields of the
    latter.
    """

    name: str
    description: str
    kind: str = "text"          # text | date | time | number | integer | boolean | list
    required: bool = False
    required_for_sectors: Tuple[str, ...] = ()
    vocabulary: Optional[Tuple[str, ...]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    sectors: Tuple[str, ...] = ()   # () means "relevant to all sectors"
    sensitive: bool = False         # consumed at ingest, never persisted
    examples: Tuple[str, ...] = ()
    # Required of the *values* but not of the header. Used where the requirement
    # depends on what else the row holds, so a workbook that never triggers it
    # should not be rejected for lacking the column.
    header_optional: bool = False

    @property
    def is_conditional(self) -> bool:
        return bool(self.required_for_sectors)

    def applies_to_sector(self, source_category: str) -> bool:
        if not self.sectors:
            return True
        return str(source_category).strip().upper() in self.sectors


@dataclass(frozen=True)
class Sheet:
    name: str
    description: str
    columns: Tuple[Column, ...]
    optional: bool = False
    key_columns: Tuple[str, ...] = ()

    @property
    def column_names(self) -> Tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    @property
    def header_required_columns(self) -> Tuple[str, ...]:
        """Columns whose header must be present for the sheet to load at all.

        Only the unconditional ones. A column that is required for human
        specimens is checked against the rows that are actually present, so a
        purely environmental workbook is not asked for a ward type it has no
        use for -- and a workbook that does carry human specimens is told,
        once and by name, that the column is missing.
        """
        return tuple(c.name for c in self.columns
                     if c.required and not c.header_optional)

    @property
    def conditional_columns(self) -> Tuple[Column, ...]:
        """Columns required only for particular sectors."""
        return tuple(c for c in self.columns if c.is_conditional)

    def column(self, name: str) -> Optional[Column]:
        for c in self.columns:
            if c.name == name:
                return c
        return None


# ---------------------------------------------------------------------------
# samples sheet -- one row per specimen
# ---------------------------------------------------------------------------

_SAMPLES_CORE = (
    Column("sample_id", "Laboratory identifier for this specimen. Unique in the file.",
           required=True, examples=("GH-2601-0001",)),
    Column("lab_name", "Reporting laboratory. Must be one of the approved laboratories.",
           required=True),
    Column("collection_date", "Date the specimen was taken (YYYY-MM-DD).",
           kind="date", required=True, examples=("2026-01-14",)),
    Column("collection_time", "Time the specimen was taken (HH:MM, 24-hour). Optional.",
           kind="time", examples=("08:30",)),
    Column("source_category", "Sector this specimen belongs to.",
           required=True, vocabulary=SOURCE_CATEGORIES),
    Column("source_type", "Local description of the source within the sector.",
           examples=("clinical_specimen", "raw_chicken", "treated_water")),
    Column("site_type", "Kind of site sampled.",
           examples=("Teaching hospital", "Retail market")),
    Column("region", "Region.", required=True, examples=("Greater Accra",)),
    Column("district", "District.", required=True, examples=("Accra Metropolitan",)),
    Column("latitude", "Decimal degrees.", kind="number", minimum=-90, maximum=90),
    Column("longitude", "Decimal degrees.", kind="number", minimum=-180, maximum=180),
)

_SAMPLES_SPECIMEN = (
    Column("accession_number",
           "Laboratory accession or register number, if different from sample_id."),
    Column("specimen_type",
           "Specimen category. Drives sterile-site logic and deduplication, so an "
           "accurate value matters.",
           vocabulary=SPECIMEN_TYPES, required_for_sectors=("HUMAN",)),
    Column("specimen_detail", "Free text for local naming that the category loses.",
           examples=("Left leg ulcer swab",)),
    Column("collected_by", "Person or team who took the specimen."),
    Column("receipt_date",
           "Date the laboratory received the specimen (YYYY-MM-DD). Must not "
           "precede collection_date.", kind="date"),
    Column("receipt_time", "Time of receipt (HH:MM).", kind="time"),
    Column("condition_on_receipt", "Condition the specimen arrived in.",
           vocabulary=SPECIMEN_CONDITIONS),
    Column("rejection_reason",
           "Required when condition_on_receipt is Rejected."),
    Column("sampling_purpose",
           "Why the specimen was taken. Separates diagnostic isolates from "
           "screening and outbreak work, which must not be pooled into one rate.",
           vocabulary=SAMPLING_PURPOSES),
)

_SAMPLES_HUMAN = (
    Column("facility_code",
           "Short code for the facility. Scopes the patient pseudonym, so it must "
           "be stable over time.",
           required_for_sectors=("HUMAN",), sectors=("HUMAN",), examples=("KBTH",)),
    Column("facility_name", "Facility name.", sectors=("HUMAN",)),
    Column("local_patient_id",
           "The hospital's own patient number. Hashed with the facility salt at "
           "upload and then discarded -- the platform never stores it. Needed so "
           "repeat specimens from one patient link together.",
           required_for_sectors=("HUMAN",), sectors=("HUMAN",), sensitive=True),
    Column("sex", "Patient sex.", vocabulary=SEX_VALUES, sectors=("HUMAN",)),
    Column("age_years",
           "Age in years at collection. Use a fraction for infants (0.25 = three "
           "months).", kind="number", minimum=0, maximum=130, sectors=("HUMAN",)),
    Column("patient_type", "Care setting.", vocabulary=PATIENT_TYPES,
           sectors=("HUMAN",)),
    Column("ward", "Ward the patient was admitted to, as named locally.",
           sectors=("HUMAN",)),
    Column("ward_type", "Standardised ward category for the admission ward.",
           vocabulary=WARD_TYPES, required_for_sectors=("HUMAN",), sectors=("HUMAN",)),
    Column("ward_at_collection",
           "Ward where this specimen was taken, if different from the admission "
           "ward.", sectors=("HUMAN",)),
    Column("ward_type_at_collection",
           "Standardised category for the collection ward. Left blank, the "
           "admission ward type is used.",
           vocabulary=WARD_TYPES, sectors=("HUMAN",)),
    Column("admission_date",
           "Admission date (YYYY-MM-DD). Needed to separate community-onset from "
           "healthcare-associated infection.", kind="date", sectors=("HUMAN",)),
    Column("discharge_date",
           "Discharge date (YYYY-MM-DD), if the episode has ended.",
           kind="date", sectors=("HUMAN",)),
    Column("admission_source", "Where the patient came from.", sectors=("HUMAN",),
           examples=("Home", "Referral from district hospital")),
)

_SAMPLES_NONHUMAN = (
    Column("animal_species", "Species sampled.", sectors=("ANIMAL", "AQUACULTURE")),
    Column("production_type", "Production system.", sectors=("ANIMAL", "AQUACULTURE"),
           examples=("Layer", "Broiler", "Pond")),
    Column("herd_flock_id",
           "Herd, flock or pond identifier. Links repeat sampling of the same unit.",
           sectors=("ANIMAL", "AQUACULTURE")),
    Column("food_commodity", "Commodity sampled.", sectors=("FOOD",)),
    Column("food_matrix", "Food matrix, retained from the original template.",
           sectors=("FOOD",)),
    Column("food_stage", "Point in the chain.", sectors=("FOOD",),
           examples=("Retail", "Slaughterhouse")),
    Column("water_body", "Named water body.", sectors=("ENVIRONMENT", "AQUACULTURE")),
    Column("catchment", "Catchment or basin.", sectors=("ENVIRONMENT",)),
    Column("treatment_stage", "Stage relative to treatment.", sectors=("ENVIRONMENT",),
           examples=("Influent", "Effluent", "Treated")),
    Column("environment_matrix",
           "Environmental matrix, retained from the original template.",
           sectors=("ENVIRONMENT",)),
    Column("sampling_point", "Precise sampling point description.",
           sectors=("ENVIRONMENT", "AQUACULTURE")),
)

SAMPLES_SHEET = Sheet(
    name="samples",
    description="One row per specimen received by the laboratory.",
    columns=_SAMPLES_CORE + _SAMPLES_SPECIMEN + _SAMPLES_HUMAN + _SAMPLES_NONHUMAN,
    key_columns=("sample_id",),
)


# ---------------------------------------------------------------------------
# isolates sheet -- one row per organism recovered
# ---------------------------------------------------------------------------

ISOLATES_SHEET = Sheet(
    name="isolates",
    description=("One row per organism recovered from a specimen. One culture "
                 "tested against twelve drugs is ONE row here and twelve rows in "
                 "ast_results."),
    optional=True,
    key_columns=("isolate_id",),
    columns=(
        Column("sample_id", "The specimen this organism was recovered from.",
               required=True),
        Column("isolate_id",
               "Identifier for this isolate. Unique in the file, and the value "
               "every ast_results and genomics row refers to.",
               required=True, examples=("GH-2601-0001-1",)),
        Column("isolate_number",
               "Sequence number within the specimen: 1 for the first organism, 2 "
               "for a second, and so on.", kind="integer", minimum=1),
        Column("organism", "Organism identified.", required=True,
               examples=("Escherichia coli",)),
        Column("organism_code", "WHONET organism code, if known.", examples=("eco",)),
        Column("identification_method", "How the organism was identified.",
               vocabulary=IDENTIFICATION_METHODS),
        Column("identification_date", "Date of identification (YYYY-MM-DD).",
               kind="date"),
        Column("is_significant",
               "Whether the laboratory judged this a clinically significant isolate "
               "rather than colonisation or contamination. Yes/No.", kind="boolean"),
        Column("notes", "Free text."),
    ),
)


# ---------------------------------------------------------------------------
# ast_results sheet -- one row per isolate x antibiotic
# ---------------------------------------------------------------------------

AST_SHEET = Sheet(
    name="ast_results",
    description="One row per antibiotic tested against one isolate.",
    key_columns=("isolate_id", "antibiotic"),
    columns=(
        Column("sample_id", "The specimen. Cross-checked against the isolate.",
               required=True),
        Column("isolate_id", "The isolate tested.", required=True),
        Column("organism",
               "Organism. Required when no isolates sheet is supplied, since "
               "isolates are then derived from this column.", required=True),
        Column("antibiotic", "Antibiotic tested.", required=True,
               examples=("Ciprofloxacin",)),
        Column("method",
               "Testing method: DD for disc diffusion, MIC for a quantitative "
               "method.", required=True, vocabulary=AST_METHODS),
        Column("ast_instrument", "Instrument used, if automated.",
               examples=("VITEK 2",)),
        Column("mic_operator",
               "Censoring operator for the MIC, when the value is a limit rather "
               "than a point estimate.", vocabulary=MIC_OPERATORS),
        Column("mic_value", "MIC in mg/L.", kind="number", minimum=0),
        Column("zone_diameter", "Inhibition zone in mm.", kind="number",
               minimum=0, maximum=100),
        Column("result",
               "S, I, R, or NS. Leave blank to have the platform derive it from "
               "the measurement.", vocabulary=RESULT_VALUES),
        Column("guideline", "Breakpoint standard behind the interpretation.",
               required=True, vocabulary=BREAKPOINT_STANDARDS),
        Column("guideline_version",
               "Edition of that standard, for example M100-Ed34 or 2024. Required "
               "whenever a result is given: breakpoints move between editions, so "
               "an S/I/R with no version cannot be reproduced.",
               required=True, header_optional=True, examples=("M100-Ed34",)),
        Column("qc_status", "Whether the run's quality control passed.",
               vocabulary=QC_STATUSES),
        Column("qc_strain", "QC organism used.", examples=("ATCC 25922",)),
        Column("test_date", "Date the susceptibility test was read (YYYY-MM-DD).",
               kind="date"),
        Column("verified_by", "Person who verified the result."),
        Column("notes", "Free text."),
    ),
)


# ---------------------------------------------------------------------------
# genomics sheet -- optional, one row per genomic result
# ---------------------------------------------------------------------------

GENOMICS_SHEET = Sheet(
    name="genomics",
    description=("Optional. One row per genomic result, attached to the same "
                 "isolate_id as the susceptibility rows, which is what links "
                 "genotype to phenotype."),
    optional=True,
    key_columns=("genomic_id",),
    columns=(
        Column("genomic_id", "Identifier for this genomic result.", required=True),
        Column("isolate_id",
               "The isolate sequenced. Must appear in the isolates or ast_results "
               "sheet.", required=True),
        Column("run_id", "Sequencing run identifier."),
        Column("platform", "Sequencing platform.", examples=("Illumina MiSeq",)),
        Column("instrument", "Instrument identifier."),
        Column("run_date", "Run date (YYYY-MM-DD).", kind="date"),
        Column("library_id", "Library or barcode identifier."),
        Column("read_path",
               "Governed storage path to the reads. The platform stores the "
               "pointer, never the file."),
        Column("read_checksum",
               "Checksum of the reads. Required whenever read_path is given, "
               "otherwise the pointer cannot be verified later."),
        Column("assembly_path", "Storage path to the assembly."),
        Column("assembly_checksum", "Checksum of the assembly."),
        Column("total_reads", "Read count.", kind="number", minimum=0),
        Column("mean_depth", "Mean depth of coverage.", kind="number", minimum=0),
        Column("coverage_breadth", "Percentage of the reference covered.",
               kind="number", minimum=0, maximum=100),
        Column("contamination_pct", "Estimated contamination, percent.",
               kind="number", minimum=0, maximum=100),
        Column("n50", "Assembly N50.", kind="number", minimum=0),
        Column("contig_count", "Number of contigs.", kind="integer", minimum=0),
        Column("qc_status", "Whether the assembly passed QC.", vocabulary=QC_STATUSES),
        Column("assembler", "Assembler used.", examples=("SPAdes",)),
        Column("assembler_version", "Assembler version."),
        Column("pipeline_name", "Analysis pipeline.", examples=("bactopia",)),
        Column("pipeline_version", "Pipeline version."),
        Column("amr_db_name", "Resistance database used.", examples=("ResFinder",)),
        Column("amr_db_version",
               "Database version. A gene call is only interpretable against the "
               "database version that made it."),
        Column("species_confirmed",
               "Species confirmed from sequence, if it differs from the phenotypic "
               "identification."),
        Column("mlst_scheme", "MLST scheme.", examples=("ecoli_achtman_4",)),
        Column("sequence_type", "Sequence type.", examples=("ST131",)),
        Column("amr_genes", "Resistance genes, separated by a semicolon.",
               kind="list", examples=("blaCTX-M-15;qnrS1",)),
        Column("amr_mutations", "Resistance mutations, separated by a semicolon.",
               kind="list", examples=("gyrA_S83L;parC_S80I",)),
        Column("plasmid_replicons", "Plasmid replicons, separated by a semicolon.",
               kind="list", examples=("IncFII;IncI1",)),
        Column("virulence_genes", "Virulence genes, separated by a semicolon.",
               kind="list"),
        Column("cluster_method", "Clustering method.", examples=("cgMLST",)),
        Column("cluster_id",
               "Cluster identifier. Equal values across patients are what suggest "
               "transmission."),
        Column("analysis_date", "Date of analysis (YYYY-MM-DD).", kind="date"),
        Column("analysed_by", "Analyst."),
        Column("review_status", "Whether a human has reviewed the call.",
               vocabulary=REVIEW_STATUSES),
        Column("reviewed_by", "Reviewer. Required when review_status is Accepted."),
    ),
)


SHEETS: Tuple[Sheet, ...] = (SAMPLES_SHEET, ISOLATES_SHEET, AST_SHEET, GENOMICS_SHEET)
SHEETS_BY_NAME: Dict[str, Sheet] = {s.name: s for s in SHEETS}

#: Sheets a workbook must contain to be loadable at all.
MANDATORY_SHEETS: Tuple[str, ...] = tuple(s.name for s in SHEETS if not s.optional)

TEMPLATE_VERSION = "2.0"
TEMPLATE_FILENAME = f"ICBB-AMRSS_upload_template_v{TEMPLATE_VERSION}.xlsx"


def sheet_for(name: str) -> Optional[Sheet]:
    return SHEETS_BY_NAME.get(name)


def sensitive_columns() -> Tuple[str, ...]:
    """Columns consumed during ingestion and never written to the database."""
    return tuple(c.name for s in SHEETS for c in s.columns if c.sensitive)


def is_blank(value) -> bool:
    """Whether a spreadsheet cell should be treated as empty.

    Handles the three ways a blank arrives: a real NaN, an empty string, and
    the literal text "nan" left behind when a NaN has been through ``str()``.
    """
    if value is None:
        return True
    try:
        import pandas as pd
        if pd.isna(value):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    return str(value).strip().lower() in NULL_TOKENS


def clean_text(value) -> Optional[str]:
    """Return a stripped string, or None when the cell is blank."""
    if is_blank(value):
        return None
    return str(value).strip()


def parse_bool(value) -> Optional[bool]:
    """Parse the spreadsheet spellings of yes and no. Unknown text is None."""
    text = clean_text(value)
    if text is None or text.lower() == "unknown":
        return None
    lowered = text.lower()
    if lowered in BOOLEAN_TRUE:
        return True
    if lowered in BOOLEAN_FALSE:
        return False
    return None


def parse_list(value) -> List[str]:
    """Split a separated cell into a clean list. Empty cells give []."""
    text = clean_text(value)
    if text is None:
        return []
    return [part.strip() for part in text.split(LIST_SEPARATOR) if part.strip()]


__all__ = [
    "Column", "Sheet",
    "SOURCE_CATEGORIES", "SECTOR_FOR_SOURCE_CATEGORY",
    "AST_METHODS", "BREAKPOINT_STANDARDS", "RESULT_VALUES", "MIC_OPERATORS",
    "LIST_SEPARATOR", "NULL_TOKENS",
    "SAMPLES_SHEET", "ISOLATES_SHEET", "AST_SHEET", "GENOMICS_SHEET",
    "SHEETS", "SHEETS_BY_NAME", "MANDATORY_SHEETS",
    "TEMPLATE_VERSION", "TEMPLATE_FILENAME",
    "sheet_for", "sensitive_columns", "is_blank", "clean_text",
    "parse_bool", "parse_list",
]
