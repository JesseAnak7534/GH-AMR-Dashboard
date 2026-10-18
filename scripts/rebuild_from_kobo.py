"""
Bring the platform back up on an empty database, carrying only KoboToolbox data.

What it does, in order:

  1. checks the database is reachable and refuses to go further if it is not;
  2. creates the schema, which is idempotent, so this is safe on a fresh project
     and a no-op on an existing one;
  3. clears every surveillance table, leaving accounts alone;
  4. pulls every submission from the configured KoboToolbox form;
  5. runs them through the same validator the upload page uses;
  6. ingests them through the same ingest path as a workbook upload;
  7. verifies and reports what landed.

Steps 3 onwards destroy data, so the script will not run them without --yes.

Why a script rather than clicking through the app: the sequence has to happen in
this order, the clear has to be complete or the dataset is a mixture, and the
whole thing should be repeatable without anybody remembering the order. It also
fails loudly at step 1, which matters -- when the Supabase project behind this
platform was removed, every symptom appeared downstream as something else.

Usage (from the project root):

    python scripts/rebuild_from_kobo.py              # dry run: checks only
    python scripts/rebuild_from_kobo.py --yes        # clear and reload
    python scripts/rebuild_from_kobo.py --yes --keep-existing   # load, no clear
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: Everything that holds surveillance data, children before parents. `users` is
#: deliberately absent: accounts are configuration, not data.
DATA_TABLES = (
    "custody_events", "phenotypes", "genomic_results", "sequencing_runs",
    "isolates", "specimens", "encounters", "subjects",
    "ast_results", "samples",
    "signal_actions", "signals",
    "amc_records", "amu_records", "pps_prescriptions", "pps_surveys",
    "alerts", "alert_subscriptions", "predictions", "report_history",
    "datasets",
)


def _fail(step: str, detail: str) -> int:
    print(f"\n[FAILED] {step}\n  {detail}\n")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true",
                        help="actually clear and reload; without it, only checks run")
    parser.add_argument("--keep-existing", action="store_true",
                        help="skip the clear and add the Kobo data to what is there")
    args = parser.parse_args()

    from src import settings

    # -- 1. is there a database at all? ------------------------------------
    print("1. Database")
    url = settings.get_setting("DATABASE_URL")
    if not url:
        return _fail("no DATABASE_URL",
                     "Set it in .env at the project root.")
    try:
        from src import db
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT current_database(), current_user")
        row = cur.fetchone()
        conn.close()
        print(f"   connected: {dict(row) if hasattr(row, 'keys') else row}")
    except Exception as exc:                          # noqa: BLE001
        text = str(exc)
        hint = ""
        if "ENOTFOUND" in text or "Tenant or user not found" in text:
            hint = ("\n  The pooler does not recognise this project. That usually means "
                    "the Supabase project no longer exists, or was paused and removed. "
                    "Check the Supabase dashboard; if the project is gone, create a new "
                    "one and put its connection string in .env. No change to this code "
                    "will fix it.")
        elif "getaddrinfo" in text:
            hint = "\n  The host does not resolve. Check the URL, and your connection."
        return _fail("could not connect", text.strip()[:400] + hint)

    # -- 2. KoboToolbox ----------------------------------------------------
    print("\n2. KoboToolbox")
    from src.lab_management import (KoboToolboxManager, load_kobo_form_id,
                                    kobo_submissions_to_frames)
    form_id = load_kobo_form_id()
    if not form_id:
        return _fail("no form id", "None saved in db/kobo_config.json.")
    manager = KoboToolboxManager()
    ok, message = manager.authenticate()
    if not ok:
        return _fail("KoboToolbox authentication", message)
    ok, message, submissions = manager.fetch_submitted_data(form_id)
    if not ok:
        return _fail("fetching submissions", message)
    count = 0 if submissions is None else len(submissions)
    print(f"   form {form_id}: {count} submission(s)")
    if not count:
        return _fail("nothing to load",
                     "The form holds no submissions, so there is nothing to pull in.")

    # -- 3. do they survive validation? ------------------------------------
    print("\n3. Validation")
    from src import validate
    samples, isolates, ast = kobo_submissions_to_frames(submissions)
    outcome = validate.validate_frames(samples, ast, isolates_df=isolates)
    print(f"   {len(samples)} specimen(s), {len(isolates)} isolate(s), "
          f"{len(ast)} result(s)")
    print(f"   valid: {outcome.ok}   errors: {len(outcome.errors)}   "
          f"warnings: {len(outcome.warnings)}")
    for error in outcome.errors[:10]:
        print("     ERROR", error)
    if not outcome.ok:
        return _fail("validation", "Nothing was written.")

    if not args.yes:
        print("\nChecks passed. Nothing has been changed.")
        print("Re-run with --yes to clear the database and load this data.")
        return 0

    # -- 4. schema ---------------------------------------------------------
    print("\n4. Schema")
    try:
        db.init_database()
        print("   created or confirmed (idempotent)")
    except Exception as exc:                          # noqa: BLE001
        return _fail("schema creation", str(exc)[:400])

    # -- 5. clear ----------------------------------------------------------
    if args.keep_existing:
        print("\n5. Clear  -- skipped (--keep-existing)")
    else:
        print("\n5. Clear")
        conn = db.get_connection()
        cur = conn.cursor()
        cleared = 0
        try:
            for table in DATA_TABLES:
                try:
                    cur.execute(f"DELETE FROM {table}")
                    cleared += 1
                except Exception:                     # noqa: BLE001
                    # A table that does not exist on a fresh project is fine.
                    conn.rollback()
                    continue
            conn.commit()
            print(f"   emptied {cleared} table(s); accounts left untouched")
        except Exception as exc:                      # noqa: BLE001
            conn.rollback()
            return _fail("clearing data", str(exc)[:400])
        finally:
            conn.close()

    # -- 6. ingest ---------------------------------------------------------
    print("\n6. Ingest")
    from src import ingest
    dataset_id = "kobo-" + uuid.uuid4().hex[:6]
    name = f"KoboToolbox sync {datetime.now():%Y-%m-%d %H:%M}"
    result = ingest.ingest_validated_upload(dataset_id, name, outcome,
                                            uploaded_by="rebuild-from-kobo")
    print(f"   {result.ok}: {result.message}")
    for key, value in (result.counts or {}).items():
        print(f"     {key:20s} {value:,}")
    if not result.ok:
        return _fail("ingest", result.message)

    # -- 6b. consumption and prescribing -----------------------------------
    # Form version 3.1 carries these as their own submission types. They are not
    # part of the specimen chain, so they take the same three db.save_* calls
    # the upload page makes rather than going through ingest.
    print("")
    print("6b. Consumption and prescribing")
    from src.lab_management import kobo_submissions_to_consumption
    amu, amc, pps_survey, pps_rx = kobo_submissions_to_consumption(submissions)
    print(f"   decoded: AMU {len(amu)}, AMC {len(amc)}, "
          f"PPS {len(pps_survey)} survey(s) / {len(pps_rx)} prescription(s)")

    if not amu.empty:
        ok, message = db.save_amu_records(amu, "rebuild-from-kobo")
        print(f"     AMU: {message}" if ok else f"     AMU FAILED: {message}")
    if not amc.empty:
        ok, message = db.save_amc_records(amc, "rebuild-from-kobo")
        print(f"     AMC: {message}" if ok else f"     AMC FAILED: {message}")
    if not pps_survey.empty:
        from src.validate_onehealth import attribute_prescriptions
        attribution, errors = attribute_prescriptions(pps_survey, pps_rx)
        for message in errors:
            print("     PPS", message)
        stored_surveys = stored_rx = 0
        for position, (_, row) in enumerate(pps_survey.iterrows()):
            chunk = attribution.get(position)
            if chunk is None or chunk.empty:
                continue
            ok, message = db.save_pps_survey(
                f"PPS-{uuid.uuid4().hex[:8]}",
                str(row["facility_name"]), str(row["survey_date"]),
                str(row.get("region", "")), str(row.get("district", "")),
                int(row.get("total_patients") or 0),
                int(row.get("patients_on_antibiotics") or 0),
                chunk, uploaded_by="rebuild-from-kobo")
            if ok:
                stored_surveys += 1
                stored_rx += len(chunk)
            else:
                print("     PPS save failed:", message)
        print(f"     PPS: {stored_surveys} survey(s), {stored_rx} prescription(s)")

    # -- 7. verify ---------------------------------------------------------
    print("\n7. Verify")
    conn = db.get_connection()
    cur = conn.cursor()
    for table in ("datasets", "samples", "ast_results", "subjects", "specimens",
                  "isolates", "phenotypes", "custody_events",
                  "amu_records", "amc_records", "pps_surveys",
                  "pps_prescriptions"):
        try:
            cur.execute(f"SELECT count(*) AS n FROM {table}")
            row = cur.fetchone()
            n = row["n"] if hasattr(row, "keys") else row[0]
            print(f"     {table:18s} {n:,}")
        except Exception:                             # noqa: BLE001
            conn.rollback()
    conn.close()

    print()
    print("Done. The platform is carrying KoboToolbox data only.")
    print("Note: genomic_results was cleared with everything else, and "
          "the KoboToolbox form carries no sequencing data. Run "
          "scripts/generate_genomes.py --yes to repopulate the genomic "
          "layer, or load genomes from a pipeline export.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
