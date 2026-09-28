"""
Surveillance analytics over the traceability chain.

This is the layer the chain was built to make possible. Everything here counts
isolates, not test rows, and every figure declares how it was derived.

Why this module exists
----------------------
The previous analytics read the flat ``ast_results`` table, where one row was one
susceptibility test. Three consequences followed, all of which the critical
review identified:

* **Organism counts were test counts.** ``value_counts()`` on an AST frame
  reported *Escherichia coli* 972 times where there were 214 isolates.

* **Deduplication was not deduplication.** ``antibiogram.py`` dropped duplicates
  on ``isolate_id + antibiotic`` and called it the CLSI requirement. It is not:
  M39 asks for the *first isolate of a given organism per patient per analysis
  period*, and the old schema had no patient key with which to express that.
  With a pseudonym on every human subject, it can now be implemented properly.

* **Nothing could be stratified clinically.** Ward, specimen type and age lived
  nowhere, so a rate could not be broken down by the things that decide whether
  it means anything.

Reporting rules applied throughout
----------------------------------
* **Isolates are the unit.** A culture tested against twelve drugs is one
  isolate.
* **Sectors are never pooled** unless a caller says so explicitly. A human blood
  culture, a farm sampling round and a wastewater grab are not interchangeable
  observations.
* **Below the reporting threshold, a percentage is withheld, not estimated.**
  The count is still shown, because the absence of enough data is itself
  reportable.
* **No data is distinguished from no signal.** A stratum with no isolates is
  ``no_data``; a stratum with enough isolates and no resistance is a real zero.
  Collapsing the two is how a surveillance blind spot becomes a clean bill of
  health.
* **Every metric has an entry in METRIC_DICTIONARY** stating its numerator,
  denominator, period, deduplication rule, standard and intended use, and what
  it must not be used for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src import db
from src.traceability import (
    HIGH_ACUITY_WARD_TYPES,
    STERILE_SITE_SPECIMENS,
    assert_single_sector,
)

logger = logging.getLogger(__name__)

#: CLSI M39's conventional minimum for reporting a susceptibility percentage.
MIN_ISOLATES_FOR_REPORTING = 30

#: Status of a reported figure. The distinction the review asked for: a stratum
#: with no observations is not a stratum with no resistance.
STATUS_REPORTED = "reported"
STATUS_SUPPRESSED = "suppressed_below_threshold"
STATUS_NO_DATA = "no_data"

#: Results that count as a tested, interpretable observation. 'NS' (non
#: susceptible, reported where a laboratory cannot separate I from R) counts as
#: tested and as not-susceptible.
INTERPRETED_RESULTS = ("S", "I", "R", "NS")
SUSCEPTIBLE_RESULTS = ("S",)

#: Strata the analytics can group by, mapped to the column that carries them.
STRATIFICATIONS: Dict[str, str] = {
    "Sector": "sector",
    "Ward type": "ward_type_at_collection",
    "Specimen type": "specimen_type",
    "Age band": "age_band_at_collection",
    "Sex": "sex",
    "Patient type": "patient_type",
    "Region": "region",
    "District": "district",
    "Laboratory": "lab_name",
    "Facility": "facility_code",
    "Sampling purpose": "sampling_purpose",
    "Organism": "organism",
}

#: Core fields whose completeness the coverage report scores. These are the
#: fields a figure needs in order to be interpretable, not merely stored.
CORE_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("collection_datetime", "Collection date"),
    ("lab_name", "Reporting laboratory"),
    ("region", "Region"),
    ("specimen_type", "Specimen type"),
    ("organism", "Organism"),
    ("result", "Interpreted result"),
    ("breakpoint_standard", "Breakpoint standard"),
    ("breakpoint_version", "Breakpoint edition"),
    ("ward_type_at_collection", "Ward type (human)"),
    ("age_band_at_collection", "Age band (human)"),
    ("sex", "Sex (human)"),
    ("patient_pseudonym", "Patient key (human)"),
    ("qc_status", "AST quality control"),
)

#: Values that are stored but carry no information. Counting "Unknown" as
#: recorded would make a coverage report congratulate itself.
_EMPTY_VALUES = {"", "unknown", "not done", "none", "nan", "n/a", "(null)"}


# ---------------------------------------------------------------------------
# Metric dictionary
#
# The review asked for a frozen dictionary covering units, numerator,
# denominator, time period, deduplication, standard/version, suppression and
# intended use. It lives in code, beside the functions that compute the metrics,
# so the two cannot drift.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricDefinition:
    name: str
    description: str
    unit: str
    numerator: str
    denominator: str
    period: str
    deduplication: str
    standard: str
    suppression: str
    intended_use: str
    not_for: str

    def as_row(self) -> Dict[str, str]:
        return {
            "Metric": self.name,
            "Unit": self.unit,
            "Numerator": self.numerator,
            "Denominator": self.denominator,
            "Period": self.period,
            "Deduplication": self.deduplication,
            "Standard": self.standard,
            "Suppression": self.suppression,
            "Intended use": self.intended_use,
            "Not to be used for": self.not_for,
        }


METRIC_DICTIONARY: Dict[str, MetricDefinition] = {
    "percent_susceptible": MetricDefinition(
        name="Percent susceptible (%S)",
        description="Share of tested isolates reported susceptible to one agent.",
        unit="percent of isolates",
        numerator="Isolates with result S for that organism-agent pair",
        denominator="Isolates with any interpreted result (S, I, R or NS) for that pair",
        period="The selected analysis period; 12 months unless narrowed",
        deduplication="First isolate per patient per organism per period (CLSI M39)",
        standard="CLSI M39 presentation convention; interpretation per the "
                 "breakpoint standard and edition recorded on each result",
        suppression=f"Percentage withheld below {MIN_ISOLATES_FOR_REPORTING} "
                    "isolates; the count is still shown",
        intended_use="Describing susceptibility patterns in a defined population "
                     "and period, for stewardship and empirical-therapy review "
                     "by a clinical governance group",
        not_for="Choosing therapy for an individual patient, comparing "
                "facilities without agreed case mix, or pooling across sectors",
    ),
    "percent_resistant": MetricDefinition(
        name="Percent resistant (%R)",
        description="Share of tested isolates reported resistant to one agent.",
        unit="percent of isolates",
        numerator="Isolates with result R for that organism-agent pair",
        denominator="Isolates with any interpreted result for that pair",
        period="The selected analysis period",
        deduplication="First isolate per patient per organism per period",
        standard="Breakpoint standard and edition as recorded per result",
        suppression=f"Withheld below {MIN_ISOLATES_FOR_REPORTING} isolates",
        intended_use="Trend and burden description within one sector",
        not_for="Inferring transmission, or adding to %S to reach 100 -- "
                "intermediate and non-susceptible results occupy the remainder",
    ),
    "isolate_count": MetricDefinition(
        name="Isolate count",
        description="Number of distinct isolates, one per organism recovered "
                    "from one specimen.",
        unit="isolates",
        numerator="Distinct (dataset, isolate) pairs",
        denominator="Not applicable; a count",
        period="The selected analysis period",
        deduplication="Optional; stated wherever the count is shown",
        standard="Platform definition: one isolate is one organism from one "
                 "specimen, however many agents were tested against it",
        suppression="None; counts are shown at any size",
        intended_use="Pathogen distribution, denominators, and judging whether "
                     "a rate is supportable",
        not_for="Standing in for patient or infection counts -- one patient may "
                "contribute several isolates unless deduplication is applied",
    ),
    "patient_count": MetricDefinition(
        name="Patient count",
        description="Distinct pseudonymous patients contributing isolates.",
        unit="patients",
        numerator="Distinct patient pseudonyms",
        denominator="Not applicable; a count",
        period="The selected analysis period",
        deduplication="Inherent; the pseudonym is the unit",
        standard="Facility-scoped salted pseudonym; a patient at two facilities "
                 "counts twice by design, since the platform cannot and should "
                 "not link them",
        suppression="None",
        intended_use="Denominators for patient-level rates and judging "
                     "deduplication impact",
        not_for="Counting individuals nationally, for the reason above",
    ),
    "specimen_positivity": MetricDefinition(
        name="Culture positivity",
        description="Share of specimens from which at least one organism was "
                    "recovered.",
        unit="percent of specimens",
        numerator="Specimens with one or more isolates",
        denominator="All specimens received, including culture-negative",
        period="The selected analysis period",
        deduplication="None; the specimen is the unit",
        standard="Platform definition",
        suppression=f"Withheld below {MIN_ISOLATES_FOR_REPORTING} specimens",
        intended_use="Laboratory workload, sampling yield, and detecting "
                     "under-reporting of negative cultures",
        not_for="Infection incidence -- specimens are not sampled at random "
                "from any population",
    ),
    "field_completeness": MetricDefinition(
        name="Field completeness",
        description="Share of records carrying an informative value for a core "
                    "field.",
        unit="percent of records",
        numerator="Records with a non-empty value that is not 'Unknown'",
        denominator="All records in scope",
        period="The selected analysis period",
        deduplication="None",
        standard="Platform definition; 'Unknown' counts as missing, because a "
                 "stored placeholder carries no information",
        suppression="None",
        intended_use="Directing data-quality effort and qualifying every other "
                     "figure on this page",
        not_for="Judging laboratory performance in isolation -- a field may be "
                "absent because the collection form never asked for it",
    ),
}


def metric_dictionary_frame() -> pd.DataFrame:
    """The metric dictionary as a table, for display and export."""
    return pd.DataFrame([m.as_row() for m in METRIC_DICTIONARY.values()])


# ---------------------------------------------------------------------------
# The surveillance view
# ---------------------------------------------------------------------------

#: One row per susceptibility observation, carrying its whole lineage. This is
#: the join the traceability model exists to make cheap: phenotype back through
#: isolate, specimen, encounter and subject in one pass.
_SURVEILLANCE_SQL = """
    SELECT
        ph.dataset_id,
        ph.isolate_id,
        ph.antibiotic,
        ph.result,
        ph.mic_value,
        ph.mic_operator,
        ph.zone_diameter,
        ph.ast_method,
        ph.breakpoint_standard,
        ph.breakpoint_version,
        ph.result_source,
        ph.qc_status,
        ph.test_date,

        i.organism,
        i.organism_code,
        i.identification_method,
        i.isolate_number,
        i.is_significant,

        sp.specimen_id,
        sp.specimen_type,
        sp.collection_datetime,
        sp.receipt_datetime,
        sp.ward_at_collection,
        sp.ward_type_at_collection,
        sp.age_years_at_collection,
        sp.age_band_at_collection,
        sp.sampling_purpose,
        sp.condition_on_receipt,
        sp.lab_name,
        sp.region,
        sp.district,
        sp.latitude,
        sp.longitude,

        e.encounter_id,
        e.ward,
        e.ward_type       AS ward_type_admission,
        e.patient_type,
        e.admission_date,
        e.discharge_date,

        s.subject_id,
        s.sector,
        s.patient_pseudonym,
        s.facility_code,
        s.sex,
        s.animal_species,
        s.herd_flock_id,
        s.food_commodity,
        s.water_body
    FROM phenotypes ph
    JOIN isolates  i  ON i.dataset_id  = ph.dataset_id AND i.isolate_id  = ph.isolate_id
    JOIN specimens sp ON sp.dataset_id = i.dataset_id  AND sp.specimen_id = i.specimen_id
    JOIN subjects  s  ON s.dataset_id  = sp.dataset_id AND s.subject_id  = sp.subject_id
    LEFT JOIN encounters e
           ON e.dataset_id = sp.dataset_id AND e.encounter_id = sp.encounter_id
