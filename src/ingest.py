"""
Writes a validated upload into the traceability chain.

``src.db.save_dataset`` stored two wide rows per record -- a ``samples`` row and
an ``ast_results`` row -- and nothing else. The traceability tables existed but
nothing ever populated them, so no result could be followed back to a ward or a
patient.

This module is that missing step. One validated workbook becomes:

    subjects -> encounters -> specimens -> isolates -> phenotypes
                                                  \\-> genomic_results
    sequencing_runs                                    custody_events

all inside one transaction, together with the legacy ``samples`` and
``ast_results`` rows that the existing analytics and report pages still read.
Either the whole upload lands or none of it does; a half-written chain is worse
than a rejected file.

Identity
--------
The hard question in ingestion is what counts as the same subject across two
specimens. The answer here is: whatever stable identifier the uploader actually
supplied, and nothing inferred beyond it.

* **human** -- the salted patient pseudonym. Two specimens from one patient at
  one facility share a subject, which is what makes first-isolate-per-patient
  deduplication and repeat-infection detection possible.
* **animal, aquaculture** -- the herd, flock or pond identifier when given.
* **environment** -- the water body and sampling point together, when both are
  given, so repeat sampling of one outfall links up.
* **anything else** -- the specimen is its own subject. Guessing that two
  market samples of chicken came from one source would invent an epidemiological
  link that was never recorded.

Patient identifiers
-------------------
``local_patient_id`` is read, hashed with the facility salt, and dropped. It is
never written to any table and never logged. If the salt is not configured the
ingestion of human specimens fails rather than proceeding unsalted, because a
hash of a hospital number with no salt is reversible by brute force over the
hospital's number range.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd
import psycopg2.extras

from src import db
from src.traceability import (
    make_patient_pseudonym,
    record_custody_event,
)
from src.upload_schema import is_blank

logger = logging.getLogger(__name__)

BATCH = 500

#: Written into ``custody_events.source_system`` so an event's origin is
#: distinguishable from one recorded by a laboratory interface later.
SOURCE_SYSTEM = "workbook-upload"


@dataclass
class IngestResult:
    ok: bool
    message: str
    counts: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _value(row, key):
    """Read a cell from a Series, mapping every emptiness spelling to None."""
    if key not in row:
        return None
    value = row[key]
    return None if is_blank(value) else value


def _text(row, key) -> Optional[str]:
    value = _value(row, key)
    return None if value is None else str(value).strip()


def _number(row, key) -> Optional[float]:
    value = _value(row, key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(row, key) -> Optional[_dt.date]:
    value = _value(row, key)
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date()
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _bool(row, key) -> Optional[bool]:
    value = _value(row, key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "y", "yes")


def _jsonb(row, key) -> Optional[str]:
    """Render a parsed list as JSON for a JSONB column. Empty becomes NULL."""
    value = row[key] if key in row else None
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        value = [part.strip() for part in value.split(";") if part.strip()]
    if not isinstance(value, (list, tuple)):
        return None
    items = [str(v) for v in value if str(v).strip()]
    return json.dumps(items) if items else None


def _insert_many(raw_cur, sql: str, rows: Sequence[tuple]) -> int:
    if not rows:
        return 0
    psycopg2.extras.execute_values(raw_cur, sql, rows, page_size=BATCH)
    return len(rows)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def _subject_identity(row) -> Tuple[str, str]:
    """Return (subject_id, how that identity was established).

    The second element is recorded in the custody log, so a later reader can
    tell whether two specimens were linked by a patient pseudonym or merely
    because they happened to be the only specimen of their subject.
    """
    sector = (_text(row, "sector") or "").lower()
    sample_id = _text(row, "sample_id") or ""

    if sector == "human":
        pseudonym = _text(row, "patient_pseudonym")
        if pseudonym:
            return pseudonym, "patient pseudonym"
        return f"specimen:{sample_id}", "specimen (no patient identifier)"

    if sector in ("animal", "aquaculture"):
        unit = _text(row, "herd_flock_id")
        if unit:
            return f"{sector}:{unit}", "herd, flock or pond identifier"

    if sector == "environment":
        water = _text(row, "water_body")
        point = _text(row, "sampling_point")
        if water and point:
            return f"environment:{water}|{point}", "water body and sampling point"

    return f"specimen:{sample_id}", "specimen (no grouping identifier supplied)"


def _encounter_identity(row, subject_id: str) -> Optional[Tuple[str, str]]:
    """Return (encounter_id, basis) for a human specimen, else None.

    An encounter is one care episode. Admission date is what delimits it; when
    it is absent the collection date stands in, which keeps the ward attached to
    something but cannot group two specimens from one admission. The basis is
    recorded so that limitation is visible in the data rather than assumed away.
    """
    if (_text(row, "sector") or "").lower() != "human":
        return None

    facility = _text(row, "facility_code") or "UNKNOWN"
    admission = _date(row, "admission_date")
    if admission is not None:
        return f"{subject_id}|{facility}|{admission.isoformat()}", "admission date"

    collection = _date(row, "collection_date")
    if collection is not None:
        return (f"{subject_id}|{facility}|collection:{collection.isoformat()}",
                "collection date (no admission date supplied)")
    return None


def _pseudonymise(samples: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Add ``patient_pseudonym`` and drop the hospital patient number.

    Raises RuntimeError when a human specimen is present and no salt is
    configured. The column is removed from the frame on the way out, so no
    caller downstream can persist or log it by accident.
    """
    notes: List[str] = []
    out = samples.copy()
    out["patient_pseudonym"] = None

    if "local_patient_id" not in out.columns:
        return out, notes

    human = out["sector"].astype(str).str.lower() == "human" if "sector" in out.columns else pd.Series(False, index=out.index)
    pseudonyms: List[Optional[str]] = []
    for index, row in out.iterrows():
        if not bool(human.get(index, False)):
            pseudonyms.append(None)
            continue
        facility = _text(row, "facility_code")
        local = _text(row, "local_patient_id")
        if not facility or not local:
            pseudonyms.append(None)
            continue
        pseudonyms.append(make_patient_pseudonym(facility, local))
    out["patient_pseudonym"] = pseudonyms

    out = out.drop(columns=["local_patient_id"])
    linked = sum(1 for p in pseudonyms if p)
    if linked:
        distinct = len({p for p in pseudonyms if p})
        notes.append(
            f"{linked} human specimen(s) resolved to {distinct} patient(s). "
            "Hospital patient numbers were hashed with the facility salt and "
            "discarded; they are not stored.")
    return out, notes


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

