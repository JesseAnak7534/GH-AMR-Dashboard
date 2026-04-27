"""Post a per-lab batch of plausible AMR demo submissions to the deployed
KoboToolbox form.

Run:
    setx KOBO_API_TOKEN "<your token>"   # then open a new shell
    python scripts/seed_kobo_demo_data.py

Or pass the token inline:
    $env:KOBO_API_TOKEN="<token>"; python scripts/seed_kobo_demo_data.py

What it does
------------
* For each of the 19 approved sentinel labs, generates a random number
  of realistic AST submissions in the range [PER_LAB_MIN, PER_LAB_MAX]
  (defaults: 100 to 120) covering the 5 One-Health sectors (HUMAN /
  ANIMAL / FOOD / ENVIRONMENT / AQUACULTURE).
* Submits each one to the form's OpenRosa endpoint as XML so they appear
  in KoboToolbox exactly as if a lab had filled the web/mobile form.
* The next time the admin clicks "Sync KoboToolbox Submissions" inside
  the dashboard, all rows will flow into the national database AND
  (because of the per-lab slicer) into each lab's own visible dataset.

Safe to re-run; each submission carries a fresh isolate_id / sample_id
so de-dup logic in the dashboard accepts every row.
"""
from __future__ import annotations

import os
import random
import sys
import uuid
import xml.sax.saxutils as xsax
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.lab_management import APPROVED_LABS  # noqa: E402

KOBO_BASE_KPI = "https://kf.kobotoolbox.org"
KOBO_BASE_KC  = "https://kc.kobotoolbox.org"
FORM_ID       = "aNZKSJhqwZukz5aoX8abvC"   # already deployed
# Per-lab volume target.  Each lab will receive a random count drawn
# uniformly from this inclusive range, giving ~100–120 submissions per
# lab and roughly 19 × 110 ≈ 2,000 rows total.
PER_LAB_MIN = 100
PER_LAB_MAX = 120

# ---------------------------------------------------------------------------
# Demo content pools
# ---------------------------------------------------------------------------
ORGANISMS = [
    "Escherichia coli", "Klebsiella pneumoniae", "Staphylococcus aureus",
    "Pseudomonas aeruginosa", "Acinetobacter baumannii", "Enterococcus faecalis",
    "Salmonella enterica", "Streptococcus pneumoniae", "Enterobacter cloacae",
    "Proteus mirabilis",
]
ANTIBIOTICS = [
    "Ampicillin", "Amoxicillin-Clavulanate", "Ceftriaxone", "Ceftazidime",
    "Cefepime", "Meropenem", "Imipenem", "Ciprofloxacin", "Levofloxacin",
    "Gentamicin", "Amikacin", "Trimethoprim-Sulfamethoxazole",
    "Piperacillin-Tazobactam", "Vancomycin", "Tetracycline",
]
SOURCE_TYPES = {
    "human":  ["Urine", "Blood", "Wound swab", "Sputum", "Stool", "CSF"],
    "animal": ["Faecal", "Milk", "Nasal swab", "Carcass swab"],
    "food":   ["Raw chicken", "Beef", "Lettuce", "Smoked fish", "Pork"],
    "env":    ["River water", "Wastewater influent", "Wastewater effluent", "Soil"],
    "aqua":   ["Pond water", "Tilapia gut", "Catfish swab"],
}
SITE_TYPES = ["Hospital ward", "Outpatient", "Slaughterhouse", "Market", "Pond", "River"]
REGIONS_DISTRICTS = [
    ("Greater Accra", "Accra Metropolitan"), ("Ashanti", "Kumasi Metropolitan"),
    ("Northern", "Tamale Metropolitan"), ("Central", "Cape Coast"),
    ("Volta", "Ho"), ("Western", "Sekondi-Takoradi"),
    ("Eastern", "Koforidua"), ("Bono", "Sunyani"),
]
GHANA_BBOX = (4.7, 11.0, -3.2, 1.2)  # min_lat, max_lat, min_lon, max_lon


# ---------------------------------------------------------------------------
# Submission building
# ---------------------------------------------------------------------------
def _rand_date(days_back_max=540) -> str:
    d = date.today() - timedelta(days=random.randint(7, days_back_max))
    return d.isoformat()


def _rand_geo() -> str:
    lat = round(random.uniform(GHANA_BBOX[0], GHANA_BBOX[1]), 5)
    lon = round(random.uniform(GHANA_BBOX[2], GHANA_BBOX[3]), 5)
    return f"{lat} {lon} 0 0"