"""


def load_surveillance_frame(dataset_id: Optional[str] = None,
                            sector: Optional[str] = None) -> pd.DataFrame:
    """Load the surveillance view: one row per susceptibility observation.

    Filtering happens in SQL rather than in pandas so a national dataset does
    not have to be pulled into memory to answer a question about one ward.
    """
    clauses: List[str] = []
    params: List[object] = []
    if dataset_id:
        clauses.append("ph.dataset_id = %s")
        params.append(dataset_id)
    if sector:
        clauses.append("s.sector = %s")
        params.append(str(sector).lower())

    sql = _SURVEILLANCE_SQL
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else None)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()

    frame = pd.DataFrame([dict(r) for r in rows], columns=columns)
    if not frame.empty:
        frame["collection_datetime"] = pd.to_datetime(
            frame["collection_datetime"], errors="coerce", utc=True)
    return frame


def load_specimen_frame(dataset_id: Optional[str] = None,
                        sector: Optional[str] = None) -> pd.DataFrame:
    """Specimens with their subject, including those that grew nothing.

    Culture-negative specimens are invisible in the surveillance view, which
    starts from phenotypes. A positivity rate needs them, and so does any honest
    statement about how much material a laboratory processed.
    """
    sql = """
        SELECT sp.dataset_id, sp.specimen_id, sp.specimen_type,
               sp.collection_datetime, sp.receipt_datetime, sp.lab_name,
               sp.region, sp.district, sp.ward_at_collection,
               sp.ward_type_at_collection, sp.age_band_at_collection,
               sp.sampling_purpose, sp.condition_on_receipt,
               s.subject_id, s.sector, s.patient_pseudonym, s.facility_code,
               s.sex,
               (SELECT count(*) FROM isolates i
                 WHERE i.dataset_id = sp.dataset_id
                   AND i.specimen_id = sp.specimen_id) AS isolate_count
        FROM specimens sp
        JOIN subjects s ON s.dataset_id = sp.dataset_id
                       AND s.subject_id = sp.subject_id
    """
    clauses, params = [], []
    if dataset_id:
        clauses.append("sp.dataset_id = %s")
        params.append(dataset_id)
    if sector:
        clauses.append("s.sector = %s")
        params.append(str(sector).lower())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else None)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()

    frame = pd.DataFrame([dict(r) for r in rows], columns=columns)
    if not frame.empty:
        frame["collection_datetime"] = pd.to_datetime(
            frame["collection_datetime"], errors="coerce", utc=True)
    return frame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_informative(series: pd.Series) -> pd.Series:
    """Whether each value carries information.

    A stored 'Unknown' is not a recorded value. Treating it as one is how a
    completeness report comes to claim full coverage of a field nobody filled.
    """
    text = series.astype(str).str.strip().str.lower()
    return series.notna() & ~text.isin(_EMPTY_VALUES)


def wilson_interval(successes: int, total: int,
                    z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    """Wilson score interval, as a percentage.

    Preferred over the normal approximation because susceptibility proportions
    are routinely near 0 or 1 at these sample sizes, where the normal interval
    runs outside [0, 1] and understates uncertainty.
    """
    if not total:
        return None, None
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    half = (z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))) / denom
    return (max(0.0, (centre - half)) * 100, min(1.0, (centre + half)) * 100)


def _tested_mask(frame: pd.DataFrame) -> pd.Series:
    """Rows with an interpreted result, which are the only countable ones.

    An untested combination is not a susceptible one, so a blank result must
    never reach a denominator.
    """
    if "result" not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame["result"].astype(str).str.strip().str.upper().isin(INTERPRETED_RESULTS)


def exclude_failed_qc(frame: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Drop results whose run failed quality control.

    A result from a failed QC run is not evidence about the isolate; it is
    evidence about the run. Returns the frame and how many rows were dropped, so
    the exclusion can be stated rather than assumed.
    """
    if frame.empty or "qc_status" not in frame.columns:
        return frame, 0
    failed = frame["qc_status"].astype(str).str.strip().str.lower() == "fail"
    return frame[~failed].copy(), int(failed.sum())