_SUBJECT_COLUMNS = (
    "dataset_id", "subject_id", "sector", "patient_pseudonym", "facility_code",
    "sex", "age_years", "age_band", "animal_species", "production_type",
    "herd_flock_id", "food_commodity", "food_stage", "water_body", "catchment",
    "treatment_stage", "sampling_point", "created_by",
)

_ENCOUNTER_COLUMNS = (
    "dataset_id", "encounter_id", "subject_id", "facility_code", "facility_name",
    "ward", "ward_type", "patient_type", "admission_date", "discharge_date",
    "admission_source", "created_by",
)

_SPECIMEN_COLUMNS = (
    "dataset_id", "specimen_id", "subject_id", "encounter_id",
    "accession_number", "specimen_type", "specimen_detail",
    "collection_datetime", "collected_by", "ward_at_collection",
    "ward_type_at_collection", "age_years_at_collection",
    "age_band_at_collection", "receipt_datetime", "condition_on_receipt",
    "rejection_reason", "sampling_purpose", "lab_name", "region", "district",
    "latitude", "longitude", "created_by",
)

_ISOLATE_COLUMNS = (
    "dataset_id", "isolate_id", "specimen_id", "isolate_number", "organism",
    "organism_code", "identification_method", "identification_date",
    "is_significant", "notes", "created_by",
)

