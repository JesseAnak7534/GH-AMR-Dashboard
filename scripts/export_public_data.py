"""
Export the public figures as JSON for the web front end.

The React site does not query the database. It reads the files this script
writes, and that is a deliberate choice rather than a shortcut.

**Disclosure control runs before anything leaves the machine.** Every figure
here has already been through ``src.disclosure``, so the published files
physically cannot contain a cell resting on fewer records than the threshold. A
live public API would have to get that right on every request, for every
combination of filters a visitor can invent, forever; a snapshot has to get it
right once, here, where it can be tested. The risk on a public surveillance
page was never the headline figures -- it is a visitor narrowing by sector,
region, laboratory and organism until a cell holds one person. Pre-computing
the publishable slices removes the ability to narrow that far.

**The analysis stays in Python.** ``src/surveillance.py``, ``src/genomics.py``
and ``src/consumption.py`` are the asset: deduplication to CLSI M39, Wilson
intervals, the thirty-isolate floor, pooled rather than averaged rates, the
refusal to mix sectors. Re-implementing any of that in TypeScript would mean
two definitions of every number and no way to tell which one is on screen.

**No credentials in the web tier.** The site is static files. There is no
database reachable from it, no API to authenticate, and nothing to leak.

What the front end does provide is the interactivity: switching sector,
sorting, searching and filtering within rows that have *already* been
published. That is safe, because no narrowing a reader performs in the browser
can reveal a cell this script did not decide to publish.

Usage::

    python scripts/export_public_data.py
    python scripts/export_public_data.py --out web/public/data --threshold 5
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import export_sections as sections  # noqa: E402
from src import consumption, db, disclosure, genomics as gx, palette  # noqa: E402
from src import surveillance as sv  # noqa: E402

DEFAULT_OUT = os.path.join("web", "public", "data")

#: Strata offered on the resistance page. Each is pre-computed and suppressed;
#: the front end switches between them rather than composing its own.
STRATA = [
    ("specimen_type", "Specimen type"),
    ("ward_type_at_collection", "Ward type"),
    ("age_band_at_collection", "Age band"),
    ("patient_type", "Patient type"),
    ("region", "Region"),
    ("sex", "Sex"),
    ("sampling_purpose", "Sampling purpose"),
]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _clean(value):
    """One value, as JSON can carry it.

    NaN is the important case. ``json.dumps`` writes it as the literal ``NaN``,
    which is not JSON and which ``JSON.parse`` rejects, so a single missing
    confidence interval would break a whole page. It becomes null, and the
    front end draws "not reported" rather than a zero.
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if hasattr(value, "item"):                        # numpy scalar
        try:
            return _clean(value.item())
        except Exception:                             # noqa: BLE001
            return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _rows(frame: pd.DataFrame, rename: Optional[Dict[str, str]] = None
          ) -> List[Dict[str, object]]:
    """A frame as a list of records, with camelCase keys for the front end."""
    if frame is None or frame.empty:
        return []
    out = frame.rename(columns=rename) if rename else frame
    return [{str(k): _clean(v) for k, v in record.items()}
            for record in out.to_dict(orient="records")]


def _write(directory: str, name: str, payload) -> str:
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1,
                  allow_nan=False)
    size = os.path.getsize(path)
    print(f"  {name:<22} {size / 1024:7.1f} KB")
    return path