# ---------------------------------------------------------------------------
# CLSI M39 first-isolate selection
# ---------------------------------------------------------------------------

@dataclass
class DeduplicationReport:
    """What deduplication did, so its effect can be seen rather than trusted."""

    isolates_before: int
    isolates_after: int
    patients: int
    unkeyed_isolates: int
    period_start: Optional[date]
    period_end: Optional[date]
    rule: str

    @property
    def removed(self) -> int:
        return self.isolates_before - self.isolates_after

    @property
    def summary(self) -> str:
        if not self.isolates_before:
            return "No isolates in scope."
        pct = 100 * self.removed / self.isolates_before
        window = ""
        if self.period_start and self.period_end:
            window = (f" between {self.period_start.isoformat()} and "
                      f"{self.period_end.isoformat()}")
        note = ""
        if self.unkeyed_isolates:
            note = (f" {self.unkeyed_isolates} isolate(s) had no patient key and "
                    "were kept as distinct, since repeat sampling of one subject "
                    "cannot be detected without one.")
        return (f"{self.rule} Kept {self.isolates_after:,} of "
                f"{self.isolates_before:,} isolates{window} "
                f"({pct:.1f}% removed as repeats) across {self.patients:,} "
                f"subject(s).{note}")


def select_first_isolates(frame: pd.DataFrame, *,
                          period_start: Optional[date] = None,
                          period_end: Optional[date] = None,
                          period_months: Optional[int] = None,
                          by_specimen_type: bool = False
                          ) -> Tuple[pd.DataFrame, DeduplicationReport]:
    """Apply CLSI M39 first-isolate-per-patient deduplication.

    The rule: within the analysis period, keep the earliest isolate of each
    organism for each subject, and drop later isolates of the same organism from
    the same subject. Repeat testing of one patient's persistent infection then
    contributes once, instead of weighting the antibiogram towards whoever was
    cultured most often -- typically the sickest and most heavily treated
    patients, whose isolates are the most resistant.

    What the old code did instead was ``drop_duplicates(['isolate_id',
    'antibiotic'])``, which removes a literal duplicate row and nothing else.

    ``by_specimen_type`` keeps the first isolate per specimen type as well,
    which M39 permits where a blood and a urine isolate of one organism are
    treated as separate observations. It is off by default because it weakens
    the deduplication and should be a deliberate choice.

    For non-human sectors the subject is a herd, flock, pond or sampling point
    rather than a patient, and the same rule expresses "first recovery of this
    organism from this unit in the period".
    """
    rule = ("First isolate per subject per organism per period"
            + (" per specimen type" if by_specimen_type else "")
            + " (CLSI M39).")

    if frame.empty:
        return frame, DeduplicationReport(0, 0, 0, 0, None, None, rule)

    working = frame.copy()

    # Resolve the analysis period. M39 antibiograms cover a defined window, and
    # "the whole database" is not one -- so the window actually used is recorded.
    collected = working["collection_datetime"]
    if period_end is None:
        period_end = (collected.max().date()
                      if collected.notna().any() else None)
    if period_start is None and period_end is not None and period_months:
        period_start = period_end - timedelta(days=int(30.44 * period_months))
    if period_start is None and collected.notna().any():
        period_start = collected.min().date()

    if period_start is not None and period_end is not None:
        in_period = (
            collected.isna()
            | ((collected.dt.date >= period_start) & (collected.dt.date <= period_end))
        )
        working = working[in_period]

    if working.empty:
        return working, DeduplicationReport(0, 0, 0, 0, period_start, period_end, rule)

    # Deduplicate isolates, not observations: collapse to one row per isolate,
    # choose the survivors, then filter the observations back.
    isolate_keys = ["dataset_id", "isolate_id"]
    isolates = (working.sort_values("collection_datetime")
                       .drop_duplicates(subset=isolate_keys)
                       .copy())
    before = len(isolates)

    # A subject with no key cannot be matched to its own earlier specimens, so
    # each such isolate stands alone rather than being silently merged with
    # another subject's.
    subject = isolates["subject_id"].astype(str)
    has_key = _is_informative(isolates["subject_id"])
    isolates["_subject_key"] = np.where(
        has_key, subject, "unkeyed:" + isolates["isolate_id"].astype(str))
    unkeyed = int((~has_key).sum())

    group_cols = ["dataset_id", "_subject_key", "organism"]
    if by_specimen_type:
        group_cols.append("specimen_type")

    # NaT collection dates sort last, so a dated isolate is preferred as "first"
    # over an undated one.
    keepers = (isolates.sort_values("collection_datetime",
                                    na_position="last")
                       .groupby(group_cols, dropna=False, sort=False)
                       .head(1))
    kept_ids = set(zip(keepers["dataset_id"], keepers["isolate_id"]))

    mask = pd.Series(
        [(d, i) in kept_ids for d, i in zip(working["dataset_id"],
                                            working["isolate_id"])],
        index=working.index)
    deduplicated = working[mask].copy()

    report = DeduplicationReport(
        isolates_before=before,
        isolates_after=len(keepers),
        patients=int(keepers["_subject_key"].nunique()),
        unkeyed_isolates=unkeyed,
        period_start=period_start,
        period_end=period_end,
        rule=rule,
    )
    return deduplicated, report


