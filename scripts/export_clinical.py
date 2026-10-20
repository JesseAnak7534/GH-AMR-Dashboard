"""
The clinical sections: mechanisms, hospital infection, data quality,
comparison and risk.

These five were the last pages still only reachable from the staff tool. Each
one is published here in full rather than summarised, because a summary of a
surveillance figure is a different figure.

Four decisions are worth stating, because they are the ones that make these
pages publishable at all.

**Mechanisms are counted, never listed.** The staff pages print an isolate
table beside each mechanism chart -- isolate id, organism, confidence. An
isolate id is a patient's culture, so what is published is the count of
isolates carrying each inferred mechanism, by organism and by sector, and
nothing that identifies one of them.

**Rates are never pooled across sectors.** A human blood culture and a
wastewater grab are not interchangeable observations, so mechanisms, risk and
comparison are each published once per sector and the reader switches between
them. Counts pool; percentages do not.

**Inference is labelled as inference.** ESBL, AmpC and carbapenemase here are
phenotypic patterns, not confirmed enzymes: resistance to two or more third
generation cephalosporins is consistent with an ESBL and is not a genotype.
The published figures carry that wording.

**A facility is never named.** Sentinel laboratories are named -- they are the
reporting units of a national system and are named everywhere else on the
site -- but facility codes are dropped from every comparison, because a code
identifies the hospital a patient attended.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

from scripts.export_slices import slug
from src import analytics, consumption, db, expert_rules, mdr, palette
from src import surveillance as sv

#: What a comparison may be made across. ``facility_code`` is deliberately
#: absent: it identifies the hospital a patient attended.
COMPARISON_DIMENSIONS: List[Tuple[str, str]] = [
    ("lab_name", "Laboratory"),
    ("region", "Region"),
    ("district", "District"),
    ("ward_type_at_collection", "Ward type"),
    ("specimen_type", "Specimen type"),
    ("age_band_at_collection", "Age band"),
    ("sex", "Sex"),
    ("patient_type", "Patient type"),
    ("sampling_purpose", "Sampling purpose"),
    ("organism", "Organism"),
]

#: Organism-agent pairs offered for a like-for-like comparison, at most this
#: many per sector. Pooling across every pair a laboratory happened to test is
#: the figure most easily misread, so the leading pairs are published
#: separately and the page says which one is on screen.
MAX_COMPARISON_PAIRS = 6

#: A pair is only offered for comparison if the sector holds this many
#: isolates of it. Below that no stratum within it can reach the reporting
#: floor and the table would be entirely withheld percentages.
MIN_PAIR_ISOLATES = 60

#: Period lengths offered on the over-time comparison, in months.
COMPARISON_PERIODS = (3, 6, 12)

#: ESKAPE: the organisms behind most hospital-acquired infection worldwide.
ESKAPE = [
    ("Enterococcus faecium", "Enterococcus faecium"),
    ("Staphylococcus aureus", "Staphylococcus aureus"),
    ("Klebsiella pneumoniae", "Klebsiella pneumoniae"),
    ("Acinetobacter baumannii", "Acinetobacter baumannii"),
    ("Pseudomonas aeruginosa", "Pseudomonas aeruginosa"),
    ("Enterobacter", "Enterobacter spp."),
]

#: Organisms whose presence in a hospital specimen is usually healthcare
#: associated. The same list as the staff page.
NOSOCOMIAL_KEYWORDS = [
    "enterococcus", "staphylococcus aureus", "klebsiella",
    "acinetobacter", "pseudomonas aeruginosa", "enterobacter",
    "escherichia coli", "serratia", "citrobacter", "proteus",
    "stenotrophomonas", "burkholderia", "clostridioides",
    "clostridium difficile", "candida",
]

#: What each inferred mechanism means, in one line. Published beside the
#: figure, because "ESBL" on a chart reads as a confirmed enzyme.
MECHANISM_BASIS = {
    "ESBL": "Non-susceptible to two or more third generation cephalosporins, "
            "in an organism that commonly carries an extended-spectrum "
            "beta-lactamase. A phenotype consistent with ESBL production, not "
            "a confirmed enzyme.",
    "Carbapenemase": "Resistant to at least one carbapenem. Carbapenem "
                     "resistance has causes other than a carbapenemase, "
                     "including porin loss alongside an AmpC.",
    "MRSA": "Staphylococcus aureus resistant to oxacillin, methicillin or "
            "cefoxitin.",
    "AmpC": "Resistant to two or more cephalosporins in an organism carrying "
            "an inducible chromosomal AmpC.",
    "VRSA": "Staphylococcus aureus resistant to vancomycin.",
    "VISA": "Staphylococcus aureus intermediate to vancomycin.",
}

#: Antibiotic classes screened for cross-resistance, as the staff page defines
#: them. Resistance to two agents of one class is the signal.
CROSS_RESISTANCE_CLASSES = {
    "Penicillins": ["Amoxicillin", "Ampicillin", "Penicillin", "Piperacillin"],
    "Cephalosporins (1st)": ["Cefazolin", "Cephalexin"],
    "Cephalosporins (2nd)": ["Cefuroxime", "Cefaclor"],
    "Cephalosporins (3rd)": ["Ceftazidime", "Cefotaxime", "Ceftriaxone",
                             "Cefpodoxime"],
    "Cephalosporins (4th)": ["Cefepime"],
    "Carbapenems": ["Imipenem", "Meropenem", "Ertapenem"],
    "Aminoglycosides": ["Gentamicin", "Tobramycin", "Amikacin"],
    "Fluoroquinolones": ["Ciprofloxacin", "Levofloxacin", "Ofloxacin"],
    "Tetracyclines": ["Tetracycline", "Doxycycline"],
    "Macrolides": ["Erythromycin", "Clarithromycin", "Azithromycin"],
    "Sulphonamides": ["Sulfamethoxazole", "Trimethoprim"],
    "Glycopeptides": ["Vancomycin", "Teicoplanin"],
}

#: How many agents an isolate is resistant to, banded. Three is the Magiorakos
#: floor for multidrug resistance; the bands above say how far past it.
RESISTANCE_BANDS = [(3, 4, "3-4 agents"), (5, 6, "5-6 agents"),
                    (7, 9, "7-9 agents"), (10, 10 ** 6, "10 or more agents")]

_FRESHNESS_NOTE = {
    "current": "Data is current.",
    "lagging": "The most recent specimen is over a month old. Submissions are "
               "behind.",
    "stale": "The most recent specimen is over three months old. These figures "
             "describe the past, not the present, and are not an early warning "
             "signal.",
    "no data": "No specimens in scope.",
    "no collection dates": "No collection dates recorded, so currency cannot "
                           "be judged.",
}

_RISK_SCORING_RULE = [
    {"component": "Resistance level", "condition": "over 70%", "points": "40"},
    {"component": "Resistance level", "condition": "over 50%", "points": "30"},
    {"component": "Resistance level", "condition": "over 30%", "points": "20"},
    {"component": "Evidence volume", "condition": "over 100 results",
     "points": "20"},
    {"component": "Evidence volume", "condition": "over 50 results",
     "points": "15"},
    {"component": "Evidence volume", "condition": "over 20 results",
     "points": "10"},
    {"component": "Panel breadth", "condition": "over 10 agents tested",
     "points": "40"},
    {"component": "Panel breadth", "condition": "over 5 agents tested",
     "points": "25"},
    {"component": "Panel breadth", "condition": "over 2 agents tested",
     "points": "15"},
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _prepared(frame: pd.DataFrame) -> pd.DataFrame:
    """A copy the detectors in ``src.analytics`` can read.

    They compare ``result`` to the literal ``'R'``, so a lower-case result
    stored by one laboratory would silently count as susceptible. Normalising
    here rather than editing the detectors keeps the staff tool and the public
    site reading the same code.
    """
    if frame.empty:
        return frame
    working = frame.copy()
    working["result"] = working["result"].astype(str).str.strip().str.upper()
    working = working[working["result"].isin(["R", "I", "S", "NS"])]
    for column in ("organism", "antibiotic", "isolate_id"):
        working[column] = working[column].astype(str).str.strip()
        working = working[working[column] != ""]
    return working


def _sector_slices(frame: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    return [(str(sector), frame[frame["sector"] == sector])
            for sector in sorted(frame["sector"].dropna().unique())]


def _colour(sector: str) -> str:
    return palette.SECTOR.get(sector, palette.GREY)


def _percent(numerator: int, denominator: int) -> Optional[float]:
    return 100 * numerator / denominator if denominator else None


def _resistance_rate(group: pd.DataFrame) -> Optional[float]:
    return _percent(int((group["result"] == "R").sum()), int(len(group)))


def _informative(value) -> bool:
    text = str(value).strip().lower()
    return bool(text) and text not in {"nan", "none", "unknown", "not recorded",
                                       "n/a", "na", "null", "-"}


# ---------------------------------------------------------------------------
# 1. Resistance mechanisms
# ---------------------------------------------------------------------------

def _mechanism_table(detected: pd.DataFrame) -> pd.DataFrame:
    """Mechanism counts by organism. Isolate identifiers are dropped here."""
    if detected.empty:
        return pd.DataFrame()
    rows = []
    for (mechanism, organism), group in detected.groupby(
            ["resistance_mechanism", "organism"]):
        confidence = group["confidence"].astype(str)
        rows.append({
            "mechanism": str(mechanism),
            "organism": str(organism),
            "isolates": int(group["isolate_id"].nunique()),
            "high": int((confidence == "High").sum()),
            "moderate": int((confidence == "Moderate").sum()),
        })
    table = pd.DataFrame(rows)
    return (table.sort_values(["mechanism", "isolates"],
                              ascending=[True, False])
            .reset_index(drop=True))


def _cross_resistance_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Isolates resistant to two or more agents within one class."""
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for label, agents in CROSS_RESISTANCE_CLASSES.items():
        pattern = "|".join(agents)
        in_class = frame[frame["antibiotic"].str.contains(
            pattern, case=False, na=False, regex=True)]
        if in_class.empty:
            continue
        high = moderate = tested = 0
        for _, group in in_class.groupby("isolate_id"):
            if len(group) < 2:
                continue
            tested += 1
            resistant = int((group["result"] == "R").sum())
            if resistant < 2:
                continue
            if resistant == len(group):
                high += 1
            else:
                moderate += 1
        if not tested:
            continue
        rows.append({
            "antibioticClass": label,
            "isolates": high + moderate,
            "high": high,
            "moderate": moderate,
            "testedOnTwoOrMore": tested,
            "percent": _percent(high + moderate, tested),
        })
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values("isolates", ascending=False).reset_index(drop=True)