def _suppress(frame: pd.DataFrame, counts: List[str], threshold: int,
              *, group_by: Optional[str] = None,
              blank: Optional[List[str]] = None):
    shown, report = disclosure.apply_disclosure_control(
        frame, counts, threshold=threshold, group_by=group_by,
        also_blank=blank)
    return shown, {"withheld": report.withheld, "primary": report.primary,
                   "secondary": report.secondary,
                   "cellsTotal": report.cells_total,
                   "threshold": report.threshold,
                   "summary": report.summary}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def export_resistance(frame: pd.DataFrame, threshold: int) -> Dict[str, object]:
    """The antibiogram, one slice per sector.

    Per sector rather than pooled, because the platform refuses to divide one
    numerator by a denominator mixing hospital isolates with river water. The
    front end lets the reader switch slices; it cannot construct one.
    """
    slices = []
    for sector in sorted(frame["sector"].dropna().unique()):
        subset = frame[frame["sector"] == sector]
        table, provenance = sv.cumulative_antibiogram(subset,
                                                      period_months=None)
        if table.empty:
            continue
        reported = table[table["status"] == sv.STATUS_REPORTED]
        shown, suppression = _suppress(
            reported, ["tested"], threshold,
            blank=["percent_susceptible", "ci_low", "ci_high"])

        strata = []
        for column, label in STRATA:
            if column not in subset.columns:
                continue
            stratified = sv.stratified_resistance(subset, by=column)
            if stratified.empty:
                continue
            shown_stratum, stratum_suppression = _suppress(
                stratified, ["isolates"], threshold,
                blank=["percent_non_susceptible", "ci_low", "ci_high"])
            strata.append({
                "key": column, "label": label,
                "rows": _rows(shown_stratum.rename(columns={column: "stratum"})),
                "suppression": stratum_suppression,
            })

        slices.append({
            "sector": str(sector),
            "colour": palette.SECTOR.get(str(sector), palette.GREY),
            "isolates": int(subset["isolate_id"].nunique()),
            "pairsTotal": int(len(table)),
            "pairsReported": int(len(reported)),
            "pairsSuppressed": int((table["status"] == sv.STATUS_SUPPRESSED).sum()),
            "rows": _rows(shown),
            "suppression": suppression,
            "strata": strata,
            "method": {
                "deduplication": str(provenance.get("deduplication_summary", "")),
                "qcExcluded": int(provenance.get("qc_failures_excluded", 0) or 0),
                "minIsolates": sv.MIN_ISOLATES_FOR_REPORTING,
            },
        })
    return {"slices": slices,
            "minIsolatesForReporting": sv.MIN_ISOLATES_FOR_REPORTING}


def export_organisms(frame: pd.DataFrame, threshold: int) -> Dict[str, object]:
    """Organism counts, overall and per sector.

    Counting is safe to pool in a way that rating is not: an isolate counted in
    the animal sector and one counted in the human sector add up to two
    isolates, whereas their susceptibility percentages do not average into
    anything.
    """
    deduplicated, dedup = sv.select_first_isolates(frame, period_months=None)
    slices = []
    groups = [("all", deduplicated)] + [
        (str(sector), deduplicated[deduplicated["sector"] == sector])
        for sector in sorted(deduplicated["sector"].dropna().unique())]

    for name, subset in groups:
        if subset.empty:
            continue
        distribution = sv.pathogen_distribution(subset, allow_cross_sector=True)
        if distribution.empty:
            continue
        shown, suppression = _suppress(distribution, ["isolates"], threshold,
                                       blank=["percent"])
        by_type = (subset.drop_duplicates(["dataset_id", "isolate_id"])
                   .groupby("specimen_type", dropna=False)
                   .size().reset_index(name="isolates")
                   .sort_values("isolates", ascending=False))
        by_type["specimen_type"] = by_type["specimen_type"].fillna("Not recorded")
        shown_types, type_suppression = _suppress(by_type, ["isolates"],
                                                  threshold)
        sterile = sv.sterile_site_share(subset)
        slices.append({
            "sector": name,
            "colour": palette.SECTOR.get(name, palette.BLUE),
            "organisms": int(len(distribution)),
            "isolates": int(distribution["isolates"].sum()),
            "laboratories": int(subset["lab_name"].nunique()),
            "rows": _rows(shown),
            "suppression": suppression,
            "specimenTypes": _rows(shown_types.rename(
                columns={"specimen_type": "specimenType"})),
            "specimenTypeSuppression": type_suppression,
            "sterileSitePercent": _clean(sterile.get("percent")),
        })
    return {"slices": slices, "deduplication": dedup.summary}


