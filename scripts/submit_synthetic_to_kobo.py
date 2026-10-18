"""
Fill the KoboToolbox form with synthetic submissions, to exercise the mobile
data path end to end.

Why this exists
---------------
Loading the synthetic dataset straight into the database tests the upload path.
It does not test the KoboToolbox path, which is a different route into the same
tables: the form encodes every dropdown as a *choice name* (``escherichia_coli``)
rather than the label the validator checks (``Escherichia coli``), and it records
susceptibility results inside a repeat nested in another repeat. Those two
transformations are where a mobile import can silently disagree with a workbook
import, and only real submissions exercise them.

So this generates specimens with the same generator the workbook uses, converts
them into the form's own encoding, and posts them as genuine submissions. After
running it, pressing "Sync KoboToolbox Submissions" in the app pulls them back
through ``kobo_submissions_to_frames``, the shared validator and the shared
ingest -- the whole route, against data whose correct answer is known.

Submissions are given their own ``sample_id`` prefix so they cannot collide with
a workbook load of the same generator, whose ids are deterministic. That keeps
the sync's duplicate filter honest: it should import these as new, and reject
them as duplicates if the sync is run twice.

**Every record is invented.** Nothing here is an observation about any patient,
laboratory or place.

Usage (from the project root):

    python scripts/submit_synthetic_to_kobo.py --count 50
    python scripts/submit_synthetic_to_kobo.py --count 20 --prefix KOBO2
    python scripts/submit_synthetic_to_kobo.py --delete-all     # clear the form
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import uuid
from typing import Dict, Optional
from xml.sax.saxutils import escape

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import settings                                        # noqa: E402
from src.kobo_form import (BREAKPOINT_EDITIONS, _REVERSE_MAPS,   # noqa: E402
                           _slug)
from src.lab_management import KOBO_API_BASE, load_kobo_form_id  # noqa: E402

#: OpenRosa submission endpoint. The v1 API (kc.../api/v1/submission) was
#: removed and now answers 410 Gone.
SUBMISSION_URL = "https://kc.kobotoolbox.org/submission"

#: Label -> choice name, per field: the inverse of the map the sync uses to
#: decode submissions. Built by inversion rather than written out again, so the
#: two directions cannot disagree.
_TO_CODE: Dict[str, Dict[str, str]] = {
    field: {label: code for code, label in mapping.items()}
    for field, mapping in _REVERSE_MAPS.items()
}

#: (standard, version) -> the single dropdown choice that carries both. The form
#: asks for one value because two fields invite a CLSI standard with a EUCAST
#: version.
_EDITION_CODE: Dict[str, str] = {label: _slug(label) for label in BREAKPOINT_EDITIONS}


def _code(field: str, value) -> Optional[str]:
    """The form's choice name for a label, or None when there is nothing to send."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none"):
        return None
    mapping = _TO_CODE.get(field)
    if mapping is None:
        return text
    if text in mapping:
        return mapping[text]
    # Fall back to slugging: a label the map does not carry still has a stable
    # choice name, and sending it is better than dropping the answer silently.
    return _slug(text)


def _plain(value) -> Optional[str]:
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "nat"):
        return None
    return text


def _el(tag: str, value) -> str:
    """One XML element, or nothing when the value is absent."""
    if value is None:
        return ""
    return f"<{tag}>{escape(str(value))}</{tag}>"


def _edition_code(guideline, version) -> Optional[str]:
    label = f"{_plain(guideline) or ''} {_plain(version) or ''}".strip()
    if not label:
        return None
    return _EDITION_CODE.get(label, _slug(label))