def _multiple_resistance(frame: pd.DataFrame):
    """How many agents each isolate is resistant to, banded and by organism."""
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    counted = analytics.get_multiple_resistance_patterns(frame,
                                                         min_resistances=1)
    if counted.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    screened = int(frame["isolate_id"].nunique())
    multidrug = counted[counted["resistant_antibiotics"] >= 3]

    bands = pd.DataFrame([
        {"band": label,
         "isolates": int(len(multidrug[
             (multidrug["resistant_antibiotics"] >= low)
             & (multidrug["resistant_antibiotics"] <= high)]))}
        for low, high, label in RESISTANCE_BANDS
    ])

    if multidrug.empty:
        return bands, pd.DataFrame(), {
            "isolates": 0, "isolatesScreened": screened, "percent": 0.0,
            "medianAgents": None}

    by_organism = (multidrug.groupby("organism")
                   .agg(isolates=("isolate_id", "nunique"),
                        medianAgents=("resistant_antibiotics", "median"),
                        maxAgents=("resistant_antibiotics", "max"))
                   .reset_index()
                   .sort_values("isolates", ascending=False))
    by_organism["organism"] = by_organism["organism"].astype(str)
    by_organism["medianAgents"] = by_organism["medianAgents"].astype(float)
    by_organism["maxAgents"] = by_organism["maxAgents"].astype(int)

    headline = {
        "isolates": int(len(multidrug)),
        "isolatesScreened": screened,
        "percent": _percent(int(len(multidrug)), screened),
        "medianAgents": float(multidrug["resistant_antibiotics"].median()),
    }
    return bands, by_organism, headline


