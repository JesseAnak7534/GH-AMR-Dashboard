"""
Traceability model for the ICBB-AMRSS surveillance platform.

The original schema stored a wide `samples` row and a wide `ast_results` row.
It could show that a susceptibility result came from a recorded sample, but it
could not follow a result back to a patient, a ward, a specimen or a genome,
and it had no isolate entity at all -- `isolate_id` was being issued per test,
so a single culture tested against six drugs was stored as six isolates.

This module defines the entity chain the platform actually needs:

    subject  ->  encounter  ->  specimen  ->  isolate  ->  phenotype (AST)
                                                      \\-> genomic result

with an append-only custody log beside it recording every handoff.

Design notes
------------
* Every table carries `dataset_id`. That is the platform's tenancy and merge
  unit (see db.merge_dataset_into_main / db.delete_dataset), so new entities
  must carry it or merges and deletes would silently orphan rows.

* `subjects` uses a single table with a `sector` discriminator rather than one
  table per sector. Four sector tables would force a four-way outer join on
  every query in a pandas-based analytics layer. Sectors are kept analytically
  distinct in the *query* layer instead -- see `assert_single_sector`.

* Human subjects are stored under a salted, facility-scoped pseudonym. The
  platform never receives or stores the hospital's own patient number, so a
  leak of this database cannot re-identify a patient without the facility's
  salt, which stays at the facility.

* Genomic results store a path and checksum for reads and assemblies, never
  the files themselves.

* PostgreSQL only. The schema enforces its own integrity rather than trusting
  the application: composite foreign keys with ON DELETE CASCADE keep the chain
  whole and make dataset deletion automatic, CHECK constraints pin the
  controlled vocabularies at the storage layer, timestamps are TIMESTAMPTZ and
  gene/replicon lists are JSONB.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Controlled vocabularies
#
# These are the values the platform will accept. Anything outside them is a
# validation error at upload, not a silently stored free-text variant. Free
# text is still available in the paired `*_detail` / `ward` columns so local
# naming is not lost.
# ---------------------------------------------------------------------------

SECTORS: Tuple[str, ...] = (
    "human",
    "animal",
    "food",
    "environment",
    "aquaculture",
)

# Aligned with the ECDC point-prevalence ward categories, so the same taxonomy
# serves both routine surveillance and a PPS.
WARD_TYPES: Tuple[str, ...] = (
    "ICU",
    "Medical",
    "Surgical",
    "Paediatric",
    "Neonatal",
    "Obstetric/Gynaecology",
    "Emergency",
    "Oncology/Haematology",
    "Burns",
    "Outpatient",
    "Other",
    "Unknown",
)

# Ward types where an infection is plausibly device- or procedure-associated.
# Used by HAI views; kept here so the definition lives with the vocabulary.
HIGH_ACUITY_WARD_TYPES: Tuple[str, ...] = (
    "ICU",
    "Neonatal",
    "Surgical",
    "Burns",
    "Oncology/Haematology",
)

SPECIMEN_TYPES: Tuple[str, ...] = (
    "Blood",
    "Urine",
    "Wound/Pus",
    "Respiratory",
    "Stool",
    "CSF",
    "Sterile fluid",
    "Device tip",
    "Other",
    "Unknown",
)

# Specimens from a normally sterile site. A positive culture here carries very
# different weight from a swab, and deduplication and significance rules need
# to know the difference.
STERILE_SITE_SPECIMENS: Tuple[str, ...] = (
    "Blood",
    "CSF",
    "Sterile fluid",
)

PATIENT_TYPES: Tuple[str, ...] = (
    "Inpatient",
    "Outpatient",
    "Emergency",
    "Day-case",
    "Unknown",
)

SEX_VALUES: Tuple[str, ...] = ("F", "M", "Other", "Unknown")

AGE_BANDS: Tuple[str, ...] = (
    "<1", "1-4", "5-14", "15-24", "25-44", "45-64", "65+", "Unknown",
)

IDENTIFICATION_METHODS: Tuple[str, ...] = (
    "MALDI-TOF",
    "Automated biochemical",
    "Manual biochemical",
    "Molecular",
    "Chromogenic agar",
    "Other",
    "Unknown",
)

SAMPLING_PURPOSES: Tuple[str, ...] = (
    "Routine diagnostic",
    "Surveillance",
    "Outbreak investigation",
    "Screening",
    "Research",
    "Unknown",
)

SPECIMEN_CONDITIONS: Tuple[str, ...] = (
    "Acceptable",
    "Suboptimal",
    "Rejected",
    "Unknown",
)

# The handoffs worth recording. Anything that changes a result, or moves
# custody of material, leaves one of these behind.
CUSTODY_EVENT_TYPES: Tuple[str, ...] = (
    "collected",
    "transported",
    "received",
    "rejected",
    "cultured",
    "identified",
    "ast_performed",
    "ast_verified",
    "sequenced",
    "sequence_analysed",
    "sequence_reviewed",
    "reported",
    "corrected",
    "approved",
    "notified",
    "transferred",
)

ENTITY_TYPES: Tuple[str, ...] = (
    "subject",
    "encounter",
    "specimen",
    "isolate",
    "phenotype",
    "genomic_result",
)

QC_STATUSES: Tuple[str, ...] = ("Pass", "Fail", "Not done", "Unknown")

RESULT_SOURCES: Tuple[str, ...] = (
    "Measured",          # read off the plate / instrument
    "Rule-interpreted",  # derived by the interpretation engine
    "Manually verified", # a human confirmed it
    "Imported",          # came in already interpreted, provenance unknown
)

REVIEW_STATUSES: Tuple[str, ...] = (
    "Unreviewed",
    "In review",
    "Accepted",
    "Rejected",
)


# ---------------------------------------------------------------------------
# Pseudonymisation
# ---------------------------------------------------------------------------

_SALT_ENV = "AMRSS_PATIENT_SALT"


def _facility_salt(facility_code: str) -> str:
    """Return the salt for a facility.

    The salt is read from the environment (or Streamlit secrets, if present)
    so it is never committed. A facility-specific salt is preferred; a
    platform-wide salt is the fallback.

    A missing salt is a hard error. Hashing an unsalted patient number is
    reversible by brute force over a hospital's number range, which would be
    worse than storing nothing.
    """
    key = f"{_SALT_ENV}_{facility_code.upper().replace('-', '_').replace(' ', '_')}"
    salt = os.environ.get(key) or os.environ.get(_SALT_ENV)

    if not salt:
        try:  # Streamlit secrets, when running inside the app
            import streamlit as st  # noqa: WPS433 (local import is deliberate)
            secrets = getattr(st, "secrets", None)
            if secrets is not None:
                salt = secrets.get(key) or secrets.get(_SALT_ENV)
        except Exception:
            salt = None

    if not salt:
        raise RuntimeError(
            f"No patient pseudonymisation salt configured. Set {_SALT_ENV} "
            f"(or {key}) in the environment or Streamlit secrets before "
            "ingesting human specimens."
        )
    return str(salt)


def make_patient_pseudonym(facility_code: str, local_patient_id: str) -> str:
    """Derive the stable, facility-scoped pseudonym for a patient.

    The same patient at the same facility always yields the same pseudonym, so
    repeat specimens link up and first-isolate-per-patient deduplication (CLSI
    M39) becomes possible. The same patient number at a *different* facility
    yields a different pseudonym, so identifiers cannot be cross-matched
    between hospitals without an explicit, governed linkage step.

    The caller must discard `local_patient_id` after this returns. It is never
    persisted by the platform.
    """
    if not facility_code or not str(facility_code).strip():
        raise ValueError("facility_code is required to build a patient pseudonym")
    if not local_patient_id or not str(local_patient_id).strip():
        raise ValueError("local_patient_id is required to build a patient pseudonym")

    facility = str(facility_code).strip().upper()
    local = str(local_patient_id).strip().upper()
    salt = _facility_salt(facility)

    digest = hashlib.sha256(f"{facility}|{local}|{salt}".encode("utf-8")).hexdigest()
    return f"{facility}-{digest[:16]}"


def age_to_band(age_years: Optional[float]) -> str:
    """Map an age in years to the reporting band."""
    if age_years is None:
        return "Unknown"
    try:
        age = float(age_years)
    except (TypeError, ValueError):
        return "Unknown"
    if age < 0:
        return "Unknown"
    if age < 1:
        return "<1"
    if age < 5:
        return "1-4"
    if age < 15:
        return "5-14"
    if age < 25:
        return "15-24"
    if age < 45:
        return "25-44"
    if age < 65:
        return "45-64"
    return "65+"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_vocabulary(value: Optional[str], allowed: Iterable[str],
                        field: str, *, required: bool = False) -> List[str]:
    """Return a list of error strings (empty when the value is acceptable)."""
    allowed = tuple(allowed)
    if value is None or str(value).strip() == "":
        if required:
            return [f"{field} is required (one of: {', '.join(allowed)})"]
        return []
    if str(value).strip() not in allowed:
        return [
            f"{field} '{value}' is not a recognised value. "
            f"Expected one of: {', '.join(allowed)}"
        ]
    return []


def assert_single_sector(sectors: Iterable[str]) -> None:
    """Guard against silently pooling sectors into one rate.

    A human clinical culture, a farm sampling round and a wastewater grab are
    not interchangeable observations. Combining them is legitimate only for a
    defined question, over a defined window and geography -- and then it should
    be an explicit, documented step, not a side effect of a groupby.
    """
    distinct = {str(s).strip().lower() for s in sectors if str(s).strip()}
    if len(distinct) > 1:
        raise ValueError(
            "Refusing to pool observations across sectors "
            f"({', '.join(sorted(distinct))}). Filter to one sector, or use an "
            "explicitly documented cross-sector comparison."
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _sql_list(values: Iterable[str]) -> str:
    """Render a vocabulary as a SQL IN-list for a CHECK constraint."""
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def _add_constraint(cur, table: str, name: str, definition: str) -> None:
    """Add a named constraint when the database does not already have it.

    PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, and a plain ADD would fail
    on the second startup. Checking pg_constraint keeps schema creation
    idempotent, which is what lets init_database() run on every boot.
    """
    cur.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = %s "
        "AND conrelid = %s::regclass",
        (name, table),
    )
    if cur.fetchone() is None:
        cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition}")


def init_traceability_schema(cur) -> None:
    """Create the traceability tables. Safe to call on every startup.

    Called from db.init_database() with an open cursor, before commit.

    Integrity is enforced by the database, not by hope: every child row has a
    composite foreign key back to its parent with ON DELETE CASCADE, so the
    chain cannot be broken and deleting a dataset removes its whole tree in one
    statement. Controlled vocabularies are CHECK constraints, so an unexpected
    ward type is rejected at write time rather than discovered later in a
    groupby.
    """

    # -- subjects ----------------------------------------------------------
    # The thing that was sampled. One row per patient (per facility), animal
    # unit, food source or environmental point.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS subjects (
            dataset_id TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            sector TEXT NOT NULL
                CHECK (sector IN ({_sql_list(SECTORS)})),

            -- human
            patient_pseudonym TEXT,
            facility_code TEXT,
            sex TEXT CHECK (sex IS NULL OR sex IN ({_sql_list(SEX_VALUES)})),
            age_years DOUBLE PRECISION
                CHECK (age_years IS NULL OR (age_years >= 0 AND age_years <= 130)),
            age_band TEXT
                CHECK (age_band IS NULL OR age_band IN ({_sql_list(AGE_BANDS)})),

            -- animal / aquaculture
            animal_species TEXT,
            production_type TEXT,
            herd_flock_id TEXT,

            -- food
            food_commodity TEXT,
            food_stage TEXT,

            -- environment
            water_body TEXT,
            catchment TEXT,
            treatment_stage TEXT,
            sampling_point TEXT,

            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, subject_id),

            -- a human subject is meaningless without its pseudonym and the
            -- facility that scopes it
            CONSTRAINT subjects_human_needs_pseudonym CHECK (
                sector <> 'human'
                OR (patient_pseudonym IS NOT NULL AND facility_code IS NOT NULL)
            )
        )
    """)

    # -- encounters --------------------------------------------------------
    # A care episode. Ward and ward type live here, and they are what make a
    # result clinically interpretable.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS encounters (
            dataset_id TEXT NOT NULL,
            encounter_id TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            facility_code TEXT,
            facility_name TEXT,
            ward TEXT,
            ward_type TEXT
                CHECK (ward_type IS NULL OR ward_type IN ({_sql_list(WARD_TYPES)})),
            patient_type TEXT
                CHECK (patient_type IS NULL OR patient_type IN ({_sql_list(PATIENT_TYPES)})),
            admission_date DATE,
            discharge_date DATE,
            admission_source TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, encounter_id),
            CONSTRAINT encounters_subject_fk
                FOREIGN KEY (dataset_id, subject_id)
                REFERENCES subjects (dataset_id, subject_id) ON DELETE CASCADE,
            CONSTRAINT encounters_dates_ordered CHECK (
                discharge_date IS NULL OR admission_date IS NULL
                OR discharge_date >= admission_date
            )
        )
    """)

    # -- specimens ---------------------------------------------------------
    # The material received by the laboratory. `ward_at_collection` is held
    # separately from the encounter ward on purpose: a patient admitted to a
    # medical ward may have a specimen drawn in ICU, and for healthcare-
    # associated attribution it is the collection ward that matters.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS specimens (
            dataset_id TEXT NOT NULL,
            specimen_id TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            encounter_id TEXT,
            accession_number TEXT,
            specimen_type TEXT
                CHECK (specimen_type IS NULL OR specimen_type IN ({_sql_list(SPECIMEN_TYPES)})),
            specimen_detail TEXT,
            collection_datetime TIMESTAMPTZ,
            collected_by TEXT,
            ward_at_collection TEXT,
            ward_type_at_collection TEXT
                CHECK (ward_type_at_collection IS NULL
                       OR ward_type_at_collection IN ({_sql_list(WARD_TYPES)})),
            -- Age is held here as well as on the subject, and this is the copy
            -- that reporting uses. A patient readmitted two years later is the
            -- same subject at a different age, so an age stored only against
            -- the subject puts every later specimen in the wrong band.
            age_years_at_collection DOUBLE PRECISION
                CHECK (age_years_at_collection IS NULL
                       OR (age_years_at_collection >= 0
                           AND age_years_at_collection <= 130)),
            age_band_at_collection TEXT
                CHECK (age_band_at_collection IS NULL
                       OR age_band_at_collection IN ({_sql_list(AGE_BANDS)})),
            receipt_datetime TIMESTAMPTZ,
            condition_on_receipt TEXT
                CHECK (condition_on_receipt IS NULL
                       OR condition_on_receipt IN ({_sql_list(SPECIMEN_CONDITIONS)})),
            rejection_reason TEXT,
            sampling_purpose TEXT
                CHECK (sampling_purpose IS NULL
                       OR sampling_purpose IN ({_sql_list(SAMPLING_PURPOSES)})),
            lab_name TEXT,
            region TEXT,
            district TEXT,
            latitude DOUBLE PRECISION
                CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90)),
            longitude DOUBLE PRECISION
                CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180)),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, specimen_id),
            CONSTRAINT specimens_subject_fk
                FOREIGN KEY (dataset_id, subject_id)
                REFERENCES subjects (dataset_id, subject_id) ON DELETE CASCADE,
            CONSTRAINT specimens_encounter_fk
                FOREIGN KEY (dataset_id, encounter_id)
                REFERENCES encounters (dataset_id, encounter_id) ON DELETE SET NULL,
            CONSTRAINT specimens_received_after_collection CHECK (
                receipt_datetime IS NULL OR collection_datetime IS NULL
                OR receipt_datetime >= collection_datetime
            ),
            CONSTRAINT specimens_rejection_has_reason CHECK (
                condition_on_receipt IS DISTINCT FROM 'Rejected'
                OR rejection_reason IS NOT NULL
            )
        )
    """)

    # -- isolates ----------------------------------------------------------
    # The entity that was missing. One row per organism recovered from one
    # specimen. A culture tested against twelve drugs is ONE isolate with
    # twelve phenotype rows.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS isolates (
            dataset_id TEXT NOT NULL,
            isolate_id TEXT NOT NULL,
            specimen_id TEXT NOT NULL,
            isolate_number SMALLINT NOT NULL DEFAULT 1
                CHECK (isolate_number >= 1),
            organism TEXT,
            organism_code TEXT,
            identification_method TEXT
                CHECK (identification_method IS NULL
                       OR identification_method IN ({_sql_list(IDENTIFICATION_METHODS)})),
            identification_date DATE,
            is_significant BOOLEAN,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, isolate_id),
            CONSTRAINT isolates_specimen_fk
                FOREIGN KEY (dataset_id, specimen_id)
                REFERENCES specimens (dataset_id, specimen_id) ON DELETE CASCADE,
            -- two isolates from one specimen cannot share a sequence number
            CONSTRAINT isolates_specimen_number_unique
                UNIQUE (dataset_id, specimen_id, isolate_number)
        )
    """)

    # -- phenotypes --------------------------------------------------------
    # One susceptibility observation: one isolate, one antibiotic. Carries the
    # breakpoint standard AND its version, because an S/I/R with no version is
    # not reproducible, and records whether the value was measured, derived by
    # rule or imported already interpreted.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS phenotypes (
            dataset_id TEXT NOT NULL,
            isolate_id TEXT NOT NULL,
            antibiotic TEXT NOT NULL,
            antibiotic_code TEXT,
            result TEXT CHECK (result IS NULL OR result IN ('S', 'I', 'R', 'NS')),
            mic_value DOUBLE PRECISION CHECK (mic_value IS NULL OR mic_value > 0),
            mic_operator TEXT
                CHECK (mic_operator IS NULL OR mic_operator IN ('=', '<', '<=', '>', '>=')),
            zone_diameter DOUBLE PRECISION
                CHECK (zone_diameter IS NULL OR (zone_diameter BETWEEN 0 AND 100)),
            ast_method TEXT,
            ast_instrument TEXT,
            breakpoint_standard TEXT,
            breakpoint_version TEXT,
            result_source TEXT
                CHECK (result_source IS NULL OR result_source IN ({_sql_list(RESULT_SOURCES)})),
            qc_status TEXT
                CHECK (qc_status IS NULL OR qc_status IN ({_sql_list(QC_STATUSES)})),
            qc_strain TEXT,
            test_date DATE,
            verified_by TEXT,
            verified_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, isolate_id, antibiotic),
            CONSTRAINT phenotypes_isolate_fk
                FOREIGN KEY (dataset_id, isolate_id)
                REFERENCES isolates (dataset_id, isolate_id) ON DELETE CASCADE,
            -- an interpreted S/I/R with no standard behind it is not reproducible
            CONSTRAINT phenotypes_interpretation_has_standard CHECK (
                result IS NULL
                OR (breakpoint_standard IS NOT NULL AND breakpoint_version IS NOT NULL)
            )
        )
    """)

    # -- sequencing --------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sequencing_runs (
            dataset_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            platform TEXT,
            instrument TEXT,
            library_kit TEXT,
            read_type TEXT,
            run_date DATE,
            lab_name TEXT,
            operator TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, run_id)
        )
    """)

    # Large files stay in governed object storage. This table holds the
    # pointer, the checksum and the provenance needed to reproduce a call.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS genomic_results (
            dataset_id TEXT NOT NULL,
            genomic_id TEXT NOT NULL,
            isolate_id TEXT NOT NULL,
            run_id TEXT,
            library_id TEXT,

            read_path TEXT,
            read_checksum TEXT,
            assembly_path TEXT,
            assembly_checksum TEXT,

            total_reads DOUBLE PRECISION CHECK (total_reads IS NULL OR total_reads >= 0),
            mean_depth DOUBLE PRECISION CHECK (mean_depth IS NULL OR mean_depth >= 0),
            coverage_breadth DOUBLE PRECISION
                CHECK (coverage_breadth IS NULL OR (coverage_breadth BETWEEN 0 AND 100)),
            contamination_pct DOUBLE PRECISION
                CHECK (contamination_pct IS NULL OR (contamination_pct BETWEEN 0 AND 100)),
            n50 DOUBLE PRECISION CHECK (n50 IS NULL OR n50 >= 0),
            contig_count INTEGER CHECK (contig_count IS NULL OR contig_count >= 0),
            qc_status TEXT
                CHECK (qc_status IS NULL OR qc_status IN ({_sql_list(QC_STATUSES)})),

            assembler TEXT,
            assembler_version TEXT,
            pipeline_name TEXT,
            pipeline_version TEXT,
            amr_db_name TEXT,
            amr_db_version TEXT,

            species_confirmed TEXT,
            mlst_scheme TEXT,
            sequence_type TEXT,
            amr_genes JSONB,
            amr_mutations JSONB,
            plasmid_replicons JSONB,
            virulence_genes JSONB,
            cluster_method TEXT,
            cluster_id TEXT,

            analysis_date DATE,
            analysed_by TEXT,
            review_status TEXT
                CHECK (review_status IS NULL OR review_status IN ({_sql_list(REVIEW_STATUSES)})),
            reviewed_by TEXT,
            reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by TEXT,
            PRIMARY KEY (dataset_id, genomic_id),
            CONSTRAINT genomic_isolate_fk
                FOREIGN KEY (dataset_id, isolate_id)
                REFERENCES isolates (dataset_id, isolate_id) ON DELETE CASCADE,
            CONSTRAINT genomic_run_fk
                FOREIGN KEY (dataset_id, run_id)
                REFERENCES sequencing_runs (dataset_id, run_id) ON DELETE SET NULL,
            -- a read pointer without a checksum cannot be verified later
            CONSTRAINT genomic_reads_have_checksum CHECK (
                read_path IS NULL OR read_checksum IS NOT NULL
            ),
            CONSTRAINT genomic_reviewed_has_reviewer CHECK (
                review_status IS DISTINCT FROM 'Accepted'
                OR reviewed_by IS NOT NULL
            )
        )
    """)

    # -- custody log -------------------------------------------------------
    # Append-only. There is deliberately no update or delete helper in this
    # module: a correction is a new 'corrected' event carrying the old and new
    # value, so the history of a result can always be replayed.
    #
    # No foreign key here on purpose. The log must survive its subject: if a
    # record is later deleted, the evidence that it existed and who touched it
    # must remain. dataset_id is cleaned up explicitly in db.delete_dataset.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS custody_events (
            event_id BIGSERIAL PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            entity_type TEXT NOT NULL
                CHECK (entity_type IN ({_sql_list(ENTITY_TYPES)})),
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL
                CHECK (event_type IN ({_sql_list(CUSTODY_EVENT_TYPES)})),
            event_datetime TIMESTAMPTZ,
            actor TEXT,
            actor_role TEXT,
            site TEXT,
            source_system TEXT,
            reason TEXT,
            field_changed TEXT,
            old_value TEXT,
            new_value TEXT,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # -- in-place upgrades --------------------------------------------------
    # CREATE TABLE IF NOT EXISTS does nothing to a table that already exists,
    # so columns added after a database was first built need stating
    # separately. Each statement is idempotent, so this stays safe to run on
    # every startup.
    for stmt in (
        "ALTER TABLE specimens ADD COLUMN IF NOT EXISTS "
        "age_years_at_collection DOUBLE PRECISION",
        "ALTER TABLE specimens ADD COLUMN IF NOT EXISTS "
        "age_band_at_collection TEXT",
    ):
        cur.execute(stmt)

    # ADD COLUMN carries no CHECK with it, and PostgreSQL has no
    # ADD CONSTRAINT IF NOT EXISTS, so each one is added only when absent.
    # Without this an upgraded database would accept an age of 900 while a
    # freshly created one rejected it.
    _add_constraint(cur, "specimens", "specimens_age_at_collection_range",
                    "CHECK (age_years_at_collection IS NULL "
                    "OR (age_years_at_collection >= 0 "
                    "AND age_years_at_collection <= 130))")
    _add_constraint(cur, "specimens", "specimens_age_band_at_collection_valid",
                    f"CHECK (age_band_at_collection IS NULL "
                    f"OR age_band_at_collection IN ({_sql_list(AGE_BANDS)}))")

    # -- indexes -----------------------------------------------------------
    # The joins this model exists to make fast: walking the chain in either
    # direction, slicing by ward type or specimen type, and pulling an
    # entity's history. Foreign keys already index the parent side; these
    # cover the lookups the analytics layer performs.
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_subjects_pseudonym "
        "ON subjects (dataset_id, patient_pseudonym)",
        "CREATE INDEX IF NOT EXISTS idx_subjects_sector "
        "ON subjects (dataset_id, sector)",
        "CREATE INDEX IF NOT EXISTS idx_encounters_subject "
        "ON encounters (dataset_id, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_encounters_ward_type "
        "ON encounters (dataset_id, ward_type)",
        "CREATE INDEX IF NOT EXISTS idx_specimens_subject "
        "ON specimens (dataset_id, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_specimens_encounter "
        "ON specimens (dataset_id, encounter_id)",
        "CREATE INDEX IF NOT EXISTS idx_specimens_type "
        "ON specimens (dataset_id, specimen_type)",
        "CREATE INDEX IF NOT EXISTS idx_specimens_ward_type "
        "ON specimens (dataset_id, ward_type_at_collection)",
        "CREATE INDEX IF NOT EXISTS idx_specimens_age_band "
        "ON specimens (dataset_id, age_band_at_collection)",
        "CREATE INDEX IF NOT EXISTS idx_specimens_collected "
        "ON specimens (dataset_id, collection_datetime)",
        "CREATE INDEX IF NOT EXISTS idx_isolates_specimen "
        "ON isolates (dataset_id, specimen_id)",
        "CREATE INDEX IF NOT EXISTS idx_isolates_organism "
        "ON isolates (dataset_id, organism)",
        "CREATE INDEX IF NOT EXISTS idx_phenotypes_isolate "
        "ON phenotypes (dataset_id, isolate_id)",
        "CREATE INDEX IF NOT EXISTS idx_phenotypes_antibiotic "
        "ON phenotypes (dataset_id, antibiotic)",
        "CREATE INDEX IF NOT EXISTS idx_genomic_isolate "
        "ON genomic_results (dataset_id, isolate_id)",
        "CREATE INDEX IF NOT EXISTS idx_custody_entity "
        "ON custody_events (dataset_id, entity_type, entity_id)",
    ):
        cur.execute(stmt)