def build_submission_xml(form_uid: str, sample, isolates: pd.DataFrame,
                         ast: pd.DataFrame) -> str:
    """One specimen, its isolates and their results, as an XForm instance."""
    sid = _plain(sample.get("sample_id"))
    category = _plain(sample.get("source_category")) or ""

    reporting = "".join([
        _el("lab_name", _code("lab_name", sample.get("lab_name"))),
        _el("region", _code("region", sample.get("region"))),
        _el("district", _plain(sample.get("district"))),
        _el("site_type", _plain(sample.get("site_type"))),
    ])

    specimen = "".join([
        _el("sample_id", sid),
        _el("source_category", _code("source_category", category)),
        _el("collection_date", _plain(sample.get("collection_date"))),
        _el("collection_time", _plain(sample.get("collection_time"))),
        _el("specimen_type", _code("specimen_type", sample.get("specimen_type"))),
        _el("specimen_detail", _plain(sample.get("source_type"))),
        _el("sampling_purpose", _code("sampling_purpose", sample.get("sampling_purpose"))),
        _el("receipt_date", _plain(sample.get("receipt_date"))),
        _el("receipt_time", _plain(sample.get("receipt_time"))),
        _el("condition_on_receipt",
            _code("condition_on_receipt", sample.get("condition_on_receipt"))),
        _el("rejection_reason", _plain(sample.get("rejection_reason"))),
    ])

    groups = [f"<reporting>{reporting}</reporting>",
              f"<specimen>{specimen}</specimen>"]

    if category.upper() == "HUMAN":
        age = sample.get("age_years")
        age_value = None
        try:
            if age is not None and float(age) == float(age):
                age_value = int(float(age))
        except (TypeError, ValueError):
            age_value = None
        patient = "".join([
            _el("facility_code", _plain(sample.get("facility_code"))),
            _el("facility_name", _plain(sample.get("facility_name"))),
            _el("local_patient_id", _plain(sample.get("local_patient_id"))),
            _el("sex", _code("sex", sample.get("sex"))),
            _el("age_value", age_value),
            _el("age_unit", "years" if age_value is not None else None),
            _el("patient_type", _code("patient_type", sample.get("patient_type"))),
            _el("ward", _plain(sample.get("ward"))),
            _el("ward_type", _code("ward_type", sample.get("ward_type"))),
            _el("admission_date", _plain(sample.get("admission_date"))),
        ])
        groups.append(f"<patient>{patient}</patient>")

    if category.upper() in ("ANIMAL", "AQUACULTURE"):
        animal = "".join([
            _el("animal_species", _code("animal_species", sample.get("animal_species"))),
            _el("production_type", _code("production_type", sample.get("production_type"))),
            _el("herd_flock_id", _plain(sample.get("herd_flock_id"))),
        ])
        groups.append(f"<animal_source>{animal}</animal_source>")

    # isolates, each carrying its own susceptibility results
    for _, iso in isolates.iterrows():
        isolate_id = _plain(iso.get("isolate_id"))
        results = []
        for _, row in ast[ast["isolate_id"] == isolate_id].iterrows():
            results.append("<ast_results>" + "".join([
                _el("antibiotic", _code("antibiotic", row.get("antibiotic"))),
                _el("method", _code("method", row.get("method"))),
                _el("zone_diameter", _plain(row.get("zone_diameter"))),
                _el("mic_operator", _code("mic_operator", row.get("mic_operator"))),
                _el("mic_value", _plain(row.get("mic_value"))),
                _el("result", _code("result", row.get("result"))),
                _el("guideline_version",
                    _edition_code(row.get("guideline"), row.get("guideline_version"))),
                _el("qc_status", _code("qc_status", row.get("qc_status"))),
                _el("qc_strain", _plain(row.get("qc_strain"))),
                _el("test_date", _plain(row.get("test_date"))),
            ]) + "</ast_results>")
        if not results:
            continue
        groups.append("<isolates>" + "".join([
            _el("organism", _code("organism", iso.get("organism"))),
            _el("identification_method",
                _code("identification_method", iso.get("identification_method"))),
            _el("identification_date", _plain(iso.get("identification_date"))),
            _el("is_significant", _code("is_significant", iso.get("is_significant"))),
        ]) + "".join(results) + "</isolates>")

    body = "".join(groups)
    instance = "uuid:" + str(uuid.uuid4())
    return (f"<?xml version='1.0' ?>\n<{form_uid} id=\"{form_uid}\">"
            f"<submission_type>ast</submission_type>{body}"
            f"<meta><instanceID>{instance}</instanceID></meta></{form_uid}>")