_PHENOTYPE_COLUMNS = (
    "dataset_id", "isolate_id", "antibiotic", "result", "mic_value",
    "mic_operator", "zone_diameter", "ast_method", "ast_instrument",
    "breakpoint_standard", "breakpoint_version", "result_source", "qc_status",
    "qc_strain", "test_date", "verified_by", "notes", "created_by",
)

_GENOMIC_COLUMNS = (
    "dataset_id", "genomic_id", "isolate_id", "run_id", "library_id",
    "read_path", "read_checksum", "assembly_path", "assembly_checksum",
    "total_reads", "mean_depth", "coverage_breadth", "contamination_pct",
    "n50", "contig_count", "qc_status", "assembler", "assembler_version",
    "pipeline_name", "pipeline_version", "amr_db_name", "amr_db_version",
    "species_confirmed", "mlst_scheme", "sequence_type", "amr_genes",
    "amr_mutations", "plasmid_replicons", "virulence_genes", "cluster_method",
    "cluster_id", "analysis_date", "analysed_by", "review_status",
    "reviewed_by", "created_by",
)


def _insert_sql(table: str, columns: Sequence[str],
                conflict: str = "") -> str:
    return (f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
            + (conflict or "ON CONFLICT DO NOTHING"))


def _build_subjects(samples: pd.DataFrame, dataset_id: str,
                    actor: str) -> Tuple[List[tuple], Dict[str, str], Dict[str, str]]:
    """One row per distinct subject. Returns rows, sample->subject, basis map."""
    subjects: Dict[str, tuple] = {}
    basis: Dict[str, str] = {}
    sample_to_subject: Dict[str, str] = {}

    for _, row in samples.iterrows():
        sample_id = _text(row, "sample_id")
        if not sample_id:
            continue
        subject_id, how = _subject_identity(row)
        sample_to_subject[sample_id] = subject_id
        if subject_id in subjects:
            continue
        basis[subject_id] = how
        subjects[subject_id] = (
            dataset_id, subject_id, _text(row, "sector"),
            _text(row, "patient_pseudonym"), _text(row, "facility_code"),
            _text(row, "sex"), _number(row, "age_years"), _text(row, "age_band"),
            _text(row, "animal_species"), _text(row, "production_type"),
            _text(row, "herd_flock_id"), _text(row, "food_commodity"),
            _text(row, "food_stage"), _text(row, "water_body"),
            _text(row, "catchment"), _text(row, "treatment_stage"),
            _text(row, "sampling_point"), actor,
        )
    return list(subjects.values()), sample_to_subject, basis


def _build_encounters(samples: pd.DataFrame, dataset_id: str, actor: str,
                      sample_to_subject: Dict[str, str]
                      ) -> Tuple[List[tuple], Dict[str, str], Dict[str, str]]:
    encounters: Dict[str, tuple] = {}
    basis: Dict[str, str] = {}
    sample_to_encounter: Dict[str, str] = {}

    for _, row in samples.iterrows():
        sample_id = _text(row, "sample_id")
        if not sample_id:
            continue
        subject_id = sample_to_subject.get(sample_id)
        if not subject_id:
            continue
        identity = _encounter_identity(row, subject_id)
        if identity is None:
            continue
        encounter_id, how = identity
        sample_to_encounter[sample_id] = encounter_id
        if encounter_id in encounters:
            continue
        basis[encounter_id] = how
        encounters[encounter_id] = (
            dataset_id, encounter_id, subject_id, _text(row, "facility_code"),
            _text(row, "facility_name"), _text(row, "ward"),
            _text(row, "ward_type"), _text(row, "patient_type"),
            _date(row, "admission_date"), _date(row, "discharge_date"),
            _text(row, "admission_source"), actor,
        )
    return list(encounters.values()), sample_to_encounter, basis