def export_mechanisms(frame: pd.DataFrame, threshold: int, rows, suppress
                      ) -> Dict[str, object]:
    """Inferred resistance mechanisms, cross-resistance and breadth."""
    prepared = _prepared(frame)
    slices = []

    for sector, subset in _sector_slices(prepared):
        if subset.empty:
            continue
        deduplicated, _ = sv.select_first_isolates(subset, period_months=None)
        if deduplicated.empty:
            continue

        screened = int(deduplicated["isolate_id"].nunique())

        sentinel = pd.DataFrame([{
            "code": item["code"],
            "label": item["label"],
            "whoTier": item["who_tier"],
            "positive": int(item["isolate_count"]),
            "tested": int(item["total_tested"]),
            "percent": item["resistance_rate"],
        } for item in analytics.detect_sentinel_phenotypes(deduplicated)])
        if not sentinel.empty:
            shown_sentinel, sentinel_suppression = suppress(
                sentinel, ["positive", "tested"], threshold, blank=["percent"])
        else:
            shown_sentinel, sentinel_suppression = sentinel, None

        detected = analytics.detect_resistance_mechanisms(deduplicated)
        by_organism = _mechanism_table(detected)
        if not by_organism.empty:
            shown_mechanisms, mechanism_suppression = suppress(
                by_organism, ["isolates", "high", "moderate"], threshold,
                group_by="mechanism")
            totals = (by_organism.groupby("mechanism")["isolates"].sum()
                      .reset_index().sort_values("isolates", ascending=False))
            totals["percent"] = totals["isolates"].map(
                lambda n: _percent(int(n), screened))
            totals["basis"] = totals["mechanism"].map(
                lambda m: MECHANISM_BASIS.get(str(m), ""))
            shown_totals, total_suppression = suppress(
                totals, ["isolates"], threshold, blank=["percent"])
        else:
            shown_mechanisms, mechanism_suppression = pd.DataFrame(), None
            shown_totals, total_suppression = pd.DataFrame(), None

        cross = _cross_resistance_table(deduplicated)
        if not cross.empty:
            shown_cross, cross_suppression = suppress(
                cross, ["isolates", "high", "moderate"], threshold,
                blank=["percent"])
        else:
            shown_cross, cross_suppression = cross, None

        bands, breadth, breadth_headline = _multiple_resistance(deduplicated)
        if not bands.empty:
            shown_bands, band_suppression = suppress(bands, ["isolates"],
                                                     threshold)
        else:
            shown_bands, band_suppression = bands, None
        if not breadth.empty:
            shown_breadth, breadth_suppression = suppress(
                breadth, ["isolates"], threshold,
                blank=["medianAgents", "maxAgents"])
        else:
            shown_breadth, breadth_suppression = breadth, None

        slices.append({
            "sector": sector,
            "colour": _colour(sector),
            "isolatesScreened": screened,
            "observations": int(len(deduplicated)),
            "sentinel": {"rows": rows(shown_sentinel),
                         "suppression": sentinel_suppression},
            "mechanisms": {
                "totals": rows(shown_totals),
                "totalSuppression": total_suppression,
                "rows": rows(shown_mechanisms),
                "suppression": mechanism_suppression,
            },
            "crossResistance": {"rows": rows(shown_cross),
                                "suppression": cross_suppression},
            "breadth": {
                "bands": rows(shown_bands),
                "bandSuppression": band_suppression,
                "rows": rows(shown_breadth),
                "suppression": breadth_suppression,
                **breadth_headline,
            },
        })

    return {"slices": slices, "basis": MECHANISM_BASIS}


# ---------------------------------------------------------------------------
# 2. Hospital-acquired infection
# ---------------------------------------------------------------------------

def _is_nosocomial(organism) -> bool:
    lowered = str(organism).lower()
    return any(keyword in lowered for keyword in NOSOCOMIAL_KEYWORDS)