# ---------------------------------------------------------------------------
# Consumption and prescribing submissions (form v3.1)
#
# The generator emits these flat: one row per facility, period and agent. The
# form is shaped the way the paperwork is -- one submission per facility and
# period, with the agents as a repeat inside it -- so the rows are grouped back
# up before they are sent.
# ---------------------------------------------------------------------------

def _group_xml(form_uid: str, kind: str, header: str, repeats: str) -> str:
    instance = "uuid:" + str(uuid.uuid4())
    return (f"<?xml version='1.0' ?>\n<{form_uid} id=\"{form_uid}\">"
            f"<submission_type>{kind}</submission_type>{header}{repeats}"
            f"<meta><instanceID>{instance}</instanceID></meta></{form_uid}>")


def build_amu_xml(form_uid: str, facility, period, region, district,
                  patient_days, items) -> str:
    header = "<amu_report>" + "".join([
        _el("amu_facility", facility),
        _el("amu_period", period),
        _el("amu_region", _code("amu_region", region)),
        _el("amu_district", district),
        _el("amu_patient_days", patient_days),
    ]) + "</amu_report>"
    rows = []
    for row in items:
        rows.append("<amu_items>" + "".join([
            _el("amu_antibiotic", _code("amu_antibiotic", row.get("antibiotic_name"))),
            _el("amu_atc", _plain(row.get("atc_code"))),
            _el("amu_aware", _code("amu_aware", row.get("aware_category"))),
            _el("amu_formulation", _code("amu_formulation", row.get("formulation"))),
            _el("amu_unit", _code("amu_unit", row.get("unit_of_measure"))),
            _el("amu_quantity", _plain(row.get("quantity_dispensed"))),
            _el("amu_ddd", _plain(row.get("ddd_per_1000"))),
        ]) + "</amu_items>")
    return _group_xml(form_uid, "amu", header, "".join(rows))


def build_amc_xml(form_uid: str, period, region, sector, species,
                  production, biomass, items) -> str:
    header = "<amc_report>" + "".join([
        _el("amc_period", period),
        _el("amc_region", _code("amc_region", region)),
        _el("amc_sector", _code("amc_sector", str(sector).title())),
        _el("amc_species", _code("amc_species", species)),
        _el("amc_production", _code("amc_production", production)),
        _el("amc_biomass", _plain(biomass)),
    ]) + "</amc_report>"
    rows = []
    for row in items:
        rows.append("<amc_items>" + "".join([
            _el("amc_class", _code("amc_class", row.get("antibiotic_class"))),
            _el("amc_antibiotic", _code("amc_antibiotic", row.get("antibiotic_name"))),
            _el("amc_atcvet", _plain(row.get("atc_vet_code"))),
            _el("amc_quantity", _plain(row.get("quantity_kg"))),
            _el("amc_route", _code("amc_route", row.get("route"))),
            _el("amc_purpose", _code("amc_purpose", row.get("purpose"))),
        ]) + "</amc_items>")
    return _group_xml(form_uid, "amc", header, "".join(rows))