# ---------------------------------------------------------------------------
# Pathogen distribution
# ---------------------------------------------------------------------------

def pathogen_distribution(frame: pd.DataFrame, *,
                          by: Optional[str] = None,
                          top: Optional[int] = None,
                          allow_cross_sector: bool = False) -> pd.DataFrame:
    """Isolate counts per organism, optionally within a stratum.

    Counts **isolates**. The page this replaces ran ``value_counts()`` over an
    AST frame, so an organism tested against more agents outranked one tested
    against fewer, and every figure was inflated by the number of drugs on the
    panel.
    """
    if frame.empty:
        return pd.DataFrame(columns=["organism", "isolates", "percent"])

    if not allow_cross_sector and "sector" in frame.columns:
        assert_single_sector(frame["sector"].dropna().unique())

    isolates = frame.drop_duplicates(subset=["dataset_id", "isolate_id"])
    group = ["organism"] + ([by] if by else [])
    counts = (isolates.groupby(group, dropna=False)
                      .size()
                      .reset_index(name="isolates"))

    if by:
        totals = counts.groupby(by, dropna=False)["isolates"].transform("sum")
    else:
        totals = counts["isolates"].sum()
    counts["percent"] = np.where(totals > 0, 100 * counts["isolates"] / totals, np.nan)

    counts = counts.sort_values(["isolates"], ascending=False).reset_index(drop=True)
    if top:
        if by:
            counts = (counts.groupby(by, dropna=False, group_keys=False)
                            .head(top).reset_index(drop=True))
        else:
            counts = counts.head(top)
    return counts