def export_hai(frame: pd.DataFrame, threshold: int, rows, suppress
               ) -> Dict[str, object]:
    """Hospital infection: ESKAPE, the hospital profile, MDR and the trend.

    Human clinical specimens only. The staff page reaches the same population
    through a site-type heuristic; here the sector is the definition, which is
    the same set of specimens and one rule rather than two.
    """
    prepared = _prepared(frame)
    hospital = prepared[prepared["sector"].astype(str).str.lower() == "human"]
    if hospital.empty:
        return {"available": False}

    hospital, _ = sv.select_first_isolates(hospital, period_months=None)
    if hospital.empty:
        return {"available": False}

    hospital = hospital.copy()
    hospital["is_nosocomial"] = hospital["organism"].map(_is_nosocomial)

    classified = mdr.classify_frame(hospital)
    multidrug_ids = set()
    if not classified.empty:
        multidrug_ids = set(classified.loc[
            classified["classification"].isin(
                [mdr.CLASS_MDR, mdr.CLASS_XDR, mdr.CLASS_PDR]),
            "isolate_id"].astype(str))
    hospital["is_mdr"] = hospital["isolate_id"].astype(str).isin(multidrug_ids)

    observations = int(len(hospital))
    isolates = int(hospital["isolate_id"].nunique())
    nosocomial = hospital[hospital["is_nosocomial"]]
    nosocomial_isolates = int(nosocomial["isolate_id"].nunique())
    other = hospital[~hospital["is_nosocomial"]]

    headline = {
        "isolates": isolates,
        "observations": observations,
        "nosocomialIsolates": nosocomial_isolates,
        "nosocomialPercent": _percent(nosocomial_isolates, isolates),
        "mdrIsolates": len(multidrug_ids),
        "mdrPercent": _percent(len(multidrug_ids), isolates),
        "resistancePercent": _resistance_rate(hospital),
        "organisms": int(hospital["organism"].nunique()),
        "laboratories": int(hospital["lab_name"].nunique()),
        "classifiable": int((classified["classification"]
                             != mdr.CLASS_INSUFFICIENT).sum())
        if not classified.empty else 0,
    }

    eskape_rows = []
    for keyword, label in ESKAPE:
        match = hospital[hospital["organism"].str.contains(
            keyword, case=False, na=False)]
        if match.empty:
            continue
        match_isolates = int(match["isolate_id"].nunique())
        mdr_isolates = int(match[match["is_mdr"]]["isolate_id"].nunique())
        eskape_rows.append({
            "organism": label,
            "isolates": match_isolates,
            "observations": int(len(match)),
            "resistancePercent": _resistance_rate(match),
            "mdrIsolates": mdr_isolates,
            "mdrPercent": _percent(mdr_isolates, match_isolates),
        })
    eskape = pd.DataFrame(eskape_rows)
    if not eskape.empty:
        eskape = eskape.sort_values("resistancePercent", ascending=False)
        shown_eskape, eskape_suppression = suppress(
            eskape, ["isolates", "observations", "mdrIsolates"], threshold,
            blank=["resistancePercent", "mdrPercent"])
    else:
        shown_eskape, eskape_suppression = eskape, None

    profile = pd.DataFrame([{
        "organism": str(organism),
        "observations": int(len(group)),
        "isolates": int(group["isolate_id"].nunique()),
        "resistancePercent": _resistance_rate(group),
        "nosocomial": bool(_is_nosocomial(organism)),
    } for organism, group in hospital.groupby("organism")])
    if not profile.empty:
        profile = (profile.sort_values("observations", ascending=False)
                   .head(15).reset_index(drop=True))
        shown_profile, profile_suppression = suppress(
            profile, ["observations", "isolates"], threshold,
            blank=["resistancePercent"])
    else:
        shown_profile, profile_suppression = profile, None

    split = pd.DataFrame([
        {"group": "Nosocomial organisms",
         "isolates": nosocomial_isolates,
         "observations": int(len(nosocomial)),
         "resistancePercent": _resistance_rate(nosocomial)
         if not nosocomial.empty else None},
        {"group": "Other organisms",
         "isolates": int(other["isolate_id"].nunique()),
         "observations": int(len(other)),
         "resistancePercent": _resistance_rate(other)
         if not other.empty else None},
    ])
    shown_split, split_suppression = suppress(
        split, ["isolates", "observations"], threshold,
        blank=["resistancePercent"])

    multidrug_frame = hospital[hospital["is_mdr"]]
    mdr_payload: Dict[str, object] = {"rows": [], "suppression": None,
                                      "topOrganism": None, "classes": None}
    if not multidrug_frame.empty:
        distribution = (multidrug_frame.groupby("organism")["isolate_id"]
                        .nunique().reset_index(name="isolates")
                        .sort_values("isolates", ascending=False).head(15))
        distribution["organism"] = distribution["organism"].astype(str)
        shown_distribution, distribution_suppression = suppress(
            distribution, ["isolates"], threshold)
        top = str(distribution.iloc[0]["organism"])
        top_frame = multidrug_frame[multidrug_frame["organism"] == top].copy()
        _, categories = mdr.category_set_for(top)
        if categories:
            top_frame["category"] = top_frame["antibiotic"].map(
                lambda a: mdr.categorise_agent(a, categories) or "Other")
            classes = pd.DataFrame([{
                "antibioticClass": str(category),
                "observations": int(len(group)),
                "resistancePercent": _resistance_rate(group),
            } for category, group in top_frame.groupby("category")])
            classes = classes.sort_values("resistancePercent", ascending=False)
            shown_classes, class_suppression = suppress(
                classes, ["observations"], threshold,
                blank=["resistancePercent"])
            mdr_payload["classes"] = {"rows": rows(shown_classes),
                                      "suppression": class_suppression}
        mdr_payload["rows"] = rows(shown_distribution)
        mdr_payload["suppression"] = distribution_suppression
        mdr_payload["topOrganism"] = top

    def _by(column: str) -> Dict[str, object]:
        """Resistance by a reporting unit.

        A sentinel laboratory is named -- it is a reporting unit of the
        national system and is named everywhere else on this site. A facility
        is not, and no facility column reaches this function.
        """
        if column not in hospital.columns:
            return {"rows": [], "suppression": None}
        grouped = [{
            column: str(value).strip(),
            "observations": int(len(group)),
            "isolates": int(group["isolate_id"].nunique()),
            "resistancePercent": _resistance_rate(group),
            "mdrIsolates": int(group[group["is_mdr"]]["isolate_id"].nunique()),
        } for value, group in hospital.groupby(column, dropna=True)
            if _informative(value)]
        table = pd.DataFrame(grouped)
        if table.empty:
            return {"rows": [], "suppression": None}
        table = table.sort_values("resistancePercent", ascending=False)
        shown, suppression = suppress(
            table, ["observations", "isolates", "mdrIsolates"], threshold,
            blank=["resistancePercent"])
        return {"rows": rows(shown.rename(columns={column: "group"})),
                "suppression": suppression}

    trend_points: List[Dict[str, object]] = []
    dated = hospital[hospital["collection_datetime"].notna()].copy()
    if not dated.empty:
        stamps = dated["collection_datetime"]
        if getattr(stamps.dtype, "tz", None) is not None:
            stamps = stamps.dt.tz_localize(None)
        dated["period"] = stamps.dt.to_period("Q").astype(str)
        for period, group in dated.groupby("period"):
            count = int(len(group))
            period_isolates = int(group["isolate_id"].nunique())
            if count < sv.MIN_ISOLATES_FOR_REPORTING:
                trend_points.append({"period": str(period),
                                     "observations": count,
                                     "resistancePercent": None,
                                     "mdrPercent": None,
                                     "nosocomialPercent": None})
                continue
            trend_points.append({
                "period": str(period),
                "observations": count,
                "resistancePercent": _resistance_rate(group),
                "mdrPercent": _percent(
                    int(group[group["is_mdr"]]["isolate_id"].nunique()),
                    period_isolates),
                "nosocomialPercent": _percent(
                    int(group[group["is_nosocomial"]]["isolate_id"].nunique()),
                    period_isolates),
            })
        trend_points.sort(key=lambda point: str(point["period"]))

    return {
        "available": True,
        "headline": headline,
        "eskape": {"rows": rows(shown_eskape),
                   "suppression": eskape_suppression},
        "profile": {"rows": rows(shown_profile),
                    "suppression": profile_suppression},
        "split": {"rows": rows(shown_split), "suppression": split_suppression},
        "mdr": mdr_payload,
        "laboratories": _by("lab_name"),
        "regions": _by("region"),
        "trend": {"points": trend_points,
                  "minObservations": sv.MIN_ISOLATES_FOR_REPORTING},
    }