def export_one_health(frame: pd.DataFrame, threshold: int) -> Dict[str, object]:
    deduplicated, dedup = sv.select_first_isolates(frame, period_months=None)
    isolates = deduplicated.drop_duplicates(["dataset_id", "isolate_id"])

    by_sector = (isolates.groupby("sector", dropna=False)
                 .size().reset_index(name="isolates")
                 .sort_values("isolates", ascending=False))
    shown_sector, sector_suppression = _suppress(by_sector, ["isolates"],
                                                 threshold)
    shown_sector["colour"] = shown_sector["sector"].map(
        lambda s: palette.SECTOR.get(str(s), palette.GREY))

    cross = (isolates.groupby(["organism", "sector"], dropna=False)
             .size().reset_index(name="isolates"))
    per_organism = cross.groupby("organism")["sector"].nunique()
    shared = per_organism[per_organism > 1].index.tolist()
    shown_cross, cross_suppression = _suppress(
        cross[cross["organism"].isin(shared)], ["isolates"], threshold,
        group_by="organism")

    return {
        "sectors": _rows(shown_sector),
        "sectorSuppression": sector_suppression,
        "sharedOrganisms": _rows(shown_cross),
        "sharedSuppression": cross_suppression,
        "organismsTotal": int(isolates["organism"].nunique()),
        "organismsShared": int(len(shared)),
        "isolates": int(len(isolates)),
        "sectorsPresent": sorted(str(s) for s in
                                 isolates["sector"].dropna().unique()),
        "deduplication": dedup.summary,
        "palette": {k: v for k, v in palette.SECTOR.items()},
    }


def export_genomics(threshold: int, total_isolates: Optional[int]
                    ) -> Dict[str, object]:
    genomic = gx.load_genomic_frame()
    if genomic.empty:
        return {"sequenced": 0, "determinants": [], "concordance": None,
                "clusters": []}

    coverage = gx.sequencing_coverage(genomic, total_isolates=total_isolates)
    frequency = gx.determinant_frequency(genomic)
    shown_frequency, frequency_suppression = _suppress(
        frequency, ["isolates"], threshold, blank=["percent"])

    concordance_payload = None
    try:
        table = gx.concordance(genomic)
    except Exception:                                 # noqa: BLE001
        table = pd.DataFrame()
    if not table.empty:
        summary = gx.concordance_summary(table)
        verdicts = (table["verdict"].value_counts()
                    .rename_axis("verdict").reset_index(name="pairs"))
        agents = (table.groupby("antibiotic").size()
                  .reset_index(name="pairs")
                  .sort_values("pairs", ascending=False))
        shown_agents, agent_suppression = _suppress(agents, ["pairs"],
                                                    threshold)
        concordance_payload = {
            "summary": {k: _clean(v) for k, v in summary.items()},
            "verdicts": _rows(verdicts),
            "agents": _rows(shown_agents),
            "agentSuppression": agent_suppression,
        }

    # A cluster below the threshold is dropped whole, not listed with its size
    # withheld: the row -- organism, sector, sequence type, laboratories
    # spanned -- describes those few specimens whether or not the count is on
    # it, so the count was never the disclosive part.
    cluster_report = gx.clusters(genomic)
    cluster_table = cluster_report.clusters
    publishable = (cluster_table[cluster_table["isolates"] >= threshold]
                   if not cluster_table.empty else pd.DataFrame())
    held_back = (len(cluster_table) - len(publishable)
                 if not cluster_table.empty else 0)

    return {
        "coverage": {k: _clean(v) for k, v in coverage.items()},
        "determinants": _rows(shown_frequency),
        "determinantSuppression": frequency_suppression,
        "concordance": concordance_payload,
        "clusters": _rows(publishable),
        "clustersTotal": int(len(cluster_table)) if not cluster_table.empty else 0,
        "clustersWithheld": int(held_back),
        "clustersUnassigned": int(getattr(cluster_report, "unclustered", 0)),
        "clusterMethods": list(getattr(cluster_report, "methods", []) or []),
        "clusterSummary": cluster_report.summary,
        "verdictLabels": {
            "explained": gx.CONCORDANT_RESISTANT,
            "susceptibleNoGene": gx.CONCORDANT_SUSCEPTIBLE,
            "geneNotExpressed": gx.GENOTYPE_ONLY,
            "unexplained": gx.PHENOTYPE_ONLY,
        },
    }