def _build_specimens(samples: pd.DataFrame, dataset_id: str, actor: str,
                     sample_to_subject: Dict[str, str],
                     sample_to_encounter: Dict[str, str]) -> List[tuple]:
    rows: List[tuple] = []
    for _, row in samples.iterrows():
        sample_id = _text(row, "sample_id")
        if not sample_id or sample_id not in sample_to_subject:
            continue
        rows.append((
            dataset_id, sample_id, sample_to_subject[sample_id],
            sample_to_encounter.get(sample_id),
            _text(row, "accession_number"), _text(row, "specimen_type"),
            _text(row, "specimen_detail"), _text(row, "collection_datetime"),
            _text(row, "collected_by"), _text(row, "ward_at_collection"),
            _text(row, "ward_type_at_collection"), _number(row, "age_years"),
            _text(row, "age_band"), _text(row, "receipt_datetime"),
            _text(row, "condition_on_receipt"), _text(row, "rejection_reason"),
            _text(row, "sampling_purpose"), _text(row, "lab_name"),
            _text(row, "region"), _text(row, "district"),
            _number(row, "latitude"), _number(row, "longitude"), actor,
        ))
    return rows


def _build_isolates(isolates: pd.DataFrame, dataset_id: str, actor: str,
                    known_specimens: set) -> List[tuple]:
    rows: List[tuple] = []
    for _, row in isolates.iterrows():
        isolate_id = _text(row, "isolate_id")
        specimen_id = _text(row, "sample_id")
        if not isolate_id or specimen_id not in known_specimens:
            continue
        number = _number(row, "isolate_number")
        rows.append((
            dataset_id, isolate_id, specimen_id,
            int(number) if number else 1,
            _text(row, "organism"), _text(row, "organism_code"),
            _text(row, "identification_method"),
            _date(row, "identification_date"), _bool(row, "is_significant"),
            _text(row, "notes"), actor,
        ))
    return rows


def _build_phenotypes(ast: pd.DataFrame, dataset_id: str, actor: str,
                      known_isolates: set) -> List[tuple]:
    rows: List[tuple] = []
    seen: set = set()
    for _, row in ast.iterrows():
        isolate_id = _text(row, "isolate_id")
        antibiotic = _text(row, "antibiotic")
        if not isolate_id or not antibiotic or isolate_id not in known_isolates:
            continue
        key = (isolate_id, antibiotic)
        if key in seen:
            continue
        seen.add(key)
        rows.append((
            dataset_id, isolate_id, antibiotic, _text(row, "result"),
            _number(row, "mic_value"), _text(row, "mic_operator"),
            _number(row, "zone_diameter"), _text(row, "method"),
            _text(row, "ast_instrument"), _text(row, "guideline"),
            _text(row, "guideline_version"), _text(row, "result_source"),
            _text(row, "qc_status"), _text(row, "qc_strain"),
            _date(row, "test_date"), _text(row, "verified_by"),
            _text(row, "notes"), actor,
        ))
    return rows


def _build_sequencing_runs(genomics: pd.DataFrame, dataset_id: str,
                           actor: str) -> List[tuple]:
    runs: Dict[str, tuple] = {}
    for _, row in genomics.iterrows():
        run_id = _text(row, "run_id")
        if not run_id or run_id in runs:
            continue
        runs[run_id] = (
            dataset_id, run_id, _text(row, "platform"),
            _text(row, "instrument"), None, None, _date(row, "run_date"),
            None, _text(row, "analysed_by"), actor,
        )
    return list(runs.values())