# ---------------------------------------------------------------------------
# 3. Data coverage and quality
# ---------------------------------------------------------------------------

def export_quality(frame: pd.DataFrame, threshold: int, rows, suppress
                   ) -> Dict[str, object]:
    """Whether the data can support the figures drawn from it.

    This page is the only one where a count of zero is the finding, so nothing
    here is suppressed into silence: a field that nobody filled is reported as
    nobody filled it. What is withheld is a cell small enough to identify
    somebody, and the counts on this page are of fields and results, not of
    people.
    """
    report = sv.coverage_report()

    completeness = report.completeness.rename(columns={
        "Field": "field", "Column": "column", "Scope": "scope",
        "Recorded": "recorded", "Of": "of", "Percent": "percent",
        "Status": "status"})
    not_collected = [str(row["field"]) for _, row in completeness.iterrows()
                     if row["status"] == "not collected"]

    sectors = [{"sector": sector, "specimens": int(count),
                "colour": _colour(sector)}
               for sector, count in report.sectors.items()]

    freshness = report.freshness or {}
    status = str(freshness.get("status", "no data"))
    turnaround = (report.quality or {}).get("turnaround") or {}

    quality = report.quality or {}
    sources = quality.get("result_source") or {}
    source_rows = [{"source": str(name), "results": int(count)}
                   for name, count in sources.items()]

    linkage = report.linkage or {}
    specimens_total = int(linkage.get("specimens_total") or 0)
    isolates_total = int(linkage.get("isolates_total") or 0)

    findings = expert_rules.screen_frame(frame)
    plausibility: Dict[str, object] = {
        "rows": [], "suppression": None, "impossiblePairs": 0,
        "suppressPairs": 0, "observationsAffected": 0,
        "percentAffected": None, "recordedSusceptible": 0,
        "resultsTotal": int(len(frame)),
    }
    if not findings.empty:
        errors = findings[findings["severity"] == expert_rules.SEVERITY_ERROR]
        unreportable = findings[
            findings["severity"] == expert_rules.SEVERITY_SUPPRESS]
        affected = int(findings["observations"].sum())
        shown_findings, finding_suppression = suppress(
            findings.rename(columns={
                "organism": "organism", "antibiotic": "antibiotic",
                "severity": "kind", "observations": "results",
                "reported_susceptible": "recordedSusceptible",
                "reason": "reason"}),
            ["results"], threshold)
        plausibility = {
            "rows": rows(shown_findings),
            "suppression": finding_suppression,
            "impossiblePairs": int(len(errors)),
            "suppressPairs": int(len(unreportable)),
            "observationsAffected": affected,
            "percentAffected": _percent(affected, int(len(frame))),
            "recordedSusceptible": int(errors["reported_susceptible"].sum())
            if not errors.empty else 0,
            "resultsTotal": int(len(frame)),
        }

    denominators: Dict[str, object] = {"rows": [], "metrics": [],
                                       "available": False}
    try:
        amu = db.get_amu_records()
        amc = db.get_amc_records()
        coverage = consumption.denominator_coverage(amu, amc)
        if not coverage.empty:
            denominators = {
                "available": True,
                "rows": rows(coverage.rename(columns={
                    "Dataset": "dataset", "Records": "records",
                    "Denominator": "denominator",
                    "With a usable denominator": "withDenominator",
                    "Percent": "percent",
                    "Consequence if missing": "consequence"})),
                "metrics": rows(consumption.metrics_frame()),
            }
    except Exception as error:                        # noqa: BLE001
        denominators = {"rows": [], "metrics": [], "available": False,
                        "error": str(error)}

    return {
        "headline": report.headline,
        "coverage": {
            "specimens": int(report.specimens),
            "isolates": int(report.isolates),
            "observations": int(report.observations),
            "patients": int(report.patients),
            "laboratories": int(report.labs),
            "sectors": sectors,
        },
        "completeness": {
            "rows": rows(completeness),
            "notCollected": not_collected,
        },
        "timeliness": {
            "latest": str(freshness.get("latest_collection") or "") or None,
            "daysSinceLatest": freshness.get("days_since_latest"),
            "status": status,
            "note": _FRESHNESS_NOTE.get(status, ""),
            "turnaroundMedianDays": turnaround.get("median_days"),
            "turnaroundMeasurable": int(turnaround.get("measurable", 0) or 0),
        },
        "linkage": {
            "culturePositivityPercent": linkage.get(
                "culture_positivity_percent"),
            "specimensTotal": specimens_total,
            "specimensWithIsolate": int(
                linkage.get("specimens_with_isolate") or 0),
            "specimensWithWard": int(linkage.get("specimens_with_ward") or 0),
            "specimensWithWardPercent": _percent(
                int(linkage.get("specimens_with_ward") or 0), specimens_total),
            "isolatesTotal": isolates_total,
            "isolatesWithResult": int(linkage.get("isolates_with_result") or 0),
            "isolatesWithResultPercent": _percent(
                int(linkage.get("isolates_with_result") or 0), isolates_total),
            "genomicResults": int(linkage.get("genomic_results") or 0),
            "isolatesSequenced": int(linkage.get("isolates_sequenced") or 0),
            "percentIsolatesSequenced": linkage.get(
                "percent_isolates_sequenced"),
        },
        "resultQuality": {
            "qcRecorded": int(quality.get("qc_recorded") or 0),
            "qcTotal": int(quality.get("qc_total") or 0),
            "qcRecordedPercent": _percent(int(quality.get("qc_recorded") or 0),
                                          int(quality.get("qc_total") or 0)),
            "qcPass": int(quality.get("qc_pass") or 0),
            "qcFail": int(quality.get("qc_fail") or 0),
            "resultsWithoutEdition": int(
                quality.get("results_without_edition") or 0),
            "sources": source_rows,
        },
        "plausibility": plausibility,
        "denominators": denominators,
    }