def export_use(threshold: int) -> Dict[str, object]:
    amu = db.get_amu_records()
    amc = db.get_amc_records()
    surveys = db.get_pps_surveys()
    prescriptions = db.get_pps_prescriptions()

    def pooled(rate, by: str, value: str):
        table = getattr(rate, "table", None)
        if table is None or table.empty:
            return None
        shown, suppression = _suppress(table, ["records"], threshold,
                                       blank=[value])
        return {"by": by, "rows": _rows(shown.rename(columns={by: "group"})),
                "suppression": suppression, "caveat": rate.caveat}

    amu_blocks = []
    if amu is not None and not amu.empty:
        # No split by facility. A facility-level consumption rate names the
        # hospital, and hospital identity is not published here.
        for column in ("region", "antibiotic_name", "report_period"):
            if column in amu.columns:
                block = pooled(consumption.pooled_ddd(amu, by=column), column,
                               "ddd_per_1000_patient_days")
                if block:
                    amu_blocks.append(block)

    amc_blocks = []
    if amc is not None and not amc.empty:
        for column in ("species", "region", "antibiotic_class"):
            if column in amc.columns:
                block = pooled(consumption.pooled_mg_per_kg(amc, by=column),
                               column, "mg_per_kg_biomass")
                if block:
                    amc_blocks.append(block)

    pps: Dict[str, object] = {"surveys": 0}
    if surveys is not None and not surveys.empty:
        patients = pd.to_numeric(surveys.get("total_patients"), errors="coerce")
        on_antibiotics = pd.to_numeric(surveys.get("patients_on_antibiotics"),
                                       errors="coerce")
        usable = patients.notna() & on_antibiotics.notna() & (patients > 0)
        total = float(patients[usable].sum()) if usable.any() else 0.0
        treated = float(on_antibiotics[usable].sum()) if usable.any() else 0.0
        pps = {
            "surveys": int(len(surveys)),
            "patients": int(total),
            "onAntibiotics": int(treated),
            "prevalencePercent": (round(100.0 * treated / total, 1)
                                  if total > 0 else None),
            "breakdowns": [],
        }
        if prescriptions is not None and not prescriptions.empty:
            for column, label in (("indication", "Indication"),
                                  ("route", "Route"),
                                  ("antibiotic_name", "Agent"),
                                  ("patient_age_group", "Age group")):
                if column not in prescriptions.columns:
                    continue
                counts = (prescriptions.groupby(column, dropna=False)
                          .size().reset_index(name="prescriptions")
                          .sort_values("prescriptions", ascending=False))
                counts[column] = counts[column].fillna("Not recorded")
                shown, suppression = _suppress(counts, ["prescriptions"],
                                               threshold)
                pps["breakdowns"].append({
                    "key": column, "label": label,
                    "rows": _rows(shown.rename(columns={column: "value"})),
                    "suppression": suppression,
                })
            documented = pd.to_numeric(
                prescriptions.get("indication_documented"),
                errors="coerce").fillna(0)
            pps["indicationDocumentedPercent"] = (
                round(100.0 * float(documented.gt(0).mean()), 1)
                if len(documented) else None)
            pps["prescriptions"] = int(len(prescriptions))

    return {"amu": amu_blocks, "amc": amc_blocks, "pps": pps}


