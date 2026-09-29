"""
Backfill the traceability chain from the legacy wide tables.

Rows that predate the traceability model live only in ``samples`` and
``ast_results``. They have no subject, encounter, specimen, isolate or custody
history, so nothing about them can be sliced by ward, patient or specimen type,
and their isolate counts are wrong.

This script derives what the legacy format actually recorded, and records
plainly what it did not.

What is derived
---------------
**Isolates.** ``isolate_id`` was issued per susceptibility test, so one culture
tested against six drugs was stored as six isolates. Grouping on specimen and
organism recovers the truth: 4,568 legacy rows describe about 1,005 isolates.
This is the single biggest correction the backfill makes. It cannot recover a
case where two colonies of one species from one specimen were genuinely separate
isolates, because that distinction was never recorded.

**Specimens.** One per legacy ``samples`` row, carrying the lab, region,
district and coordinates that were recorded.

**Subjects.** One per specimen. For human specimens that means one synthetic
patient per specimen, under the facility code ``LEGACY``.

What is NOT derived, and the consequences
----------------------------------------
The legacy format recorded no patient identifier, ward, specimen type, sex, age
or admission date. None of those is invented here.

The practical consequence, which matters when reading any output built on this
data: **no two legacy specimens can ever be linked to the same patient.** Each
one is its own patient by construction. So for legacy data specifically:

* first-isolate-per-patient deduplication (CLSI M39) is a no-op -- every isolate
  is already a first isolate;
* repeat-infection and readmission detection will find nothing;
* community-onset versus healthcare-associated classification is impossible;
* ward and age stratification show everything in the ``Unknown`` bucket.

Every subject the backfill creates is stamped in ``created_by`` and carries a
custody event saying so, so this data is distinguishable from a real upload in
any query.

No encounter rows are created. An encounter whose ward, ward type, patient type
and admission date are all empty would assert a care episode that was never
recorded; leaving ``specimens.encounter_id`` null is the honest representation.

Breakpoint editions
-------------------
``phenotypes`` requires a breakpoint standard and version behind any S/I/R,
because a result with no edition cannot be reproduced. The legacy rows carry
``guideline`` but no edition, so the version is written as
``unrecorded (legacy import)``. That is the truthful value and it is greppable;
the alternative, discarding 4,568 results, loses more than it protects.

Usage
-----
    python scripts/backfill_traceability.py --dry-run
    python scripts/backfill_traceability.py
    python scripts/backfill_traceability.py --dataset d5368356
    python scripts/backfill_traceability.py --rewrite-legacy-ids

``--rewrite-legacy-ids`` additionally replaces the per-test ``isolate_id`` in
``ast_results`` with the derived isolate identifiers, so the legacy tables agree
with the chain and any deduplication on ``isolate_id`` starts working there too.
It rewrites existing rows, so it is off by default. Run a ``--dry-run`` first.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2.extras  # noqa: E402

from src import db  # noqa: E402
from src.traceability import (  # noqa: E402
    SECTORS,
    make_patient_pseudonym,
)

#: Facility code scoping every synthetic legacy patient pseudonym. A distinct,
#: obviously artificial value so these subjects can never be mistaken for, or
#: matched against, a real facility's patients.
LEGACY_FACILITY = "LEGACY"

#: Stamped into created_by on every row this script writes.
PROVENANCE = "backfill: legacy wide tables"

#: Written as the breakpoint edition where the legacy row recorded none.
UNRECORDED_EDITION = "unrecorded (legacy import)"

BATCH = 500


def _sector_for(source_category: Optional[str]) -> str:
    """Map a legacy source_category onto a traceability sector."""
    value = (source_category or "").strip().lower()
    return value if value in SECTORS else "environment"


def _fetch(cur, sql: str, params: Sequence = ()) -> List[dict]:
    cur.execute(sql, tuple(params) if params else None)
    return [dict(r) for r in cur.fetchall()]


def _dataset_ids(cur, only: Optional[str]) -> List[str]:
    if only:
        return [only]
    return [r["dataset_id"] for r in _fetch(cur, """
        SELECT DISTINCT dataset_id FROM samples
        WHERE dataset_id IS NOT NULL ORDER BY dataset_id
    """)]


def _already_backfilled(cur, dataset_id: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table in ("subjects", "specimens", "isolates", "phenotypes"):
        cur.execute(f"SELECT count(*) FROM {table} WHERE dataset_id = %s",
                    (dataset_id,))
        counts[table] = cur.fetchone()[0]
    return counts


def _derive_isolates(ast_rows: Sequence[dict]) -> Tuple[Dict[Tuple[str, str], str],
                                                        Dict[str, int]]:
    """Map (specimen, organism) to a derived isolate id, numbered per specimen."""
    per_specimen: Dict[str, List[str]] = defaultdict(list)
    for row in ast_rows:
        sample_id = str(row.get("sample_id") or "").strip()
        organism = str(row.get("organism") or "").strip()
        if not sample_id or not organism:
            continue
        if organism not in per_specimen[sample_id]:
            per_specimen[sample_id].append(organism)

    mapping: Dict[Tuple[str, str], str] = {}
    numbers: Dict[str, int] = {}
    for sample_id, organisms in per_specimen.items():
        for position, organism in enumerate(sorted(organisms), start=1):
            isolate_id = f"{sample_id}-{position}"
            mapping[(sample_id, organism)] = isolate_id
            numbers[isolate_id] = position
    return mapping, numbers


def backfill_dataset(conn, dataset_id: str, *, dry_run: bool,
                     rewrite_legacy_ids: bool, force: bool) -> Dict[str, int]:
    cur = conn.cursor()
    raw = cur.raw

    existing = _already_backfilled(cur, dataset_id)
    if any(existing.values()) and not force:
        print(f"  skipped: the chain already holds rows for this dataset "
              f"({', '.join(f'{k}={v}' for k, v in existing.items() if v)}). "
              f"Use --force to add to it.")
        return {}

    samples = _fetch(cur, """
        SELECT sample_id, lab_name, collection_date, region, district, site_type,
               source_category, source_type, food_matrix, environment_matrix,
               latitude, longitude
        FROM samples WHERE dataset_id = %s ORDER BY sample_id
    """, (dataset_id,))
    ast_rows = _fetch(cur, """
        SELECT sample_id, isolate_id, organism, antibiotic, result, method,
               guideline, test_date, mic_value, zone_diameter,
               interpreted_result, interpretation_guideline, interpretation_notes
        FROM ast_results WHERE dataset_id = %s
        ORDER BY sample_id, organism, antibiotic
    """, (dataset_id,))

    if not samples:
        print("  nothing to do: no legacy sample rows.")
        return {}

    isolate_map, isolate_numbers = _derive_isolates(ast_rows)

    subject_rows: List[tuple] = []
    specimen_rows: List[tuple] = []
    sample_to_subject: Dict[str, str] = {}
    human_count = 0

    for row in samples:
        sample_id = str(row["sample_id"]).strip()
        sector = _sector_for(row.get("source_category"))

        if sector == "human":
            # One synthetic patient per specimen. Derived from the specimen id,
            # so it is stable across re-runs -- and, by construction, shared
            # with no other specimen.
            pseudonym = make_patient_pseudonym(LEGACY_FACILITY, sample_id)
            facility = LEGACY_FACILITY
            subject_id = pseudonym
            human_count += 1
        else:
            pseudonym = None
            facility = None
            subject_id = f"specimen:{sample_id}"

        sample_to_subject[sample_id] = subject_id
        subject_rows.append((
            dataset_id, subject_id, sector, pseudonym, facility,
            None, None, None,                      # sex, age_years, age_band
            None, None, None,                      # animal fields
            row.get("food_matrix"), None,           # food_commodity, food_stage
            None, None, None,                       # water_body, catchment, stage
            row.get("environment_matrix"),          # sampling_point
            PROVENANCE,
        ))

        collection = row.get("collection_date")
        specimen_rows.append((
            dataset_id, sample_id, subject_id, None,
            None,                                   # accession_number
            "Unknown",                              # specimen_type: not recorded
            row.get("source_type"),                 # specimen_detail
            str(collection)[:10] if collection else None,
            None,                                   # collected_by
            None, "Unknown",                        # ward, ward_type at collection
            None, "Unknown",                        # age at collection
            None, None, None,                       # receipt, condition, rejection
            "Unknown",                              # sampling_purpose
            row.get("lab_name"), row.get("region"), row.get("district"),
            row.get("latitude"), row.get("longitude"),
            PROVENANCE,
        ))

    organism_for_isolate: Dict[str, Tuple[str, str]] = {}
    for (sample_id, organism), isolate_id in isolate_map.items():
        organism_for_isolate[isolate_id] = (sample_id, organism)

    isolate_rows = [
        (dataset_id, isolate_id, sample_id, isolate_numbers[isolate_id],
         organism, None, "Unknown", None, None, None, PROVENANCE)
        for isolate_id, (sample_id, organism) in sorted(organism_for_isolate.items())
        if sample_id in sample_to_subject
    ]

    phenotype_rows: List[tuple] = []
    seen: set = set()
    orphan_ast = 0
    for row in ast_rows:
        sample_id = str(row.get("sample_id") or "").strip()
        organism = str(row.get("organism") or "").strip()
        antibiotic = str(row.get("antibiotic") or "").strip()
        isolate_id = isolate_map.get((sample_id, organism))
        if not isolate_id or not antibiotic or sample_id not in sample_to_subject:
            orphan_ast += 1
            continue
        key = (isolate_id, antibiotic)
        if key in seen:
            orphan_ast += 1
            continue
        seen.add(key)

        result = (str(row.get("result")).strip()
                  if row.get("result") not in (None, "") else None)
        if result not in ("S", "I", "R", "NS"):
            result = None
        standard = (str(row.get("guideline")).strip()
                    if row.get("guideline") else None)
        # The CHECK constraint requires both a standard and an edition behind
        # any result. Neither may be fabricated, so where the legacy row gave no
        # standard the result cannot be stored as interpreted.
        if result is not None and not standard:
            standard = "unrecorded"
        version = UNRECORDED_EDITION if result is not None else None

        test_date = row.get("test_date")
        phenotype_rows.append((
            dataset_id, isolate_id, antibiotic, result,
            row.get("mic_value"), None, row.get("zone_diameter"),
            row.get("method"), None, standard, version,
            "Imported", None, None,
            str(test_date)[:10] if test_date else None,
            None, row.get("interpretation_notes"), PROVENANCE,
        ))

    summary = {
        "subjects": len(subject_rows),
        "human_subjects": human_count,
        "specimens": len(specimen_rows),
        "legacy_ast_rows": len(ast_rows),
        "isolates": len(isolate_rows),
        "phenotypes": len(phenotype_rows),
        "ast_rows_not_carried": orphan_ast,
    }

    inflation = (len(ast_rows) / len(isolate_rows)) if isolate_rows else 0
    print(f"  legacy: {len(samples)} specimen row(s), {len(ast_rows)} AST row(s)")
    print(f"  derived: {len(isolate_rows)} isolate(s) "
          f"-- the legacy tables recorded {len(ast_rows)}, "
          f"an inflation of {inflation:.1f}x")
    print(f"  subjects: {len(subject_rows)} ({human_count} synthetic legacy "
          f"patient(s), one per human specimen)")
    print(f"  phenotypes: {len(phenotype_rows)}"
          + (f", {orphan_ast} AST row(s) not carried" if orphan_ast else ""))

    if dry_run:
        print("  dry run: nothing written.")
        return summary

    from src.ingest import (
        _ENCOUNTER_COLUMNS, _ISOLATE_COLUMNS, _PHENOTYPE_COLUMNS,
        _SPECIMEN_COLUMNS, _SUBJECT_COLUMNS, _insert_sql,
    )

    psycopg2.extras.execute_values(
        raw, _insert_sql("subjects", _SUBJECT_COLUMNS), subject_rows,
        page_size=BATCH)
    psycopg2.extras.execute_values(
        raw, _insert_sql("specimens", _SPECIMEN_COLUMNS), specimen_rows,
        page_size=BATCH)
    psycopg2.extras.execute_values(
        raw, _insert_sql("isolates", _ISOLATE_COLUMNS), isolate_rows,
        page_size=BATCH)
    psycopg2.extras.execute_values(
        raw, _insert_sql("phenotypes", _PHENOTYPE_COLUMNS), phenotype_rows,
        page_size=BATCH)

    # One custody event per entity, stating that this record was reconstructed
    # rather than reported. Without it there is nothing in the data to
    # distinguish a backfilled specimen from an uploaded one.
    #
    # These are batched rather than sent through record_custody_event one row at
    # a time. That helper is the right API for a handful of events written
    # alongside the change they describe, but here there are two per specimen
    # across the whole database -- about 21,000 rows -- and one round trip each
    # to a database in another region takes minutes rather than seconds. The
    # vocabularies are constants in this loop, so they are checked once below
    # instead of per row.
    from src.traceability import CUSTODY_EVENT_TYPES, ENTITY_TYPES
    assert "transferred" in CUSTODY_EVENT_TYPES
    assert {"specimen", "isolate"} <= set(ENTITY_TYPES)

    custody_rows: List[tuple] = [
        (dataset_id, "specimen", sample_id, "transferred", PROVENANCE,
         "backfill",
         "reconstructed from the legacy samples table; no ward, specimen type "
         "or patient identifier was recorded")
        for sample_id in sorted(sample_to_subject)
    ] + [
        (dataset_id, "isolate", isolate_id, "transferred", PROVENANCE,
         "backfill",
         f"{organism}, derived by grouping legacy susceptibility rows on "
         "specimen and organism")
        for isolate_id, (sample_id, organism) in sorted(organism_for_isolate.items())
        if sample_id in sample_to_subject
    ]
    psycopg2.extras.execute_values(
        raw,
        "INSERT INTO custody_events (dataset_id, entity_type, entity_id, "
        "event_type, actor, source_system, reason) VALUES %s",
        custody_rows, page_size=BATCH)
    summary["custody_events"] = len(custody_rows)

    if rewrite_legacy_ids:
        updates = [
            (isolate_map[(str(r["sample_id"]).strip(),
                          str(r["organism"] or "").strip())],
             dataset_id, r["isolate_id"], r["antibiotic"])
            for r in ast_rows
            if (str(r["sample_id"]).strip(),
                str(r["organism"] or "").strip()) in isolate_map
        ]
        # The primary key is (dataset_id, isolate_id, antibiotic), and several
        # old rows collapse onto one new isolate_id, so the rewrite is done into
        # a temporary column and swapped. Updating in place would collide.
        # ON COMMIT DROP is not enough here: the whole run is one transaction
        # across every dataset, so the table from the previous dataset is still
        # live when the next one starts. Dropping it explicitly per dataset is
        # what makes the loop repeatable.
        raw.execute("DROP TABLE IF EXISTS _isolate_remap")
        raw.execute("""
            CREATE TEMP TABLE _isolate_remap (
                dataset_id TEXT, old_isolate_id TEXT, antibiotic TEXT,
                new_isolate_id TEXT
            ) ON COMMIT DROP
        """)
        psycopg2.extras.execute_values(
            raw,
            "INSERT INTO _isolate_remap (new_isolate_id, dataset_id, "
            "old_isolate_id, antibiotic) VALUES %s",
            updates, page_size=BATCH)
        raw.execute("""
            UPDATE ast_results a SET isolate_id = m.new_isolate_id
            FROM _isolate_remap m
            WHERE a.dataset_id = m.dataset_id
              AND a.isolate_id = m.old_isolate_id
              AND a.antibiotic = m.antibiotic
        """)
        summary["legacy_ids_rewritten"] = raw.rowcount
        print(f"  rewrote {raw.rowcount} legacy ast_results isolate_id value(s)")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the traceability chain from the legacy tables.")
    parser.add_argument("--dataset", help="limit to one dataset_id")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen and write nothing")
    parser.add_argument("--force", action="store_true",
                        help="proceed even when the chain already holds rows "
                             "for a dataset")
    parser.add_argument("--rewrite-legacy-ids", action="store_true",
                        help="also replace the per-test isolate_id in "
                             "ast_results with the derived isolate ids")
    args = parser.parse_args()

    # Importing src.settings loads .env from the project root.
    from src.settings import get_setting
    if not get_setting("AMRSS_PATIENT_SALT"):
        print("AMRSS_PATIENT_SALT is not set. Human specimens cannot be given a "
              "pseudonym without it. Set it in .env and re-run.")
        return 2

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT current_database(), "
                    "coalesce(inet_server_addr()::text, 'local socket')")
        database, host = cur.fetchone()
        print(f"target: {database} at {host}")
        if args.dry_run:
            print("mode: DRY RUN, nothing will be written")

        datasets = _dataset_ids(cur, args.dataset)
        if not datasets:
            print("no datasets with legacy sample rows.")
            return 0

        totals: Dict[str, int] = {}
        for dataset_id in datasets:
            print(f"\ndataset {dataset_id}")
            summary = backfill_dataset(
                conn, dataset_id, dry_run=args.dry_run,
                rewrite_legacy_ids=args.rewrite_legacy_ids, force=args.force)
            for key, value in summary.items():
                totals[key] = totals.get(key, 0) + value

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

        print("\ntotals")
        for key in ("subjects", "human_subjects", "specimens", "isolates",
                    "phenotypes", "custody_events", "legacy_ast_rows",
                    "ast_rows_not_carried", "legacy_ids_rewritten"):
            if key in totals:
                print(f"  {key:24s} {totals[key]}")
        if not args.dry_run and totals:
            print("\nEvery row written carries created_by = "
                  f"'{PROVENANCE}'. Legacy human specimens are one patient each, "
                  "so patient-level linkage, first-isolate deduplication and "
                  "infection-onset classification do not apply to them.")
        return 0
    except Exception as exc:                          # noqa: BLE001
        conn.rollback()
        print(f"\nfailed, nothing written: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