# ---------------------------------------------------------------------------
# 4. Comparative analysis
# ---------------------------------------------------------------------------

def _comparison_rows(table: pd.DataFrame, column: str, value_column: str
                     ) -> pd.DataFrame:
    """One stratified table, renamed for the front end."""
    unit_column = ("observations" if "observations" in table.columns
                   else "tested")
    out = pd.DataFrame({
        "group": table[column].astype(str),
        "unit": table[unit_column],
        "percent": table[value_column],
        "ciLow": table["ci_low"],
        "ciHigh": table["ci_high"],
        "status": table["status"],
    })
    if "isolates" in table.columns:
        out["isolates"] = table["isolates"]
    if "tested" in table.columns and unit_column != "tested":
        out["tested"] = table["tested"]
    if "distinct_pairs" in table.columns:
        out["pairs"] = table["distinct_pairs"]
    if "susceptible" in table.columns:
        out["susceptible"] = table["susceptible"]
    if "non_susceptible" in table.columns:
        out["nonSusceptible"] = table["non_susceptible"]
    return out


def _leading_pairs(frame: pd.DataFrame) -> List[Tuple[str, str, int]]:
    """The organism-agent pairs with enough isolates to compare across.

    One pair per organism. Taking the largest pairs outright gave six agents
    of the same organism in every sector, which answers one question six times
    and leaves the second organism unanswerable.
    """
    deduplicated, _ = sv.select_first_isolates(frame, period_months=None)
    if deduplicated.empty:
        return []
    counted = (deduplicated.groupby(["organism", "antibiotic"])["isolate_id"]
               .nunique().reset_index(name="isolates")
               .sort_values("isolates", ascending=False))
    counted = counted[counted["isolates"] >= MIN_PAIR_ISOLATES]

    chosen: List[Tuple[str, str, int]] = []
    seen: set = set()
    for _, row in counted.iterrows():
        organism = str(row["organism"])
        if organism in seen:
            continue
        seen.add(organism)
        chosen.append((organism, str(row["antibiotic"]), int(row["isolates"])))
        if len(chosen) >= MAX_COMPARISON_PAIRS:
            break
    return chosen