# ---------------------------------------------------------------------------
# Susceptibility
# ---------------------------------------------------------------------------

def _summarise_group(group: pd.DataFrame, min_isolates: int) -> Dict[str, object]:
    tested_rows = group[_tested_mask(group)]
    tested = int(len(tested_rows.drop_duplicates(subset=["dataset_id", "isolate_id"])))
    if tested == 0:
        return {
            "tested": 0, "susceptible": 0, "intermediate": 0, "resistant": 0,
            "percent_susceptible": None, "percent_resistant": None,
            "ci_low": None, "ci_high": None, "status": STATUS_NO_DATA,
        }

    result = tested_rows["result"].astype(str).str.strip().str.upper()
    susceptible = int((result == "S").sum())
    intermediate = int((result == "I").sum())
    resistant = int(result.isin(["R", "NS"]).sum())

    if tested < min_isolates:
        # Count reported, percentage withheld. The review's point: a rate on
        # eight isolates invites a decision the data cannot support.
        return {
            "tested": tested, "susceptible": susceptible,
            "intermediate": intermediate, "resistant": resistant,
            "percent_susceptible": None, "percent_resistant": None,
            "ci_low": None, "ci_high": None, "status": STATUS_SUPPRESSED,
        }

    low, high = wilson_interval(susceptible, tested)
    return {
        "tested": tested, "susceptible": susceptible,
        "intermediate": intermediate, "resistant": resistant,
        "percent_susceptible": 100 * susceptible / tested,
        "percent_resistant": 100 * resistant / tested,
        "ci_low": low, "ci_high": high, "status": STATUS_REPORTED,
    }


def cumulative_antibiogram(frame: pd.DataFrame, *,
                           deduplicate: bool = True,
                           min_isolates: int = MIN_ISOLATES_FOR_REPORTING,
                           period_months: Optional[int] = 12,
                           drop_failed_qc: bool = True,
                           allow_cross_sector: bool = False
                           ) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """A cumulative antibiogram, as close to CLSI M39 as the data allows.

    Returns the table and a provenance dictionary recording every choice made:
    the period, the deduplication rule and its effect, QC exclusions and the
    suppression threshold. A table without that context is not auditable, and
    the review's objection to the previous version was precisely that its
    method was invisible.
    """
    provenance: Dict[str, object] = {
        "min_isolates": min_isolates,
        "deduplicated": bool(deduplicate),
        "qc_failures_excluded": 0,
        "sectors": [],
        "period_start": None,
        "period_end": None,
        "deduplication_summary": "Not applied.",
        "observations_in": int(len(frame)),
    }

    if frame.empty:
        return pd.DataFrame(), provenance

    if not allow_cross_sector and "sector" in frame.columns:
        assert_single_sector(frame["sector"].dropna().unique())
    provenance["sectors"] = sorted(
        {str(s) for s in frame.get("sector", pd.Series(dtype=object)).dropna()})

    working = frame
    if drop_failed_qc:
        working, dropped = exclude_failed_qc(working)
        provenance["qc_failures_excluded"] = dropped

    if deduplicate:
        working, report = select_first_isolates(working, period_months=period_months)
        provenance["deduplication_summary"] = report.summary
        provenance["period_start"] = report.period_start
        provenance["period_end"] = report.period_end
        provenance["isolates_before_dedup"] = report.isolates_before
        provenance["isolates_after_dedup"] = report.isolates_after
        provenance["patients"] = report.patients

    if working.empty:
        return pd.DataFrame(), provenance

    rows: List[Dict[str, object]] = []
    for (organism, antibiotic), group in working.groupby(["organism", "antibiotic"],
                                                         dropna=False):
        summary = _summarise_group(group, min_isolates)
        standards = sorted({f"{s} {v}".strip() for s, v in zip(
            group.get("breakpoint_standard", pd.Series(dtype=object)).fillna(""),
            group.get("breakpoint_version", pd.Series(dtype=object)).fillna(""))
            if str(s).strip()})
        rows.append({"organism": organism, "antibiotic": antibiotic,
                     **summary,
                     "breakpoints": "; ".join(standards) or "not recorded"})

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["organism", "antibiotic"]).reset_index(drop=True)
    provenance["pairs_total"] = int(len(table))
    provenance["pairs_reportable"] = int(
        (table["status"] == STATUS_REPORTED).sum()) if not table.empty else 0
    return table, provenance