def build_pps_xml(form_uid: str, survey, prescriptions) -> str:
    header = "<pps_header>" + "".join([
        _el("pps_facility", _plain(survey.get("facility_name"))),
        _el("pps_date", _plain(survey.get("survey_date"))),
        _el("pps_region", _code("pps_region", survey.get("region"))),
        _el("pps_district", _plain(survey.get("district"))),
        _el("pps_total", _plain(survey.get("total_patients"))),
        _el("pps_on_antibiotics", _plain(survey.get("patients_on_antibiotics"))),
    ]) + "</pps_header>"
    rows = []
    for _, row in prescriptions.iterrows():
        rows.append("<pps_items>" + "".join([
            _el("pps_ward", _plain(row.get("ward"))),
            _el("pps_ward_type", _code("pps_ward_type", row.get("ward"))),
            _el("pps_age_group", _code("pps_age_group", row.get("patient_age_group"))),
            _el("pps_antibiotic", _code("pps_antibiotic", row.get("antibiotic_name"))),
            _el("pps_route", _code("pps_route", row.get("route"))),
            _el("pps_indication", _code("pps_indication", row.get("indication"))),
            _el("pps_documented", _code("pps_documented", row.get("indication_documented"))),
            _el("pps_compliant", _code("pps_compliant", row.get("guideline_compliant"))),
            _el("pps_duration", _plain(row.get("duration_days"))),
        ]) + "</pps_items>")
    return _group_xml(form_uid, "pps", header, "".join(rows))


def submit_consumption(uid: str, headers, months: int, seed: int) -> int:
    """Generate AMU, AMC and PPS records and post them through the form."""
    from scripts.generate_synthetic_data import Generator

    generator = Generator(10, seed=seed, months=months)
    generator.build_amu()
    generator.build_amc()
    generator.build_pps(surveys=6)
    pps_survey, pps_rx, amu, amc = generator.onehealth_frames()

    sent = failed = 0

    def post(xml: str) -> bool:
        r = requests.post(SUBMISSION_URL, headers=headers,
                          files={"xml_submission_file": ("submission.xml",
                                                         xml.encode("utf-8"),
                                                         "text/xml")},
                          timeout=90)
        return r.status_code in (200, 201, 202)

    # -- AMU: one submission per facility and period -----------------------
    print(f"AMU: {len(amu)} row(s) ...")
    for (facility, period), chunk in amu.groupby(["facility_name", "report_period"]):
        first = chunk.iloc[0]
        xml = build_amu_xml(uid, facility, period, first.get("region"),
                            first.get("district"), first.get("patient_days"),
                            chunk.to_dict("records"))
        if post(xml):
            sent += 1
        else:
            failed += 1
    print(f"  -> {sent} submission(s), {failed} failed")

    # -- AMC: one submission per stratum and period ------------------------
    before = sent
    print(f"AMC: {len(amc)} row(s) ...")
    for (period, species, sector), chunk in amc.groupby(
            ["report_period", "species", "sector"]):
        first = chunk.iloc[0]
        xml = build_amc_xml(uid, period, first.get("region"), sector, species,
                            first.get("production_type"), first.get("biomass_kg"),
                            chunk.to_dict("records"))
        if post(xml):
            sent += 1
        else:
            failed += 1
    print(f"  -> {sent - before} submission(s)")

    # -- PPS: one submission per survey ------------------------------------
    before = sent
    print(f"PPS: {len(pps_survey)} survey(s), {len(pps_rx)} prescription(s) ...")
    for _, survey in pps_survey.iterrows():
        mine = pps_rx[(pps_rx["facility_name"] == survey["facility_name"]) &
                      (pps_rx["survey_date"] == survey["survey_date"])]
        if mine.empty:
            continue
        if post(build_pps_xml(uid, survey, mine)):
            sent += 1
        else:
            failed += 1
    print(f"  -> {sent - before} submission(s)")

    print(f"\nsubmitted {sent}, failed {failed}")
    return 0 if failed == 0 else 1