def export_comparison(frame: pd.DataFrame, out_dir: str, threshold: int,
                      rows, suppress) -> Dict[str, object]:
    """Groups compared on one denominator, with the uncertainty beside each.

    The staff page lets a reader choose any dimension, organism and agent and
    computes the table on demand. A static site cannot answer an arbitrary
    combination, and should not: narrowing by laboratory, region, ward and
    organism is exactly how a reader reaches a cell holding one person. So the
    publishable combinations are computed here -- every dimension pooled, and
    every dimension for each of the leading organism-agent pairs -- and the
    page switches between them.

    The pooled view of each sector travels in the page, so the table is there
    in the first paint. A single organism-agent pair is a second question and
    goes in a file of its own, fetched when it is asked for -- the same trade
    the filtered antibiograms make, and for the same reason: ten dimensions
    for six pairs in five sectors is most of a megabyte of tables for views
    most readers never open.

    Interval overlap is not computed here. The intervals travel with each row,
    and the comparison a reader makes between two of them happens in the
    browser against figures that were already cleared for publication.
    """
    prepared = _prepared(frame)
    directory = os.path.join(out_dir, "slices", "comparison")
    os.makedirs(directory, exist_ok=True)
    slices = []

    for sector, subset in _sector_slices(prepared):
        if subset.empty:
            continue

        kept, findings = expert_rules.drop_unreportable(subset)
        if kept.empty:
            continue

        pairs = _leading_pairs(kept)
        views = []

        # The pooled view: every organism-agent pair the sector tested.
        pooled_dimensions = []
        for column, label in COMPARISON_DIMENSIONS:
            if column not in kept.columns:
                continue
            table = sv.stratified_resistance(kept, by=column,
                                             allow_cross_sector=True)
            if table.empty:
                continue
            shown, suppression = suppress(
                _comparison_rows(table, column, "percent_non_susceptible"),
                ["unit", "isolates"], threshold,
                blank=["percent", "ciLow", "ciHigh"])
            pooled_dimensions.append({
                "key": column, "label": label,
                "rows": rows(shown), "suppression": suppression,
            })
        if pooled_dimensions:
            views.append({
                "key": "pooled",
                "slug": None,
                "label": "All organisms and agents",
                "measure": "% non-susceptible",
                "unitLabel": "Observations",
                "pooled": True,
                "dimensions": pooled_dimensions,
            })

        # One view per leading pair, where the unit is an isolate.
        for organism, antibiotic, isolates in pairs:
            dimensions = []
            for column, label in COMPARISON_DIMENSIONS:
                if column not in kept.columns or column == "organism":
                    continue
                table = sv.stratified_susceptibility(
                    kept, by=column, organism=organism, antibiotic=antibiotic,
                    allow_cross_sector=True)
                if table.empty:
                    continue
                shown, suppression = suppress(
                    _comparison_rows(table, column, "percent_susceptible"),
                    ["unit"], threshold,
                    blank=["percent", "ciLow", "ciHigh"])
                dimensions.append({
                    "key": column, "label": label,
                    "rows": rows(shown), "suppression": suppression,
                })
            if not dimensions:
                continue
            name = slug(sector, organism, antibiotic)
            with open(os.path.join(directory, f"{name}.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"dimensions": dimensions}, handle,
                          ensure_ascii=False, allow_nan=False,
                          separators=(",", ":"))
            views.append({
                "key": f"{organism}|{antibiotic}",
                "slug": name,
                "label": f"{organism} - {antibiotic}",
                "measure": "% susceptible",
                "unitLabel": "Isolates tested",
                "pooled": False,
                "isolates": isolates,
                "dimensions": None,
            })

        # Over time: the most recent window against the one before it.
        periods = []
        dated = kept[kept["collection_datetime"].notna()]
        if not dated.empty:
            latest = dated["collection_datetime"].max()
            for months in COMPARISON_PERIODS:
                window = pd.Timedelta(days=int(30.44 * months))
                boundary = latest - window
                start = boundary - window
                recent = dated[dated["collection_datetime"] > boundary].copy()
                baseline = dated[
                    (dated["collection_datetime"] > start)
                    & (dated["collection_datetime"] <= boundary)].copy()
                if recent.empty or baseline.empty:
                    continue
                recent["period"] = f"Most recent {months} months"
                baseline["period"] = f"Preceding {months} months"
                combined = pd.concat([baseline, recent], ignore_index=True)
                table = sv.stratified_resistance(combined, by="period",
                                                 allow_cross_sector=True)
                if table.empty:
                    continue
                shown, suppression = suppress(
                    _comparison_rows(table, "period",
                                     "percent_non_susceptible"),
                    ["unit", "isolates"], threshold,
                    blank=["percent", "ciLow", "ciHigh"])
                periods.append({
                    "months": months,
                    "rows": rows(shown),
                    "suppression": suppression,
                })

        slices.append({
            "sector": sector,
            "colour": _colour(sector),
            "isolates": int(kept["isolate_id"].nunique()),
            "excludedPairs": int(len(findings)),
            "views": views,
            "periods": periods,
        })

    return {"slices": slices,
            "minIsolatesForReporting": sv.MIN_ISOLATES_FOR_REPORTING,
            "periods": list(COMPARISON_PERIODS)}


# ---------------------------------------------------------------------------
# 5. Risk assessment
# ---------------------------------------------------------------------------

def export_risk(frame: pd.DataFrame, threshold: int, rows, suppress
                ) -> Dict[str, object]:
    """The composite risk indicator, the burden, and the forward-looking views.

    This carries both of the old Risk Assessment tabs and all four live tabs
    of the old Advanced Analytics page -- statistics, trend direction, organism
    and agent comparison, the forecast, emerging patterns and the exploratory
    susceptibility summary. They belong on one page because each of them is an
    attempt to say which way things are going, and splitting them across two
    pages made the dashboard look like it had two answers.

    The scoring rule travels with the score, because the score is a way of
    ordering a list for review and not a validated measure of danger.
    """
    prepared = _prepared(frame)
    slices = []

    for sector, subset in _sector_slices(prepared):
        if subset.empty:
            continue

        statistics = analytics.calculate_resistance_statistics(subset)
        trend = analytics.calculate_trend_direction(subset)

        # Risk scores. The staff page filters by a slider on resistance rate;
        # every organism is published and the page does the filtering.
        scores = pd.DataFrame([{
            "organism": str(score["organism"]),
            "riskScore": int(score["risk_score"]),
            "riskLevel": str(score["risk_level"]),
            "resistancePercent": float(score["resistance_rate"]),
            "observations": int(score["test_count"]),
            "antibioticDiversity": int(score["antibiotic_diversity"]),
            "factors": "; ".join(score["risk_factors"]),
        } for score in (analytics.calculate_organism_risk_score(subset, organism)
                        for organism in sorted(subset["organism"].unique()))
            if score])
        if not scores.empty:
            scores = scores.sort_values("riskScore", ascending=False)
            shown_scores, score_suppression = suppress(
                scores, ["observations"], threshold,
                blank=["resistancePercent", "riskScore", "riskLevel",
                       "antibioticDiversity", "factors"])
        else:
            shown_scores, score_suppression = scores, None

        # Burden, by the categories the platform actually records: the sector
        # is already fixed here, so the split is by specimen type.
        burden_rows = pd.DataFrame([{
            "group": str(value).strip(),
            "observations": int(len(group)),
            "resistantObservations": int((group["result"] == "R").sum()),
            "resistancePercent": _resistance_rate(group),
        } for value, group in subset.groupby("specimen_type", dropna=True)
            if _informative(value)])
        if not burden_rows.empty:
            burden_rows = burden_rows.sort_values("resistancePercent",
                                                  ascending=False)
            shown_burden, burden_suppression = suppress(
                burden_rows, ["observations", "resistantObservations"],
                threshold, blank=["resistancePercent"])
        else:
            shown_burden, burden_suppression = burden_rows, None

        overall = _resistance_rate(subset) or 0.0
        if overall > 50:
            impact = "Highest band on this indicator."
        elif overall > 30:
            impact = "Upper band on this indicator."
        elif overall > 15:
            impact = "Middle band on this indicator."
        else:
            impact = "Lower band on this indicator."

        emerging = pd.DataFrame([{
            "organism": str(item["organism"]),
            "antibiotic": str(item["antibiotic"]),
            "resistancePercent": float(item["resistance_rate"]),
            "observations": int(item["tests"]),
            "severity": str(item["severity"]),
        } for item in analytics.identify_emerging_resistance(subset, subset)])
        if not emerging.empty:
            shown_emerging, emerging_suppression = suppress(
                emerging, ["observations"], threshold,
                blank=["resistancePercent"])
        else:
            shown_emerging, emerging_suppression = emerging, None

        # The forecast, and the monthly series it was fitted to. A projection
        # with no history behind it reads as a measurement.
        forecast = analytics.forecast_resistance_trend(subset, periods=6)
        history: List[Dict[str, object]] = []
        dated = subset[subset["collection_datetime"].notna()].copy()
        if not dated.empty:
            stamps = dated["collection_datetime"]
            if getattr(stamps.dtype, "tz", None) is not None:
                stamps = stamps.dt.tz_localize(None)
            dated["period"] = stamps.dt.to_period("M").astype(str)
            for period, group in dated.groupby("period"):
                count = int(len(group))
                history.append({
                    "period": str(period),
                    "observations": count,
                    "resistancePercent": _resistance_rate(group)
                    if count >= sv.MIN_ISOLATES_FOR_REPORTING else None,
                })
            history.sort(key=lambda point: str(point["period"]))

        organism_comparison = analytics.compare_organisms(subset)
        if not organism_comparison.empty:
            organism_comparison = organism_comparison.reset_index()
            for letter in ("R", "I", "S"):
                if letter not in organism_comparison.columns:
                    organism_comparison[letter] = 0
            organism_comparison = organism_comparison.rename(columns={
                "R": "resistant", "I": "intermediate", "S": "susceptible",
                "total": "observations", "resistance_rate": "resistancePercent",
            })[["organism", "resistant", "intermediate", "susceptible",
                "observations", "resistancePercent"]]
            shown_organisms, organism_suppression = suppress(
                organism_comparison,
                ["resistant", "intermediate", "susceptible", "observations"],
                threshold, blank=["resistancePercent"])
        else:
            shown_organisms, organism_suppression = pd.DataFrame(), None

        antibiotic_comparison = analytics.compare_antibiotics(subset)
        if not antibiotic_comparison.empty:
            antibiotic_comparison = antibiotic_comparison.reset_index()
            for letter in ("R", "I", "S"):
                if letter not in antibiotic_comparison.columns:
                    antibiotic_comparison[letter] = 0
            antibiotic_comparison = antibiotic_comparison.rename(columns={
                "R": "resistant", "I": "intermediate", "S": "susceptible",
                "total": "observations", "resistance_rate": "resistancePercent",
                "susceptibility_rate": "susceptibilityPercent",
            })[["antibiotic", "resistant", "intermediate", "susceptible",
                "observations", "resistancePercent", "susceptibilityPercent"]]
            shown_antibiotics, antibiotic_suppression = suppress(
                antibiotic_comparison,
                ["resistant", "intermediate", "susceptible", "observations"],
                threshold,
                blank=["resistancePercent", "susceptibilityPercent"])
        else:
            shown_antibiotics, antibiotic_suppression = pd.DataFrame(), None

        summary = pd.DataFrame([{
            "organism": str(row["organism"]),
            "antibiotic": str(row["antibiotic"]),
            "tested": int(row["tested"]),
            "susceptible": int(row["susceptible"]),
            "susceptibilityPercent": float(row["susceptibility_rate"]),
            "ciLow": float(row["ci_low"]),
            "ciHigh": float(row["ci_high"]),
            "observation": str(row["observation"]),
            "meetsThreshold": bool(row["meets_reporting_threshold"]),
        } for row in analytics.summarise_susceptibility(subset)])
        if not summary.empty:
            reportable = int(summary["meetsThreshold"].sum())
            shown_summary, summary_suppression = suppress(
                summary, ["tested", "susceptible"], threshold,
                blank=["susceptibilityPercent", "ciLow", "ciHigh",
                       "observation"])
        else:
            reportable = 0
            shown_summary, summary_suppression = summary, None

        slices.append({
            "sector": sector,
            "colour": _colour(sector),
            "statistics": {
                "observations": int(statistics.get("total_tests") or 0),
                "resistant": int(statistics.get("resistant_count") or 0),
                "intermediate": int(statistics.get("intermediate_count") or 0),
                "susceptible": int(statistics.get("susceptible_count") or 0),
                "resistancePercent": statistics.get("resistance_rate"),
                "intermediatePercent": statistics.get("intermediate_rate"),
                "susceptiblePercent": statistics.get("susceptible_rate"),
                "organisms": int(subset["organism"].nunique()),
                "antibiotics": int(subset["antibiotic"].nunique()),
                "isolates": int(subset["isolate_id"].nunique()),
            },
            "trend": {
                "direction": str(trend.get("trend") or "insufficient_data"),
                "firstHalfPercent": trend.get("first_half_resistance"),
                "secondHalfPercent": trend.get("second_half_resistance"),
                "changePoints": trend.get("change_percentage"),
                "band": trend.get("risk_level"),
            },
            "scores": {"rows": rows(shown_scores),
                       "suppression": score_suppression},
            "burden": {
                "observations": int(len(subset)),
                "resistantObservations": int((subset["result"] == "R").sum()),
                "resistancePercent": _resistance_rate(subset),
                "band": impact,
                "rows": rows(shown_burden),
                "suppression": burden_suppression,
            },
            "emerging": {"rows": rows(shown_emerging),
                         "suppression": emerging_suppression,
                         "windowDays": 90},
            "forecast": {
                "points": [{"monthsAhead": int(point["months_ahead"]),
                            "percent": float(
                                point["predicted_resistance_rate"])}
                           for point in forecast.get("forecasts", [])],
                "history": history,
                "slope": forecast.get("trend_slope"),
                "confidence": forecast.get("confidence"),
                "error": forecast.get("error"),
            },
            "organismComparison": {"rows": rows(shown_organisms),
                                   "suppression": organism_suppression},
            "antibioticComparison": {"rows": rows(shown_antibiotics),
                                     "suppression": antibiotic_suppression},
            "susceptibilitySummary": {
                "rows": rows(shown_summary),
                "suppression": summary_suppression,
                "pairs": int(len(summary)),
                "reportable": reportable,
                "provisional": int(len(summary)) - reportable,
            },
        })

    return {"slices": slices,
            "scoringRule": _RISK_SCORING_RULE,
            "minIsolates": analytics.SURVEILLANCE_MIN_ISOLATES}


__all__ = ["export_mechanisms", "export_hai", "export_quality",
           "export_comparison", "export_risk"]