def stratified_susceptibility(frame: pd.DataFrame, *,
                              by: str,
                              organism: Optional[str] = None,
                              antibiotic: Optional[str] = None,
                              deduplicate: bool = True,
                              min_isolates: int = MIN_ISOLATES_FOR_REPORTING,
                              allow_cross_sector: bool = False
                              ) -> pd.DataFrame:
    """Susceptibility broken down by one stratum -- ward type, specimen type,
    age band, region and so on.

    This is what the clinical fields were added for. An overall 56% susceptible
    to ciprofloxacin may be 80% on an outpatient specimen and 30% in intensive
    care, and the average is the one number that describes neither.

    Strata below the reporting threshold keep their counts and lose their
    percentage, and a stratum with no tested isolates is marked ``no_data``
    rather than shown as zero.
    """
    if frame.empty or by not in frame.columns:
        return pd.DataFrame()

    if not allow_cross_sector and "sector" in frame.columns:
        assert_single_sector(frame["sector"].dropna().unique())

    working = frame
    if organism:
        working = working[working["organism"] == organism]
    if antibiotic:
        working = working[working["antibiotic"] == antibiotic]
    if working.empty:
        return pd.DataFrame()

    if deduplicate:
        working, _ = select_first_isolates(working)

    rows: List[Dict[str, object]] = []
    for stratum, group in working.groupby(by, dropna=False):
        label = "Not recorded" if not _is_informative(pd.Series([stratum])).iloc[0] \
            else str(stratum)
        rows.append({by: label, **_summarise_group(group, min_isolates)})

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values("tested", ascending=False).reset_index(drop=True)


def stratified_resistance(frame: pd.DataFrame, *,
                         by: str,
                         organism: Optional[str] = None,
                         antibiotic: Optional[str] = None,
                         deduplicate: bool = True,
                         min_observations: int = MIN_ISOLATES_FOR_REPORTING,
                         allow_cross_sector: bool = False) -> pd.DataFrame:
    """Non-susceptibility by stratum, pooled across organisms or agents.

    ``stratified_susceptibility`` answers "how susceptible is this organism to
    this agent, by ward" and counts isolates. This answers the broader question
    "how much resistance is there, by ward" across many organism-agent pairs at
    once, and it cannot use the same denominator: with twelve agents per isolate,
    counting isolates as the denominator while counting results as the numerator
    would produce a percentage over 100.

    So the unit here is the **observation** -- one isolate against one agent --
    and the column names say so. The figure is genuinely useful for comparing
    strata, and genuinely dependent on which agents each laboratory happened to
    test, which is why ``distinct_pairs`` is returned beside it: two strata are
    only comparable when their panels are similar.
    """
    if frame.empty or by not in frame.columns:
        return pd.DataFrame()

    if not allow_cross_sector and "sector" in frame.columns:
        assert_single_sector(frame["sector"].dropna().unique())

    working = frame
    if organism:
        working = working[working["organism"] == organism]
    if antibiotic:
        working = working[working["antibiotic"] == antibiotic]
    working = working[_tested_mask(working)]
    if working.empty:
        return pd.DataFrame()

    if deduplicate:
        working, _ = select_first_isolates(working)
        if working.empty:
            return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    for stratum, group in working.groupby(by, dropna=False):
        label = ("Not recorded"
                 if not _is_informative(pd.Series([stratum])).iloc[0]
                 else str(stratum))
        results = group["result"].astype(str).str.strip().str.upper()
        observations = int(len(group))
        non_susceptible = int(results.isin(["I", "R", "NS"]).sum())
        susceptible = int((results == "S").sum())
        isolates = int(len(group.drop_duplicates(
            subset=["dataset_id", "isolate_id"])))
        pairs = int(group.groupby(["organism", "antibiotic"]).ngroups)

        if observations == 0:
            status, percent, low, high = STATUS_NO_DATA, None, None, None
        elif observations < min_observations:
            status, percent, low, high = STATUS_SUPPRESSED, None, None, None
        else:
            status = STATUS_REPORTED
            percent = 100 * non_susceptible / observations
            low, high = wilson_interval(non_susceptible, observations)

        rows.append({
            by: label,
            "isolates": isolates,
            "observations": observations,
            "susceptible": susceptible,
            "non_susceptible": non_susceptible,
            "percent_non_susceptible": percent,
            "ci_low": low,
            "ci_high": high,
            "distinct_pairs": pairs,
            "status": status,
        })

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values("observations", ascending=False).reset_index(drop=True)


def high_acuity_comparison(frame: pd.DataFrame, *, organism: str,
                           antibiotic: str,
                           min_isolates: int = MIN_ISOLATES_FOR_REPORTING
                           ) -> pd.DataFrame:
    """Susceptibility in high-acuity wards against the rest.

    ICU, neonatal, surgical, burns and haemato-oncology wards are where
    device- and procedure-associated infection concentrates, so they are the
    comparison an infection-prevention team actually wants. The grouping comes
    from ``traceability.HIGH_ACUITY_WARD_TYPES`` so it is defined once.
    """
    if frame.empty or "ward_type_at_collection" not in frame.columns:
        return pd.DataFrame()

    working = frame[(frame["organism"] == organism)
                    & (frame["antibiotic"] == antibiotic)].copy()
    if working.empty:
        return pd.DataFrame()

    ward = working["ward_type_at_collection"]
    working["ward_group"] = np.where(
        ~_is_informative(ward), "Not recorded",
        np.where(ward.isin(HIGH_ACUITY_WARD_TYPES), "High-acuity wards",
                 "Other wards"))
    working, _ = select_first_isolates(working)

    rows = [{"ward_group": g, **_summarise_group(grp, min_isolates)}
            for g, grp in working.groupby("ward_group", dropna=False)]
    return pd.DataFrame(rows)


