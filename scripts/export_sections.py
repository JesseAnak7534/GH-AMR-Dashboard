"""
The sections added after the first public release: trends, MDR, geography and
the priority-pathogen lens.

Kept beside ``export_public_data.py`` rather than inside it because each of
these needs a decision the others do not, and burying those decisions in one
long module makes them invisible.

**Trends deduplicate inside each period, not across the series.** CLSI M39 says
first isolate per patient per organism per period. Deduplicating across the
whole series instead would drop a patient's second isolate a year later, which
is not a repeat -- it is next year's data point, and dropping it bends the
trend.

**MDR is only counted where enough agent categories were tested.** Magiorakos
defines multidrug resistance as non-susceptibility in three or more categories,
which is unanswerable on an isolate tested against two. Those isolates are
reported as "insufficient testing" rather than as "not MDR", because calling
them not-MDR would make a laboratory with a small panel look like one with
little resistance.

**Regions are symbols, not shading.** Every specimen in the platform has a
region and none has usable coordinates, and the repository holds no boundary
polygons. A choropleth would need boundaries this platform does not have, so
each region is drawn at its centroid, sized by isolates. A circle at a centroid
claims less than a shaded district.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from src import disclosure, genomics as gx, mdr, palette
from src import surveillance as sv
from src.ghana_map import GHANA_REGIONS

#: Quarters rather than months. Thirty-one months of data split by month gives
#: points resting on a few dozen observations each, where the interval is wider
#: than the movement being read into it.
PERIOD_FREQ = "Q"

#: A period is only drawn if it holds at least this many observations. Below
#: it, the point is noise and a reader will still draw a line through it.
MIN_PERIOD_OBSERVATIONS = 30


def _periodise(frame: pd.DataFrame, freq: str = PERIOD_FREQ) -> pd.DataFrame:
    """Add a period label, and deduplicate within each period separately."""
    if frame.empty or "collection_datetime" not in frame.columns:
        return pd.DataFrame()

    working = frame[frame["collection_datetime"].notna()].copy()
    if working.empty:
        return pd.DataFrame()

    stamps = working["collection_datetime"]
    if getattr(stamps.dtype, "tz", None) is not None:
        stamps = stamps.dt.tz_localize(None)
    working["period"] = stamps.dt.to_period(freq).astype(str)

    chunks: List[pd.DataFrame] = []
    for _, chunk in working.groupby("period", dropna=True):
        deduplicated, _ = sv.select_first_isolates(chunk, period_months=None)
        if not deduplicated.empty:
            chunks.append(deduplicated)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def export_trends(frame: pd.DataFrame, threshold: int, rows, suppress
                  ) -> Dict[str, object]:
    """Non-susceptibility over time, per sector and for the leading pairs."""
    slices = []
    for sector in sorted(frame["sector"].dropna().unique()):
        subset = frame[frame["sector"] == sector]
        periodised = _periodise(subset)
        if periodised.empty:
            continue

        overall = sv.stratified_resistance(
            periodised, by="period", deduplicate=False,
            min_observations=MIN_PERIOD_OBSERVATIONS,
            allow_cross_sector=True)
        if overall.empty:
            continue
        overall = overall.sort_values("period")
        shown, suppression = suppress(
            overall, ["isolates"], threshold,
            blank=["percent_non_susceptible", "ci_low", "ci_high"])

        # The pairs worth following: the most-tested combinations in this
        # sector, so the series are the ones with enough data to mean anything.
        counts = (periodised.groupby(["organism", "antibiotic"])
                  .size().reset_index(name="observations")
                  .sort_values("observations", ascending=False)
                  .head(8))
        series = []
        for _, pair in counts.iterrows():
            table = sv.stratified_susceptibility(
                periodised, by="period", organism=pair["organism"],
                antibiotic=pair["antibiotic"], deduplicate=False,
                min_isolates=MIN_PERIOD_OBSERVATIONS,
                allow_cross_sector=True)
            if table.empty:
                continue
            table = table.sort_values("period")
            shown_pair, pair_suppression = suppress(
                table, ["tested"], threshold,
                blank=["percent_susceptible", "ci_low", "ci_high"])
            drawable = int(shown_pair["percent_susceptible"].notna().sum())
            if drawable < 2:
                continue                       # two points are not a trend
            series.append({
                "organism": str(pair["organism"]),
                "antibiotic": str(pair["antibiotic"]),
                "points": rows(shown_pair),
                "suppression": pair_suppression,
            })

        slices.append({
            "sector": str(sector),
            "colour": palette.SECTOR.get(str(sector), palette.GREY),
            "periods": rows(shown),
            "suppression": suppression,
            "series": series,
        })

    return {
        "slices": slices,
        "frequency": "quarter",
        "minObservations": MIN_PERIOD_OBSERVATIONS,
    }


def export_mdr(frame: pd.DataFrame, threshold: int, rows, suppress
               ) -> Dict[str, object]:
    """Multidrug resistance, to the Magiorakos definitions."""
    deduplicated, dedup = sv.select_first_isolates(frame, period_months=None)
    if deduplicated.empty:
        return {"isolates": 0, "slices": []}

    # One classification pass over everything, then split. Classifying each
    # sector separately would be the same work repeated, and an isolate's
    # classification does not depend on which slice it is being viewed in.
    classified = mdr.classify_frame(deduplicated)
    if classified.empty:
        return {"isolates": 0, "slices": []}

    # The classification already carries the organism it was made against, so
    # only the columns it lacks are joined on. Bringing organism across too
    # would collide with it, and the two must agree in any case.
    lookup = (deduplicated.drop_duplicates("isolate_id")
              .set_index("isolate_id")[["sector", "region"]])
    classified = classified.join(lookup, on="isolate_id")

    def block(subset: pd.DataFrame, name: str) -> Optional[Dict[str, object]]:
        if subset.empty:
            return None
        summary = mdr.summarise(subset)
        counts = (subset.groupby("classification", dropna=False)
                  .size().reset_index(name="isolates")
                  .sort_values("isolates", ascending=False))
        shown_counts, counts_suppression = suppress(counts, ["isolates"],
                                                    threshold)
        by_organism = (subset.groupby(["organism", "classification"],
                                      dropna=False)
                       .size().reset_index(name="isolates"))
        shown_organism, organism_suppression = suppress(
            by_organism, ["isolates"], threshold, group_by="organism")
        return {
            "name": name,
            "colour": palette.SECTOR.get(name, palette.GREY),
            "isolates": int(summary.get("isolates", 0)),
            "classifiable": int(summary.get("classifiable", 0)),
            "insufficient": int(summary.get("insufficient", 0)),
            "percent": {k: v for k, v in
                        (summary.get("percent_of_classifiable") or {}).items()},
            "counts": rows(shown_counts),
            "countsSuppression": counts_suppression,
            "byOrganism": rows(shown_organism),
            "byOrganismSuppression": organism_suppression,
        }

    slices = [b for b in
              [block(classified, "all")]
              + [block(classified[classified["sector"] == sector], str(sector))
                 for sector in sorted(classified["sector"].dropna().unique())]
              if b]

    return {
        "slices": slices,
        "deduplication": dedup.summary,
        "definitions": {
            "MDR": "Non-susceptible to at least one agent in three or more "
                   "antimicrobial categories.",
            "XDR": "Non-susceptible to at least one agent in all but two or "
                   "fewer categories.",
            "Insufficient testing": "Too few categories tested to answer the "
                                    "question. Not the same as not resistant.",
        },
    }


def export_regions(frame: pd.DataFrame, threshold: int, rows, suppress
                   ) -> Dict[str, object]:
    """Isolates and non-susceptibility by region, with centroids to plot."""
    deduplicated, dedup = sv.select_first_isolates(frame, period_months=None)
    if deduplicated.empty:
        return {"regions": [], "centroids": {}}

    resistance = sv.stratified_resistance(deduplicated, by="region",
                                          deduplicate=False,
                                          allow_cross_sector=True)
    isolates = deduplicated.drop_duplicates(["dataset_id", "isolate_id"])
    counts = (isolates.groupby("region", dropna=False)
              .agg(isolates=("isolate_id", "size"),
                   organisms=("organism", "nunique"),
                   laboratories=("lab_name", "nunique"))
              .reset_index())
    counts["region"] = counts["region"].fillna("Not recorded")

    merged = counts.merge(
        resistance.rename(columns={"region": "region"}), on="region",
        how="left", suffixes=("", "_strat"))
    merged = merged.sort_values("isolates", ascending=False)

    shown, suppression = suppress(
        merged, ["isolates"], threshold,
        blank=["percent_non_susceptible", "ci_low", "ci_high"])

    # Per-sector counts, so a reader can see which regions report from which
    # sectors rather than assuming every region reports all five.
    by_sector = (isolates.groupby(["region", "sector"], dropna=False)
                 .size().reset_index(name="isolates"))
    by_sector["region"] = by_sector["region"].fillna("Not recorded")
    shown_sector, sector_suppression = suppress(
        by_sector, ["isolates"], threshold, group_by="region")

    return {
        "regions": rows(shown),
        "suppression": suppression,
        "bySector": rows(shown_sector),
        "bySectorSuppression": sector_suppression,
        "centroids": {name: {"lat": lat, "lon": lon}
                      for name, (lat, lon) in GHANA_REGIONS.items()},
        "deduplication": dedup.summary,
        "palette": dict(palette.SECTOR),
    }


#: Genera the priority lists refer to collectively as *Enterobacterales*. The
#: lists name the order; the laboratory names the species, so without this the
#: most important entry on the WHO critical list would match nothing and the
#: page would report that carbapenem-resistant Enterobacterales are not under
#: surveillance, which is the opposite of the truth.
#:
#: Deliberately a short, explicit list rather than a taxonomy lookup: it covers
#: what this platform actually isolates, and a name it does not cover fails
#: visibly as "not matched" instead of silently mis-assigning an organism.
ENTEROBACTERALES = (
    "Escherichia", "Klebsiella", "Enterobacter", "Salmonella", "Shigella",
    "Proteus", "Serratia", "Citrobacter", "Morganella", "Providencia",
    "Yersinia", "Raoultella", "Hafnia", "Edwardsiella", "Cronobacter",
)


def _matches(listed: str, observed: str) -> bool:
    """Whether an isolated organism falls under a priority-list entry.

    Three shapes of entry, each matched on its own terms rather than by one
    loose prefix test:

    * a species -- "Escherichia coli" -- matches exactly;
    * a genus written "Campylobacter spp." matches any species in that genus;
    * an order -- "Enterobacterales" -- matches the genera listed above.
    """
    listed = listed.strip()
    observed = observed.strip()
    if not listed or not observed:
        return False
    if listed.lower() == observed.lower():
        return True
    if listed.lower() in ("enterobacterales", "enterobacteriaceae"):
        return observed.split(" ")[0] in ENTEROBACTERALES
    for suffix in (" spp.", " species", " sp."):
        if listed.lower().endswith(suffix):
            genus = listed[: -len(suffix)].strip()
            return observed.lower().startswith(genus.lower() + " ") \
                or observed.lower() == genus.lower()
    return False


def export_priority(frame: pd.DataFrame, lookup: Dict[str, object],
                    threshold: int, rows, suppress) -> Dict[str, object]:
    """The WHO and Ghana priority lists, matched against what is in the data.

    An organism on a priority list that the platform has never isolated is as
    much a finding as one it has: it says the surveillance is not seeing it,
    which is different from it not being there.
    """
    deduplicated, _ = sv.select_first_isolates(frame, period_months=None)
    isolates = deduplicated.drop_duplicates(["dataset_id", "isolate_id"])
    observed = (isolates.groupby("organism", dropna=False)
                .size().reset_index(name="isolates"))
    shown_observed, _ = suppress(observed, ["isolates"], threshold)
    seen = {str(row["organism"]): row["isolates"]
            for _, row in shown_observed.iterrows()}

    def entries(block: Dict[str, object]) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for tier, items in (block or {}).items():
            for item in items or []:
                organism = (item.get("organism") if isinstance(item, dict)
                            else str(item))
                resistance = (item.get("resistance", "")
                              if isinstance(item, dict) else "")
                organism = str(organism or "").strip()
                if not organism:
                    continue
                matches = {name: value for name, value in seen.items()
                           if _matches(organism, name)}
                total = sum(v for v in matches.values()
                            if isinstance(v, (int, float)))
                out.append({
                    "tier": str(tier),
                    "organism": organism,
                    "resistance": str(resistance or ""),
                    "isolates": int(total) if matches else None,
                    "matched": sorted(matches.keys()),
                    "underSurveillance": bool(matches),
                })
        return out

    return {
        "who": entries(lookup.get("WHO_2024", {})),
        "ghana": entries(lookup.get("GHANA_PRIORITY", {})),
        "tierOrder": ["CRITICAL", "HIGH", "MEDIUM"],
    }


def export_genomic_extras(threshold: int, rows, suppress) -> Dict[str, object]:
    """Sequence types, plasmid replicons and virulence genes.

    Held separately from the determinant frequencies because they answer a
    different question. A plasmid replicon says how a gene may be moving; a
    virulence gene says what the organism may do; neither is a resistance
    determinant, and putting them in the same table as one invites a reader to
    treat them as such.
    """
    genomic = gx.load_genomic_frame()
    if genomic.empty:
        return {}

    def tally(column: str, label: str) -> Dict[str, object]:
        if column not in genomic.columns:
            return {"label": label, "rows": []}
        examined = len(genomic)
        counts: Dict[str, int] = {}
        for value in genomic[column]:
            for item in set(value or []):
                name = str(item).strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
        table = pd.DataFrame(
            [{"name": name, "genomes": value,
              "percent": round(100.0 * value / examined, 1) if examined else None}
             for name, value in sorted(counts.items(), key=lambda kv: -kv[1])])
        shown, suppression = suppress(table, ["genomes"], threshold,
                                      blank=["percent"])
        return {"label": label, "rows": rows(shown),
                "suppression": suppression, "examined": examined}

    sequence_types = pd.DataFrame()
    if "sequence_type" in genomic.columns:
        sequence_types = (genomic[genomic["sequence_type"].notna()]
                          .groupby("sequence_type")
                          .size().reset_index(name="genomes")
                          .sort_values("genomes", ascending=False))
    shown_types, type_suppression = suppress(sequence_types, ["genomes"],
                                             threshold)

    return {
        "sequenceTypes": rows(shown_types),
        "sequenceTypeSuppression": type_suppression,
        "plasmids": tally("plasmid_replicons", "Plasmid replicons"),
        "virulence": tally("virulence_genes", "Virulence genes"),
    }


__all__ = ["export_trends", "export_mdr", "export_regions", "export_priority",
           "export_genomic_extras", "PERIOD_FREQ", "MIN_PERIOD_OBSERVATIONS"]