def _build_genomics(genomics: pd.DataFrame, dataset_id: str, actor: str,
                    known_isolates: set) -> List[tuple]:
    rows: List[tuple] = []
    for _, row in genomics.iterrows():
        genomic_id = _text(row, "genomic_id")
        isolate_id = _text(row, "isolate_id")
        if not genomic_id or isolate_id not in known_isolates:
            continue
        contig_count = _number(row, "contig_count")
        rows.append((
            dataset_id, genomic_id, isolate_id, _text(row, "run_id"),
            _text(row, "library_id"), _text(row, "read_path"),
            _text(row, "read_checksum"), _text(row, "assembly_path"),
            _text(row, "assembly_checksum"), _number(row, "total_reads"),
            _number(row, "mean_depth"), _number(row, "coverage_breadth"),
            _number(row, "contamination_pct"), _number(row, "n50"),
            int(contig_count) if contig_count is not None else None,
            _text(row, "qc_status"), _text(row, "assembler"),
            _text(row, "assembler_version"), _text(row, "pipeline_name"),
            _text(row, "pipeline_version"), _text(row, "amr_db_name"),
            _text(row, "amr_db_version"), _text(row, "species_confirmed"),
            _text(row, "mlst_scheme"), _text(row, "sequence_type"),
            _jsonb(row, "amr_genes"), _jsonb(row, "amr_mutations"),
            _jsonb(row, "plasmid_replicons"), _jsonb(row, "virulence_genes"),
            _text(row, "cluster_method"), _text(row, "cluster_id"),
            _date(row, "analysis_date"), _text(row, "analysed_by"),
            _text(row, "review_status"), _text(row, "reviewed_by"), actor,
        ))
    return rows


# ---------------------------------------------------------------------------
# Legacy wide tables
# ---------------------------------------------------------------------------

_LEGACY_SAMPLE_COLUMNS = (
    "dataset_id", "sample_id", "lab_name", "collection_date", "region",
    "district", "site_type", "source_category", "source_type", "food_matrix",
    "environment_matrix", "latitude", "longitude",
)

_LEGACY_AST_COLUMNS = (
    "dataset_id", "sample_id", "isolate_id", "organism", "antibiotic", "result",
    "method", "guideline", "test_date", "mic_value", "zone_diameter",
    "auto_interpreted", "interpreted_result", "interpretation_guideline",
    "interpretation_confidence", "suspected_mechanism", "interpretation_notes",
)


def _build_legacy_samples(samples: pd.DataFrame, dataset_id: str) -> List[tuple]:
    rows: List[tuple] = []
    for _, row in samples.iterrows():
        sample_id = _text(row, "sample_id")
        if not sample_id:
            continue
        collection = _date(row, "collection_date")
        rows.append((
            dataset_id, sample_id, _text(row, "lab_name"),
            collection.isoformat() if collection else None,
            _text(row, "region"), _text(row, "district"),
            _text(row, "site_type"), _text(row, "source_category"),
            _text(row, "source_type"), _text(row, "food_matrix"),
            _text(row, "environment_matrix"), _number(row, "latitude"),
            _number(row, "longitude"),
        ))
    return rows


def _build_legacy_ast(ast: pd.DataFrame, dataset_id: str) -> List[tuple]:
    """Legacy AST rows.

    ``zone_diameter`` and every interpretation column are written here. The
    previous writer validated and interpreted them and then stored neither, so
    a disc-diffusion measurement was accepted, used to derive an S/I/R, and
    then thrown away.
    """
    rows: List[tuple] = []
    seen: set = set()
    for _, row in ast.iterrows():
        isolate_id = _text(row, "isolate_id")
        antibiotic = _text(row, "antibiotic")
        if not isolate_id or not antibiotic:
            continue
        key = (isolate_id, antibiotic)
        if key in seen:
            continue
        seen.add(key)
        test_date = _date(row, "test_date")
        rows.append((
            dataset_id, _text(row, "sample_id"), isolate_id,
            _text(row, "organism"), antibiotic, _text(row, "result"),
            _text(row, "method"), _text(row, "guideline"),
            test_date.isoformat() if test_date else None,
            _number(row, "mic_value"), _number(row, "zone_diameter"),
            1 if _bool(row, "auto_interpreted") else 0,
            _text(row, "interpreted_result"),
            _text(row, "interpretation_guideline"),
            _text(row, "interpretation_confidence"),
            _text(row, "suspected_mechanism"),
            _text(row, "interpretation_notes"),
        ))
    return rows