def sterile_site_share(frame: pd.DataFrame) -> Dict[str, object]:
    """How much of the evidence comes from a normally sterile site.

    A positive blood or CSF culture means something a wound swab does not, so
    the mix matters when reading any aggregate rate.
    """
    if frame.empty or "specimen_type" not in frame.columns:
        return {"isolates": 0, "sterile_site": 0, "percent": None}
    isolates = frame.drop_duplicates(subset=["dataset_id", "isolate_id"])
    sterile = isolates["specimen_type"].isin(STERILE_SITE_SPECIMENS).sum()
    total = len(isolates)
    return {"isolates": int(total), "sterile_site": int(sterile),
            "percent": (100 * sterile / total) if total else None}


__all__ = [
    "MIN_ISOLATES_FOR_REPORTING",
    "STATUS_REPORTED", "STATUS_SUPPRESSED", "STATUS_NO_DATA",
    "STRATIFICATIONS", "CORE_FIELDS",
    "MetricDefinition", "METRIC_DICTIONARY", "metric_dictionary_frame",
    "load_surveillance_frame", "load_specimen_frame",
    "wilson_interval", "exclude_failed_qc",
    "DeduplicationReport", "select_first_isolates",
    "pathogen_distribution", "cumulative_antibiogram",
    "stratified_susceptibility", "stratified_resistance",
    "high_acuity_comparison", "sterile_site_share",
]


# ---------------------------------------------------------------------------
# Data-system performance
#
# The review asked for this as a surveillance product in its own right: "Report
# site and sector coverage; expected versus received submissions; timeliness;
# completeness of core fields; duplicate, invalid and unlinked record rates; AST
# quality-control performance; sequence linkage; and missing denominators. Show
# reporting volume and uncertainty beside every rate, and allow users to
# distinguish 'no signal' from 'no data'."
#
# It is the most useful page in the platform today, because every clinical field
# is empty for the backfilled records and this is what says so.
# ---------------------------------------------------------------------------

@dataclass
class CoverageReport:
    """Whether the data can support the figures drawn from it."""

    specimens: int
    isolates: int
    observations: int
    patients: int
    labs: int
    sectors: Dict[str, int]
    completeness: pd.DataFrame
    freshness: Dict[str, object]
    linkage: Dict[str, object]
    quality: Dict[str, object]

    @property
    def headline(self) -> str:
        if not self.specimens:
            return "No specimens in scope."
        return (f"{self.specimens:,} specimens, {self.isolates:,} isolates and "
                f"{self.observations:,} susceptibility results from "
                f"{self.labs} laboratories.")


def field_completeness(frame: pd.DataFrame,
                       fields: Sequence[Tuple[str, str]] = CORE_FIELDS,
                       ) -> pd.DataFrame:
    """Completeness of each core field, counting 'Unknown' as missing.

    That last point is the whole value of this table. The backfilled records
    store 'Unknown' for ward type, specimen type and age band, so a check for
    NULL would report those fields as fully populated and the dashboard would
    draw a confident chart of a single bar.
    """
    rows: List[Dict[str, object]] = []
    human_only = {"ward_type_at_collection", "age_band_at_collection", "sex",
                  "patient_pseudonym"}

    for column, label in fields:
        if column not in frame.columns:
            rows.append({"Field": label, "Column": column, "Scope": "n/a",
                         "Recorded": 0, "Of": 0, "Percent": None,
                         "Status": "column absent"})
            continue

        scope = frame
        scope_label = "all records"
        if column in human_only and "sector" in frame.columns:
            scope = frame[frame["sector"].astype(str).str.lower() == "human"]
            scope_label = "human records"

        denom = len(scope)
        recorded = int(_is_informative(scope[column]).sum()) if denom else 0
        percent = (100 * recorded / denom) if denom else None
        if denom == 0:
            status = "no records in scope"
        elif percent == 0:
            status = "not collected"
        elif percent < 50:
            status = "sparse"
        elif percent < 95:
            status = "partial"
        else:
            status = "complete"

        rows.append({"Field": label, "Column": column, "Scope": scope_label,
                     "Recorded": recorded, "Of": denom,
                     "Percent": percent, "Status": status})

    table = pd.DataFrame(rows)
    return table.sort_values("Percent", na_position="first").reset_index(drop=True)


def _freshness(specimens: pd.DataFrame) -> Dict[str, object]:
    """How current the data is.

    The review found a dashboard tile reading "182d ago" with no indication that
    this mattered. An "as of" date belongs beside every headline figure, so it is
    computed here rather than left to each page to remember.
    """
    if specimens.empty or "collection_datetime" not in specimens.columns:
        return {"latest_collection": None, "earliest_collection": None,
                "days_since_latest": None, "status": "no data"}

    collected = specimens["collection_datetime"].dropna()
    if collected.empty:
        return {"latest_collection": None, "earliest_collection": None,
                "days_since_latest": None, "status": "no collection dates"}

    latest = collected.max()
    earliest = collected.min()
    days = int((pd.Timestamp.now(tz="UTC") - latest).days)
    if days <= 31:
        status = "current"
    elif days <= 92:
        status = "lagging"
    else:
        status = "stale"
    return {
        "latest_collection": latest.date(),
        "earliest_collection": earliest.date(),
        "days_since_latest": days,
        "status": status,
        "span_days": int((latest - earliest).days),
    }