def export_about(frame: pd.DataFrame) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "minIsolatesForReporting": sv.MIN_ISOLATES_FOR_REPORTING,
        "minPublicCell": disclosure.MIN_PUBLIC_CELL,
        "withheldLabel": disclosure.WITHHELD,
    }
    try:
        report = sv.coverage_report()
        completeness = getattr(report, "completeness", None)
        if completeness is not None and not completeness.empty:
            # The internal column name stays behind. A public reader needs the
            # field, its scope and how complete it is; naming the database
            # column it lives in tells them nothing and publishes the schema.
            completeness = completeness.drop(columns=["Column"],
                                             errors="ignore")
        payload["completeness"] = _rows(completeness)
    except Exception as error:                        # noqa: BLE001
        payload["completeness"] = []
        payload["completenessError"] = str(error)
    try:
        payload["metrics"] = _rows(sv.metric_dictionary_frame())
    except Exception:                                 # noqa: BLE001
        payload["metrics"] = []
    if not frame.empty:
        deduplicated, dedup = sv.select_first_isolates(frame,
                                                       period_months=None)
        payload["deduplication"] = dedup.summary
    return payload


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _priority_lookup() -> Dict[str, object]:
    """The WHO and Ghana priority pathogen lists, if the lookup is present."""
    path = os.path.join("data", "lookups", "priority_pathogens.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:                                 # noqa: BLE001
        return {}


def _use_record_total() -> int:
    """Consumption and prescribing records, counted together.

    A reader looking at the landing page does not care which table a record
    landed in, so AMU, AMC and the point-prevalence surveys are summed into one
    figure for the card.
    """
    total = 0
    for loader in (db.get_amu_records, db.get_amc_records, db.get_pps_surveys):
        try:
            frame = loader()
        except Exception:                             # noqa: BLE001
            continue
        if frame is not None and not frame.empty:
            total += int(len(frame))
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"output directory (default: {DEFAULT_OUT})")
    parser.add_argument("--threshold", type=int,
                        default=disclosure.MIN_PUBLIC_CELL,
                        help="smallest publishable cell; may be raised, never "
                             "lowered")
    args = parser.parse_args()

    threshold = max(int(args.threshold), disclosure.MIN_PUBLIC_CELL)
    if threshold != args.threshold:
        print(f"Threshold raised to the floor of {threshold}: the minimum "
              "publishable cell cannot be lowered.")

    os.makedirs(args.out, exist_ok=True)
    print(f"Exporting public figures to {args.out} "
          f"(minimum cell {threshold})\n")

    frame = sv.load_surveillance_frame()
    if frame.empty:
        print("No surveillance data found. Nothing to publish.")
        return 1

    total_isolates = int(frame["isolate_id"].nunique())
    collected = frame["collection_datetime"].dropna()

    _write(args.out, "resistance.json", export_resistance(frame, threshold))
    _write(args.out, "organisms.json", export_organisms(frame, threshold))
    _write(args.out, "one-health.json", export_one_health(frame, threshold))
    genomics = export_genomics(threshold, total_isolates)
    _write(args.out, "genomics.json", genomics)
    use = export_use(threshold)
    _write(args.out, "use.json", use)
    _write(args.out, "about.json", export_about(frame))

    _write(args.out, "trends.json",
           sections.export_trends(frame, threshold, _rows, _suppress))
    _write(args.out, "mdr.json",
           sections.export_mdr(frame, threshold, _rows, _suppress))
    _write(args.out, "regions.json",
           sections.export_regions(frame, threshold, _rows, _suppress))
    _write(args.out, "priority.json",
           sections.export_priority(frame, _priority_lookup(), threshold,
                                    _rows, _suppress))
    extras = sections.export_genomic_extras(threshold, _rows, _suppress)
    if extras:
        genomics.update(extras)
        _write(args.out, "genomics.json", genomics)

    # The landing page needs one figure per section and should not have to read
    # every section file to find them, so they are repeated in the manifest.
    genome_count = int((genomics.get("coverage") or {}).get("sequenced") or 0)
    use_records = _use_record_total()

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "minIsolatesForReporting": sv.MIN_ISOLATES_FOR_REPORTING,
        "counts": {
            "genomes": genome_count,
            "useRecords": use_records,
            "specimens": int(frame["specimen_id"].nunique()),
            "isolates": total_isolates,
            "results": int(len(frame)),
            "organisms": int(frame["organism"].nunique()),
            "laboratories": int(frame["lab_name"].nunique()),
            "sectors": int(frame["sector"].nunique()),
            "regions": int(frame["region"].nunique()),
        },
        "period": {
            "first": _clean(collected.min()) if not collected.empty else None,
            "last": _clean(collected.max()) if not collected.empty else None,
        },
        "sectors": sorted(str(s) for s in frame["sector"].dropna().unique()),
        "laboratories": sorted(str(l) for l in
                               frame["lab_name"].dropna().unique()),
        "palette": {
            "sector": dict(palette.SECTOR),
            "sequence": list(palette.SEQUENCE),
            "result": dict(palette.RESULT),
            "missing": palette.MISSING,
        },
    }
    _write(args.out, "manifest.json", manifest)

    print("\nEvery figure above passed disclosure control before it was "
          "written. No record-level row is included in any file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