# ---------------------------------------------------------------------------
# Custody log
# ---------------------------------------------------------------------------

def record_custody_event(cur, dataset_id: str, entity_type: str, entity_id: str,
                         event_type: str, *, actor: str = "",
                         actor_role: str = "", site: str = "",
                         event_datetime: Optional[str] = None,
                         source_system: str = "", reason: str = "",
                         field_changed: str = "", old_value: str = "",
                         new_value: str = "") -> None:
    """Append one event to the custody log.

    Takes an open cursor so a caller can write the entity and its event in the
    same transaction -- a handoff that is not recorded atomically with the
    change it describes is not an audit trail.
    """
    errs = (validate_vocabulary(entity_type, ENTITY_TYPES, "entity_type", required=True)
            + validate_vocabulary(event_type, CUSTODY_EVENT_TYPES, "event_type", required=True))
    if errs:
        raise ValueError("; ".join(errs))

    # recorded_at is set by the database default, so the audit timestamp comes
    # from the server clock rather than whichever machine happened to call in.
    cur.execute("""
        INSERT INTO custody_events
        (dataset_id, entity_type, entity_id, event_type, event_datetime,
         actor, actor_role, site, source_system, reason,
         field_changed, old_value, new_value)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        dataset_id, entity_type, entity_id, event_type,
        event_datetime or _utcnow(), actor, actor_role, site,
        source_system, reason, field_changed,
        str(old_value) if old_value is not None else None,
        str(new_value) if new_value is not None else None,
    ))


__all__ = [
    "SECTORS", "WARD_TYPES", "HIGH_ACUITY_WARD_TYPES", "SPECIMEN_TYPES",
    "STERILE_SITE_SPECIMENS", "PATIENT_TYPES", "SEX_VALUES", "AGE_BANDS",
    "IDENTIFICATION_METHODS", "SAMPLING_PURPOSES", "SPECIMEN_CONDITIONS",
    "CUSTODY_EVENT_TYPES", "ENTITY_TYPES", "QC_STATUSES", "RESULT_SOURCES",
    "REVIEW_STATUSES",
    "make_patient_pseudonym", "age_to_band",
    "validate_vocabulary", "assert_single_sector",
    "init_traceability_schema", "record_custody_event",
]