def _delete_all(uid: str, headers: Dict[str, str]) -> int:
    removed = 0
    while True:
        r = requests.get(f"{KOBO_API_BASE}/assets/{uid}/data/?format=json&limit=200",
                         headers=headers, timeout=60)
        rows = r.json().get("results", []) if r.status_code == 200 else []
        if not rows:
            break
        for row in rows:
            d = requests.delete(f"{KOBO_API_BASE}/assets/{uid}/data/{row['_id']}/",
                                headers={**headers, "Content-Type": "application/json"},
                                timeout=60)
            removed += 1 if d.status_code in (200, 204) else 0
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=50,
                        help="how many specimens to submit (default 50)")
    parser.add_argument("--seed", type=int, default=7717)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--prefix", default="KOBO",
                        help="sample_id prefix, kept distinct from a workbook load")
    parser.add_argument("--delete-all", action="store_true",
                        help="delete every submission on the form and exit")
    parser.add_argument("--consumption", action="store_true",
                        help="submit AMU, AMC and PPS records instead of specimens")
    args = parser.parse_args()

    token = settings.get_setting("KOBO_API_TOKEN")
    if not token:
        print("KOBO_API_TOKEN is not set. Put it in .env at the project root.")
        return 1
    headers = {"Authorization": f"Token {token}"}

    uid = load_kobo_form_id()
    if not uid:
        print("No KoboToolbox form id saved. Create the form first.")
        return 1

    if args.delete_all:
        print(f"Deleting every submission on {uid} ...")
        print(f"  removed {_delete_all(uid, headers)} submission(s)")
        return 0

    if args.consumption:
        return submit_consumption(uid, headers, args.months, args.seed)

    from scripts.generate_synthetic_data import Generator
    generator = Generator(args.count, seed=args.seed, months=args.months)
    generator.run()
    samples, isolates, ast, _ = generator.frames()

    # Give this batch its own identifiers. The generator numbers samples by
    # index, so a workbook load with the same settings would produce the same
    # ids and the sync would correctly reject these as already seen.
    remap = {old: f"{args.prefix}-{i + 1:05d}"
             for i, old in enumerate(samples["sample_id"])}
    samples = samples.copy()
    samples["sample_id"] = samples["sample_id"].map(remap)
    isolates = isolates.copy()
    isolates["isolate_id"] = [
        f"{remap.get(s, s)}-{n}" for s, n in
        zip(isolates["sample_id"], isolates["isolate_number"])]
    ast = ast.copy()
    ast["isolate_id"] = [
        f"{remap.get(s, s)}-{str(i).rsplit('-', 1)[-1]}"
        for s, i in zip(ast["sample_id"], ast["isolate_id"])]
    isolates["sample_id"] = isolates["sample_id"].map(remap)
    ast["sample_id"] = ast["sample_id"].map(remap)

    print(f"Submitting {len(samples)} specimen(s) to {uid} as {args.prefix}-* ...")
    sent = failed = skipped = 0
    for _, sample in samples.iterrows():
        sid = sample["sample_id"]
        iso = isolates[isolates["sample_id"] == sid]
        rows = ast[ast["sample_id"] == sid]
        if iso.empty or rows.empty:
            skipped += 1          # culture-negative or rejected: nothing to report
            continue
        xml = build_submission_xml(uid, sample, iso, rows)
        response = requests.post(
            SUBMISSION_URL, headers=headers,
            files={"xml_submission_file": ("submission.xml", xml.encode("utf-8"),
                                           "text/xml")},
            timeout=90)
        if response.status_code in (200, 201, 202):
            sent += 1
        else:
            failed += 1
            if failed <= 3:
                print(f"  {sid}: HTTP {response.status_code} "
                      f"{response.text[:160]}")
        if (sent + failed) % 10 == 0:
            print(f"  {sent} sent, {failed} failed ...")

    print(f"\nsubmitted {sent}, failed {failed}, "
          f"skipped {skipped} (no isolate or no result)")
    print("Every record is invented and must not be quoted as a finding.")
    print('Now press "Sync KoboToolbox Submissions" in the app, or run the sync '
          'from the Data page.')
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