def _turnaround(frame: pd.DataFrame) -> Dict[str, object]:
    """Time from collection to laboratory receipt.

    A system that reports resistance six weeks after the specimen was taken
    cannot inform the treatment of the patient it came from. Median rather than
    mean, because transport delays have a long tail.
    """
    if frame.empty or not {"collection_datetime", "receipt_datetime"} <= set(frame.columns):
        return {"median_days": None, "measurable": 0}
    collected = pd.to_datetime(frame["collection_datetime"], errors="coerce", utc=True)
    received = pd.to_datetime(frame["receipt_datetime"], errors="coerce", utc=True)
    delta = (received - collected).dt.total_seconds() / 86400
    usable = delta[(delta.notna()) & (delta >= 0)]
    return {"median_days": float(usable.median()) if not usable.empty else None,
            "measurable": int(len(usable))}


def coverage_report(dataset_id: Optional[str] = None,
                    sector: Optional[str] = None) -> CoverageReport:
    """Assemble the data-system performance report."""
    observations = load_surveillance_frame(dataset_id=dataset_id, sector=sector)
    specimens = load_specimen_frame(dataset_id=dataset_id, sector=sector)

    sectors: Dict[str, int] = {}
    if not specimens.empty and "sector" in specimens.columns:
        sectors = (specimens.groupby("sector", dropna=False)
                            .size().sort_values(ascending=False).to_dict())

    isolates = 0
    if not observations.empty:
        isolates = int(len(observations.drop_duplicates(
            subset=["dataset_id", "isolate_id"])))

    patients = 0
    if not specimens.empty and "patient_pseudonym" in specimens.columns:
        patients = int(specimens.loc[
            _is_informative(specimens["patient_pseudonym"]),
            "patient_pseudonym"].nunique())

    labs = 0
    if not specimens.empty and "lab_name" in specimens.columns:
        labs = int(specimens.loc[_is_informative(specimens["lab_name"]),
                                 "lab_name"].nunique())

    # Linkage: the chain is only useful where it is actually joined up.
    linkage: Dict[str, object] = {}
    if not specimens.empty:
        with_isolate = int((specimens["isolate_count"].fillna(0) > 0).sum())
        linkage["specimens_with_isolate"] = with_isolate
        linkage["specimens_total"] = int(len(specimens))
        linkage["culture_positivity_percent"] = (
            100 * with_isolate / len(specimens) if len(specimens) else None)
        linkage["specimens_with_ward"] = int(_is_informative(
            specimens.get("ward_type_at_collection", pd.Series(dtype=object))).sum())

    if isolates:
        tested_isolates = int(len(
            observations[_tested_mask(observations)]
            .drop_duplicates(subset=["dataset_id", "isolate_id"])))
        linkage["isolates_with_result"] = tested_isolates
        linkage["isolates_total"] = isolates

    # Genomic linkage is the review's "sequence linkage" measure.
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        where, params = "", []
        if dataset_id:
            where, params = " WHERE dataset_id = %s", [dataset_id]
        cur.execute(f"SELECT count(*) FROM genomic_results{where}",
                    tuple(params) if params else None)
        genomes = cur.fetchone()[0]
        cur.execute(
            "SELECT count(DISTINCT isolate_id) FROM genomic_results" + where,
            tuple(params) if params else None)
        sequenced_isolates = cur.fetchone()[0]
        cur.close()
    except Exception:
        logger.exception("genomic linkage query failed")
        genomes, sequenced_isolates = 0, 0
    finally:
        conn.close()

    linkage["genomic_results"] = int(genomes)
    linkage["isolates_sequenced"] = int(sequenced_isolates)
    linkage["percent_isolates_sequenced"] = (
        100 * sequenced_isolates / isolates if isolates else None)

    # AST quality control, and how much of the evidence is rule-derived rather
    # than measured -- a distinction the review asked to be made visible.
    quality: Dict[str, object] = {}
    if not observations.empty:
        qc = observations.get("qc_status", pd.Series(dtype=object))
        quality["qc_recorded"] = int(_is_informative(qc).sum())
        quality["qc_total"] = int(len(observations))
        lowered = qc.astype(str).str.strip().str.lower()
        quality["qc_pass"] = int((lowered == "pass").sum())
        quality["qc_fail"] = int((lowered == "fail").sum())
        source = observations.get("result_source", pd.Series(dtype=object))
        quality["result_source"] = (source.fillna("not recorded")
                                          .value_counts().to_dict())
        edition = observations.get("breakpoint_version", pd.Series(dtype=object))
        quality["results_without_edition"] = int((~_is_informative(edition)).sum())
    quality["turnaround"] = _turnaround(specimens)

    return CoverageReport(
        specimens=int(len(specimens)),
        isolates=isolates,
        observations=int(len(observations)),
        patients=patients,
        labs=labs,
        sectors={str(k): int(v) for k, v in sectors.items()},
        completeness=field_completeness(observations if not observations.empty
                                        else specimens),
        freshness=_freshness(specimens),
        linkage=linkage,
        quality=quality,
    )


__all__ += ["CoverageReport", "field_completeness", "coverage_report"]
