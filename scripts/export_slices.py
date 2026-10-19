"""
Filtered views, pre-computed.

The site is static, so a filter cannot re-run the analysis. Either the
combination was computed here or it cannot be shown, and that is the trade the
architecture makes: the figures a visitor can reach are the figures somebody
decided to publish.

So every filter the interface offers has a file behind it. One secondary
dimension at a time -- sector and region, or sector and period, not all three
-- because the cross-product of sector, region, laboratory and period is
several thousand tables of which almost all would be empty.

**Most of them are empty, and that is the finding.** A regional antibiogram in
this collection reaches the thirty-isolate floor for nought to eight
organism-antibiotic pairs out of roughly a hundred and ten. The filter is still
offered, because "this region cannot yet support a published rate" is worth
knowing and is invisible if the control is simply left off the page. The slice
carries the counts that say so.

Each slice holds only the rows that passed, so a region with nothing
publishable is a file of a few hundred bytes rather than a hundred withheld
rows. The strata breakdowns stay on the default sector slice: they are a second
question, and repeating them under every filter value would multiply the
published bytes for views nobody asked for.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional

import pandas as pd

from src import palette
from src import surveillance as sv

#: How many isolates a slice needs before it is written at all. Below this
#: there is nothing to say beyond "too few", which the manifest already
#: records, and the file would be noise in the repository.
MIN_SLICE_ISOLATES = 20


def slug(*parts: str) -> str:
    """A filename for a slice. Stable, lower case, no surprises on Windows.

    Each part is cleaned before the parts are joined, so the ``__`` separator
    survives. Cleaning the joined string instead collapsed the separator into a
    single dash, and a value containing a space would then be indistinguishable
    from a part boundary -- a laboratory called "region accra" and the region
    "accra" would land on the same file.
    """
    cleaned = []
    for part in parts:
        text = re.sub(r"[^a-z0-9]+", "-", str(part).strip().lower()).strip("-")
        if text:
            cleaned.append(text)
    return "__".join(cleaned) or "all"


def _year(frame: pd.DataFrame) -> pd.Series:
    stamps = frame["collection_datetime"]
    if getattr(stamps.dtype, "tz", None) is not None:
        stamps = stamps.dt.tz_localize(None)
    return stamps.dt.year


def dimensions(frame: pd.DataFrame) -> List[Dict[str, object]]:
    """The secondary dimensions offered, and the values each can take."""
    years = sorted({int(y) for y in _year(frame).dropna().unique()})
    return [
        {
            "key": "period",
            "label": "Period",
            "values": [str(y) for y in years],
            "note": "Deduplicated within the year, following CLSI M39.",
        },
        {
            "key": "region",
            "label": "Region",
            "values": sorted({str(r) for r in frame["region"].dropna().unique()}),
            "note": "A single region rarely holds enough isolates for a "
                    "published percentage. The counts are shown either way.",
        },
        {
            "key": "lab_name",
            "label": "Laboratory",
            "values": sorted({str(l) for l in frame["lab_name"].dropna().unique()}),
            "note": "Laboratories are named deliberately: attribution is the "
                    "point of sentinel surveillance.",
        },
    ]


def _subset(frame: pd.DataFrame, key: str, value: str) -> pd.DataFrame:
    if key == "period":
        return frame[_year(frame).astype("Int64").astype(str) == str(value)]
    return frame[frame[key].astype(str) == str(value)]


def export_resistance_slices(frame: pd.DataFrame, out_dir: str, threshold: int,
                             rows: Callable, suppress: Callable
                             ) -> Dict[str, object]:
    """One antibiogram per sector-and-filter combination."""
    directory = os.path.join(out_dir, "slices", "resistance")
    os.makedirs(directory, exist_ok=True)

    available: Dict[str, Dict[str, object]] = {}
    written = 0
    skipped = 0

    for sector in sorted(frame["sector"].dropna().unique()):
        sector_frame = frame[frame["sector"] == sector]
        for dimension in dimensions(sector_frame):
            key = dimension["key"]
            for value in dimension["values"]:
                subset = _subset(sector_frame, key, value)
                isolates = int(subset["isolate_id"].nunique()) if not subset.empty else 0
                if isolates < MIN_SLICE_ISOLATES:
                    skipped += 1
                    continue

                table, provenance = sv.cumulative_antibiogram(
                    subset, period_months=None)
                if table.empty:
                    skipped += 1
                    continue
                reported = table[table["status"] == sv.STATUS_REPORTED]
                shown, suppression = suppress(
                    reported, ["tested"], threshold,
                    blank=["percent_susceptible", "ci_low", "ci_high"])

                name = slug(str(sector), key, str(value))
                payload = {
                    "sector": str(sector),
                    "dimension": key,
                    "value": str(value),
                    "colour": palette.SECTOR.get(str(sector), palette.GREY),
                    "isolates": isolates,
                    "pairsTotal": int(len(table)),
                    "pairsReported": int(len(reported)),
                    "pairsSuppressed": int(
                        (table["status"] == sv.STATUS_SUPPRESSED).sum()),
                    "rows": rows(shown),
                    "suppression": suppression,
                    "method": {
                        "deduplication": str(
                            provenance.get("deduplication_summary", "")),
                        "qcExcluded": int(
                            provenance.get("qc_failures_excluded", 0) or 0),
                        "minIsolates": sv.MIN_ISOLATES_FOR_REPORTING,
                    },
                }
                with open(os.path.join(directory, f"{name}.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False,
                              allow_nan=False, separators=(",", ":"))
                written += 1
                available.setdefault(str(sector), {}).setdefault(key, []).append({
                    "value": str(value),
                    "slug": name,
                    "isolates": isolates,
                    "pairsReported": int(len(reported)),
                })

    return {
        "dimensions": [{k: v for k, v in d.items() if k != "values"}
                       for d in dimensions(frame)],
        "available": available,
        "written": written,
        "skipped": skipped,
        "minSliceIsolates": MIN_SLICE_ISOLATES,
    }


def export_organism_slices(frame: pd.DataFrame, out_dir: str, threshold: int,
                           rows: Callable, suppress: Callable
                           ) -> Dict[str, object]:
    """Organism counts per sector-and-filter combination.

    Counts survive filtering where percentages do not: a region holding 150
    isolates cannot support a rate but can perfectly well report which
    organisms those 150 were.
    """
    directory = os.path.join(out_dir, "slices", "organisms")
    os.makedirs(directory, exist_ok=True)

    available: Dict[str, Dict[str, object]] = {}
    written = 0

    groups = [("all", frame)] + [
        (str(sector), frame[frame["sector"] == sector])
        for sector in sorted(frame["sector"].dropna().unique())]

    for name, sector_frame in groups:
        if sector_frame.empty:
            continue
        for dimension in dimensions(sector_frame):
            key = dimension["key"]
            for value in dimension["values"]:
                subset = _subset(sector_frame, key, value)
                if subset.empty:
                    continue
                deduplicated, _ = sv.select_first_isolates(
                    subset, period_months=None)
                if deduplicated.empty:
                    continue
                distribution = sv.pathogen_distribution(
                    deduplicated, allow_cross_sector=True)
                if distribution.empty:
                    continue
                isolates = int(distribution["isolates"].sum())
                if isolates < MIN_SLICE_ISOLATES:
                    continue

                shown, suppression = suppress(
                    distribution, ["isolates"], threshold, blank=["percent"])
                by_type = (deduplicated
                           .drop_duplicates(["dataset_id", "isolate_id"])
                           .groupby("specimen_type", dropna=False)
                           .size().reset_index(name="isolates")
                           .sort_values("isolates", ascending=False))
                by_type["specimen_type"] = by_type["specimen_type"].fillna(
                    "Not recorded")
                shown_types, type_suppression = suppress(
                    by_type, ["isolates"], threshold)
                sterile = sv.sterile_site_share(deduplicated)

                file_slug = slug(name, key, str(value))
                payload = {
                    "sector": name,
                    "dimension": key,
                    "value": str(value),
                    "colour": palette.SECTOR.get(name, palette.BLUE),
                    "organisms": int(len(distribution)),
                    "isolates": isolates,
                    "laboratories": int(subset["lab_name"].nunique()),
                    "rows": rows(shown),
                    "suppression": suppression,
                    "specimenTypes": rows(shown_types.rename(
                        columns={"specimen_type": "specimenType"})),
                    "specimenTypeSuppression": type_suppression,
                    "sterileSitePercent": (
                        float(sterile["percent"])
                        if sterile.get("percent") is not None else None),
                }
                with open(os.path.join(directory, f"{file_slug}.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False,
                              allow_nan=False, separators=(",", ":"))
                written += 1
                available.setdefault(name, {}).setdefault(key, []).append({
                    "value": str(value),
                    "slug": file_slug,
                    "isolates": isolates,
                })

    return {
        "dimensions": [{k: v for k, v in d.items() if k != "values"}
                       for d in dimensions(frame)],
        "available": available,
        "written": written,
    }


__all__ = ["export_resistance_slices", "export_organism_slices",
           "dimensions", "slug", "MIN_SLICE_ISOLATES"]