# ---------------------------------------------------------------------------
# Custody log
# ---------------------------------------------------------------------------

def _log_custody(cur, dataset_id: str, actor: str, samples: pd.DataFrame,
                 isolates: pd.DataFrame, genomics: pd.DataFrame,
                 sample_to_subject: Dict[str, str],
                 subject_basis: Dict[str, str],
                 phenotype_counts: Dict[str, int]) -> int:
    """Record the handoffs this upload evidences.

    Granularity is deliberate. A susceptibility panel run against one isolate is
    one laboratory action, so it is one ``ast_performed`` event carrying the
    number of drugs, not one event per drug: inflating the log would make it
    harder to read without recording anything more.
    """
    written = 0

    for subject_id, how in subject_basis.items():
        record_custody_event(
            cur, dataset_id, "subject", subject_id, "transferred",
            actor=actor, source_system=SOURCE_SYSTEM,
            reason=f"subject identity established from {how}")
        written += 1

    for _, row in samples.iterrows():
        sample_id = _text(row, "sample_id")
        if not sample_id or sample_id not in sample_to_subject:
            continue
        record_custody_event(
            cur, dataset_id, "specimen", sample_id, "collected", actor=actor,
            event_datetime=_text(row, "collection_datetime"),
            site=_text(row, "ward_at_collection") or _text(row, "district") or "",
            source_system=SOURCE_SYSTEM,
            reason=_text(row, "sampling_purpose") or "")
        written += 1

        receipt = _text(row, "receipt_datetime")
        condition = _text(row, "condition_on_receipt")
        if receipt or condition:
            rejected = condition == "Rejected"
            record_custody_event(
                cur, dataset_id, "specimen", sample_id,
                "rejected" if rejected else "received", actor=actor,
                event_datetime=receipt, site=_text(row, "lab_name") or "",
                source_system=SOURCE_SYSTEM,
                reason=(_text(row, "rejection_reason") or "") if rejected
                       else (condition or ""))
            written += 1

    for _, row in isolates.iterrows():
        isolate_id = _text(row, "isolate_id")
        if not isolate_id:
            continue
        identified = _date(row, "identification_date")
        record_custody_event(
            cur, dataset_id, "isolate", isolate_id, "identified", actor=actor,
            event_datetime=identified.isoformat() if identified else None,
            source_system=SOURCE_SYSTEM,
            reason=(f"{_text(row, 'organism') or 'organism'} by "
                    f"{_text(row, 'identification_method') or 'unrecorded method'}"))
        written += 1

        tested = phenotype_counts.get(isolate_id, 0)
        if tested:
            record_custody_event(
                cur, dataset_id, "isolate", isolate_id, "ast_performed",
                actor=actor, source_system=SOURCE_SYSTEM,
                reason=f"{tested} antibiotic(s) tested")
            written += 1

    for _, row in genomics.iterrows():
        genomic_id = _text(row, "genomic_id")
        if not genomic_id:
            continue
        run_date = _date(row, "run_date")
        record_custody_event(
            cur, dataset_id, "genomic_result", genomic_id, "sequenced",
            actor=actor,
            event_datetime=run_date.isoformat() if run_date else None,
            source_system=SOURCE_SYSTEM,
            reason=f"run {_text(row, 'run_id') or 'unrecorded'} on "
                   f"{_text(row, 'platform') or 'unrecorded platform'}")
        written += 1

        analysed = _date(row, "analysis_date")
        if analysed or _text(row, "pipeline_name"):
            record_custody_event(
                cur, dataset_id, "genomic_result", genomic_id,
                "sequence_analysed", actor=_text(row, "analysed_by") or actor,
                event_datetime=analysed.isoformat() if analysed else None,
                source_system=SOURCE_SYSTEM,
                reason=(f"{_text(row, 'pipeline_name') or 'pipeline'} "
                        f"{_text(row, 'pipeline_version') or ''}".strip()
                        + f", {_text(row, 'amr_db_name') or 'database'} "
                          f"{_text(row, 'amr_db_version') or 'version unrecorded'}"))
            written += 1

        if _text(row, "review_status") == "Accepted":
            record_custody_event(
                cur, dataset_id, "genomic_result", genomic_id,
                "sequence_reviewed",
                actor=_text(row, "reviewed_by") or actor,
                source_system=SOURCE_SYSTEM, reason="review accepted")
            written += 1

    return written


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def ingest_validated_upload(dataset_id: str, dataset_name: str,
                            validation, uploaded_by: str = "System"
                            ) -> IngestResult:
    """Write a validated workbook into the database in one transaction.

    ``validation`` is a ``src.validate.UploadValidation``. A validation that did
    not pass is refused here rather than partially written: the constraints in
    the schema would reject most of it anyway, and a rejection halfway through a
    chain leaves specimens with no isolates and isolates with no phenotypes.
    """
    if not getattr(validation, "ok", False):
        return IngestResult(False, "The upload did not pass validation, so "
                                   "nothing was written.")

    notes: List[str] = []
    samples, pseudonym_notes = _pseudonymise(validation.samples)
    notes.extend(pseudonym_notes)

    isolates = validation.isolates
    ast = validation.ast
    genomics = validation.genomics

    if validation.isolates_derived and not isolates.empty:
        notes.append(
            f"The workbook carried no isolates sheet, so {len(isolates)} "
            "isolate(s) were derived by grouping susceptibility rows on "
            "specimen and organism. Two colonies of one species from one "
            "specimen cannot be told apart this way, because that distinction "
            "was never recorded.")

    actor = uploaded_by or "System"
    conn = db.get_connection()
    counts: Dict[str, int] = {}

    try:
        cur = conn.cursor()
        raw = cur.raw

        cur.execute("""
            INSERT INTO datasets (dataset_id, dataset_name, uploaded_by,
                                  uploaded_at, rows_samples, rows_tests)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (dataset_id, dataset_name, actor, _dt.datetime.now().isoformat(),
              len(samples), len(ast)))

        subject_rows, sample_to_subject, subject_basis = _build_subjects(
            samples, dataset_id, actor)
        counts["subjects"] = _insert_many(
            raw, _insert_sql("subjects", _SUBJECT_COLUMNS), subject_rows)

        encounter_rows, sample_to_encounter, _ = _build_encounters(
            samples, dataset_id, actor, sample_to_subject)
        counts["encounters"] = _insert_many(
            raw, _insert_sql("encounters", _ENCOUNTER_COLUMNS), encounter_rows)

        specimen_rows = _build_specimens(samples, dataset_id, actor,
                                        sample_to_subject, sample_to_encounter)
        counts["specimens"] = _insert_many(
            raw, _insert_sql("specimens", _SPECIMEN_COLUMNS), specimen_rows)

        known_specimens = {r[1] for r in specimen_rows}
        isolate_rows = _build_isolates(isolates, dataset_id, actor,
                                       known_specimens)
        counts["isolates"] = _insert_many(
            raw, _insert_sql("isolates", _ISOLATE_COLUMNS), isolate_rows)

        known_isolates = {r[1] for r in isolate_rows}
        phenotype_rows = _build_phenotypes(ast, dataset_id, actor,
                                           known_isolates)
        counts["phenotypes"] = _insert_many(
            raw, _insert_sql("phenotypes", _PHENOTYPE_COLUMNS), phenotype_rows)

        run_rows = _build_sequencing_runs(genomics, dataset_id, actor) if not genomics.empty else []
        counts["sequencing_runs"] = _insert_many(
            raw,
            _insert_sql("sequencing_runs",
                        ("dataset_id", "run_id", "platform", "instrument",
                         "library_kit", "read_type", "run_date", "lab_name",
                         "operator", "created_by")),
            run_rows)

        genomic_rows = _build_genomics(genomics, dataset_id, actor,
                                       known_isolates) if not genomics.empty else []
        counts["genomic_results"] = _insert_many(
            raw, _insert_sql("genomic_results", _GENOMIC_COLUMNS), genomic_rows)

        # Legacy wide tables, so the existing analytics and report pages keep
        # working while they are migrated onto the chain above.
        counts["legacy_samples"] = _insert_many(
            raw, _insert_sql("samples", _LEGACY_SAMPLE_COLUMNS),
            _build_legacy_samples(samples, dataset_id))
        counts["legacy_ast_results"] = _insert_many(
            raw, _insert_sql("ast_results", _LEGACY_AST_COLUMNS),
            _build_legacy_ast(ast, dataset_id))

        phenotype_counts: Dict[str, int] = {}
        for row in phenotype_rows:
            phenotype_counts[row[1]] = phenotype_counts.get(row[1], 0) + 1

        counts["custody_events"] = _log_custody(
            cur, dataset_id, actor, samples, isolates, genomics,
            sample_to_subject, subject_basis, phenotype_counts)

        conn.commit()

        # Refresh planner statistics for the tables just written.
        #
        # After a bulk insert PostgreSQL has no statistics for the new rows, so
        # it can pick a plan suited to an empty table. On a 2,500-specimen
        # upload the first query joining the chain hit the 30-second statement
        # timeout; the same query took well under a second once analysed. Doing
        # it here means the first page load after an upload is fast rather than
        # a failure the user has to retry.
        #
        # Outside the transaction, and failure is not fatal: stale statistics
        # make queries slow, not wrong.
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            cur.raw.connection.set_isolation_level(0)  # autocommit for ANALYZE
            for table in ("subjects", "encounters", "specimens", "isolates",
                          "phenotypes", "genomic_results", "custody_events",
                          "samples", "ast_results"):
                cur.execute(f"ANALYZE {table}")
        except Exception:                             # noqa: BLE001
            logger.warning("could not refresh planner statistics after ingest",
                           exc_info=True)
    except Exception as exc:                          # noqa: BLE001
        conn.rollback()
        logger.exception("ingest_validated_upload failed")
        return IngestResult(False, f"Nothing was written. Database error: {exc}")
    finally:
        conn.close()

    dropped = _report_dropped(validation, counts)
    notes.extend(dropped)

    return IngestResult(
        True,
        (f"Stored {counts.get('specimens', 0)} specimen(s), "
         f"{counts.get('isolates', 0)} isolate(s) and "
         f"{counts.get('phenotypes', 0)} susceptibility result(s)."),
        counts=counts, notes=notes)


def _report_dropped(validation, counts: Dict[str, int]) -> List[str]:
    """Say plainly when fewer rows were stored than the workbook held."""
    notes: List[str] = []
    pairs = (
        ("specimens", len(validation.samples), "specimen row(s)"),
        ("isolates", len(validation.isolates), "isolate row(s)"),
        ("phenotypes", len(validation.ast), "susceptibility row(s)"),
        ("genomic_results", len(validation.genomics), "genomic row(s)"),
    )
    for key, supplied, label in pairs:
        stored = counts.get(key, 0)
        if supplied and stored < supplied:
            notes.append(
                f"{supplied - stored} of {supplied} {label} were not stored "
                "because they referenced a parent row that was itself not "
                "stored.")
    return notes


__all__ = ["IngestResult", "ingest_validated_upload"]