def _build_submission_xml(idx: int, lab_name: str, lab_code: str) -> str:
    region, district = random.choice(REGIONS_DISTRICTS)
    sector_code = random.choices(
        ["human", "animal", "food", "env", "aqua"],
        weights=[5, 2, 2, 2, 1],
    )[0]
    source_type = random.choice(SOURCE_TYPES[sector_code])
    organism = random.choice(ORGANISMS)
    antibiotic = random.choice(ANTIBIOTICS)
    # Bias the result a little so charts look interesting:
    result = random.choices(["s", "i", "r"], weights=[55, 10, 35])[0]
    method = random.choice(["dd", "mic"])
    guideline = random.choice(["clsi", "eucast"])
    sample_id  = f"DEMO-{idx:04d}-{uuid.uuid4().hex[:6].upper()}"
    isolate_id = f"ISO-{idx:04d}-{uuid.uuid4().hex[:6].upper()}"
    coll_date = _rand_date()
    test_date = coll_date  # keep simple
    geo = _rand_geo()

    fields = {
        "form_intro":          "",
        "data_type":           "ast",
        "lab_name":            lab_code,
        "region":              region,
        "district":            district,
        # AST group
        "collection_date":     coll_date,
        "sample_id":           sample_id,
        "source_category":     sector_code,
        "source_type":         source_type,
        "site_type":           random.choice(SITE_TYPES),
        "food_matrix":         source_type if sector_code == "food" else "",
        "environment_matrix":  source_type if sector_code == "env"  else "",
        "geolocation":         geo,
        "isolate_id":          isolate_id,
        "organism":            organism,
        "antibiotic":          antibiotic,
        "result":              result,
        "method":              method,
        "guideline":           guideline,
        "test_date":           test_date,
        "mic_value":           f"{random.uniform(0.06, 64.0):.2f}" if method == "mic" else "",
        "zone_diameter":       f"{random.randint(6, 35)}" if method == "dd" else "",
    }
    ast_inner = "".join(
        f"<{k}>{xsax.escape(v)}</{k}>" for k, v in fields.items()
        if k in (
            "collection_date","sample_id","source_category","source_type","site_type",
            "food_matrix","environment_matrix","geolocation","isolate_id","organism",
            "antibiotic","result","method","guideline","test_date","mic_value","zone_diameter"
        )
    )
    common_inner = "".join(
        f"<{k}>{xsax.escape(v)}</{k}>" for k, v in fields.items()
        if k in ("form_intro","data_type","lab_name","region","district")
    )
    instance_id = f"uuid:{uuid.uuid4()}"
    xml = (
        f'<?xml version="1.0" ?>'
        f'<{FORM_ID} id="{FORM_ID}">'
        f'{common_inner}'
        f'<ast_section>{ast_inner}</ast_section>'
        f'<meta><instanceID>{instance_id}</instanceID></meta>'
        f'</{FORM_ID}>'
    )
    return xml


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------
def post_one(session: requests.Session, xml: str, attempt_endpoints) -> tuple[bool, str]:
    files = {
        "xml_submission_file": ("submission.xml", xml, "text/xml"),
    }
    last_err = ""
    for url in attempt_endpoints:
        try:
            r = session.post(url, files=files, timeout=20)
            if r.status_code in (200, 201, 202):
                return True, f"OK via {url}"
            last_err = f"{url} -> HTTP {r.status_code} {r.text[:160]}"
        except Exception as e:
            last_err = f"{url} -> {type(e).__name__}: {e}"
    return False, last_err


def main():
    token = os.environ.get("KOBO_API_TOKEN", "").strip()
    if not token:
        print("ERROR: please export KOBO_API_TOKEN before running.")
        sys.exit(1)

    sess = requests.Session()
    sess.headers.update({"Authorization": f"Token {token}"})

    # We try the modern KPI endpoint first, then fall back to KoBoCAT's
    # OpenRosa endpoint.  Different KoBo deployments accept different ones.
    endpoints = [
        f"{KOBO_BASE_KPI}/api/v2/assets/{FORM_ID}/data/",
        f"{KOBO_BASE_KC}/api/v1/submissions",
        f"{KOBO_BASE_KC}/submission",
    ]

    ok = 0
    fail = 0
    # Build a per-lab submission plan first so we can report progress.
    plan: list[tuple[str, str]] = []  # (lab_name, lab_code)
    for lab_name, lab_code in APPROVED_LABS.items():
        n = random.randint(PER_LAB_MIN, PER_LAB_MAX)
        plan.extend([(lab_name, lab_code)] * n)
    random.shuffle(plan)
    total = len(plan)
    print(
        f"Posting {total} submissions across {len(APPROVED_LABS)} labs "
        f"({PER_LAB_MIN}–{PER_LAB_MAX} per lab)..."
    )

    for i, (lab_name, lab_code) in enumerate(plan, start=1):
        xml = _build_submission_xml(i, lab_name, lab_code)
        success, msg = post_one(sess, xml, endpoints)
        if success:
            ok += 1
        else:
            fail += 1
            if fail <= 3:
                print(f"[{i:04d}] FAIL  {msg}")
        if i % 50 == 0:
            print(f"  ...{i}/{total}  ok={ok}  fail={fail}")

    print(f"\nDone. {ok}/{total} submitted, {fail} failed.")
    if ok:
        print(
            "\nNext step: open the dashboard, log in as the admin, go to "
            "'Upload & Data Quality' -> 'KoboToolbox Sync', click "
            "'Sync KoboToolbox Submissions'.  All rows will flow into "
            "the national database AND a per-lab dataset slice will be "
            "created for every lab that received submissions."
        )


if __name__ == "__main__":
    main()
