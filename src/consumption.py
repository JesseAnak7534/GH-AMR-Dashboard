"""
Antimicrobial use and consumption, with denominators that hold up.

What the review objected to
---------------------------
    "The AMU page plots raw quantities for regional comparisons and averages
    row-level ddd_per_1000 values by period. Simple means across records can be
    misleading when sites have different patient-day denominators or reporting
    volumes. Store numerator, denominator, units, conversion factor and
    calculation method, then calculate a pooled rate from the appropriate
    totals. Show raw use alongside a clearly defined normalized rate. Do not
    compare regions using an unnormalized quantity alone."

    "The animal AMC page also averages row-level mg_per_kg_biomass by species.
    Verify that the underlying unit is active ingredient mass and calculate a
    correctly weighted measure from total active ingredient and the specified
    biomass denominator."

Both were doing exactly that. Regional AMU compared ``sum(quantity_dispensed)``,
so a region with more hospitals looked like it used more antibiotics per
patient, which is not what the chart appeared to say. The DDD trend averaged
one rate per record, so a clinic reporting three prescriptions counted as much
as a teaching hospital reporting thirty thousand.

The arithmetic
--------------
A rate of rates is not a rate. The pooled figure divides summed numerator by
summed denominator:

    DDD per 1,000 patient-days  =  sum(DDD)        / sum(patient-days) x 1000
    mg per kg biomass           =  sum(active mg)  / sum(biomass kg)

These differ substantially whenever reporting volume varies between the units
being compared, which in a national system it always does.

Missing denominators
--------------------
A record with no denominator cannot contribute to a rate. It is excluded from
the rate and counted separately, because quietly dropping it would overstate
coverage, and quietly treating it as zero would understate the rate. Every
function here returns the coverage alongside the figure, so a rate computed
from a third of the records is visibly that.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src import db

logger = logging.getLogger(__name__)

#: Defined daily doses per 1,000 patient-days is reported per thousand.
DDD_MULTIPLIER = 1000.0

#: Milligrams in a kilogram, for the AMC active-ingredient conversion.
MG_PER_KG = 1_000_000.0


@dataclass(frozen=True)
class ConsumptionMetric:
    """A consumption metric, defined the way the review asked."""

    name: str
    unit: str
    numerator: str
    denominator: str
    conversion: str
    calculation: str
    intended_use: str
    not_for: str

    def as_row(self) -> Dict[str, str]:
        return {
            "Metric": self.name, "Unit": self.unit,
            "Numerator": self.numerator, "Denominator": self.denominator,
            "Conversion": self.conversion, "Calculation": self.calculation,
            "Intended use": self.intended_use, "Not to be used for": self.not_for,
        }


METRICS: Dict[str, ConsumptionMetric] = {
    "ddd_per_1000_patient_days": ConsumptionMetric(
        name="DDD per 1,000 patient-days",
        unit="defined daily doses per 1,000 patient-days",
        numerator="Total defined daily doses dispensed in the group",
        denominator="Total patient-days reported by the same facilities over "
                    "the same periods",
        conversion="Where DDD is not reported directly it is recovered as "
                   "ddd_per_1000 x patient_days / 1000, so a record "
                   "contributes only when it carries both",
        calculation="sum(DDD) / sum(patient-days) x 1000. Pooled, not the mean "
                    "of each record's rate: averaging rates weights a clinic "
                    "reporting three prescriptions equally with a hospital "
                    "reporting thirty thousand",
        intended_use="Comparing antimicrobial use between facilities, regions "
                     "or periods on a common denominator",
        not_for="Comparing against a facility that did not report patient-days, "
                "or inferring appropriateness -- volume is not quality",
    ),
    "quantity_dispensed": ConsumptionMetric(
        name="Quantity dispensed",
        unit="as reported by the facility",
        numerator="Sum of quantity_dispensed",
        denominator="None. This is a volume, not a rate",
        conversion="None. Units are as submitted and may differ between "
                   "facilities",
        calculation="sum(quantity_dispensed)",
        intended_use="Describing procurement and workload within one facility "
                     "or one unit of measure",
        not_for="Comparing regions or facilities. A region with more hospitals "
                "dispenses more without using more per patient, and the units "
                "may not even be the same",
    ),
    "mg_per_kg_biomass": ConsumptionMetric(
        name="Milligrams of active ingredient per kilogram of biomass",
        unit="mg active ingredient / kg biomass",
        numerator="Total active-ingredient mass, in milligrams",
        denominator="Total biomass of the population at risk, in kilograms",
        conversion="quantity_kg is taken to be active-ingredient mass and "
                   "converted at 1,000,000 mg per kg. Where a submission "
                   "reports product mass rather than active ingredient, the "
                   "figure overstates use and the submission must be corrected "
                   "at source",
        calculation="sum(active ingredient mg) / sum(biomass kg). Pooled, not "
                    "the mean of each record's ratio",
        intended_use="Comparing veterinary antimicrobial consumption between "
                     "species, production systems or periods",
        not_for="Comparing against human DDD figures, which use an entirely "
                "different denominator",
    ),
}


def metrics_frame() -> pd.DataFrame:
    return pd.DataFrame([m.as_row() for m in METRICS.values()])


# ---------------------------------------------------------------------------
# Result of a pooled calculation
# ---------------------------------------------------------------------------

@dataclass
class PooledRate:
    """A pooled rate, with the evidence for how much of the data it used."""

    table: pd.DataFrame
    records_total: int
    records_used: int
    numerator_total: float
    denominator_total: float

    @property
    def coverage(self) -> Optional[float]:
        if not self.records_total:
            return None
        return 100 * self.records_used / self.records_total

    @property
    def usable(self) -> bool:
        return self.records_used > 0 and self.denominator_total > 0

    @property
    def caveat(self) -> str:
        if not self.records_total:
            return "No records in scope."
        if not self.records_used:
            return ("No record carries both a numerator and a denominator, so a "
                    "rate cannot be computed. Raw volumes are shown instead, "
                    "and they are not comparable between groups.")
        if self.coverage is not None and self.coverage < 100:
            return (f"Computed from {self.records_used:,} of "
                    f"{self.records_total:,} records "
                    f"({self.coverage:.0f}%). The remainder carry no usable "
                    "denominator and are excluded from the rate rather than "
                    "counted as zero.")
        return f"Computed from all {self.records_total:,} records."


# ---------------------------------------------------------------------------
# AMU
# ---------------------------------------------------------------------------

def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def prepare_amu(amu_df: pd.DataFrame) -> pd.DataFrame:
    """Add the explicit DDD numerator the pooled calculation needs.

    The table stores ``ddd_per_1000`` and ``patient_days`` but not the dose
    count itself, so the numerator is recovered from the two. A record missing
    either cannot contribute, and is marked rather than silently dropped.
    """
    if amu_df is None or amu_df.empty:
        return pd.DataFrame()

    out = amu_df.copy()
    rate = _numeric(out.get("ddd_per_1000", pd.Series(dtype=float)))
    days = _numeric(out.get("patient_days", pd.Series(dtype=float)))

    out["_patient_days"] = days.where(days > 0)
    out["_ddd_total"] = np.where(
        rate.notna() & out["_patient_days"].notna(),
        rate * out["_patient_days"] / DDD_MULTIPLIER,
        np.nan)
    out["_rate_usable"] = out["_ddd_total"].notna() & out["_patient_days"].notna()
    return out


def pooled_ddd(amu_df: pd.DataFrame, by: Optional[str] = None) -> PooledRate:
    """DDD per 1,000 patient-days, pooled over the group."""
    prepared = prepare_amu(amu_df)
    if prepared.empty:
        return PooledRate(pd.DataFrame(), 0, 0, 0.0, 0.0)

    usable = prepared[prepared["_rate_usable"]]
    total_ddd = float(usable["_ddd_total"].sum()) if not usable.empty else 0.0
    total_days = float(usable["_patient_days"].sum()) if not usable.empty else 0.0

    if by and by in prepared.columns:
        rows: List[Dict[str, object]] = []
        for group, chunk in prepared.groupby(by, dropna=False):
            contributing = chunk[chunk["_rate_usable"]]
            ddd = float(contributing["_ddd_total"].sum())
            days = float(contributing["_patient_days"].sum())
            rows.append({
                by: "Not recorded" if pd.isna(group) else str(group),
                "records": int(len(chunk)),
                "records_with_denominator": int(len(contributing)),
                "ddd_total": ddd,
                "patient_days": days,
                "ddd_per_1000_patient_days": (
                    ddd / days * DDD_MULTIPLIER if days > 0 else None),
                "quantity_dispensed": float(
                    _numeric(chunk.get("quantity_dispensed",
                                       pd.Series(dtype=float))).sum()),
            })
        table = (pd.DataFrame(rows)
                 .sort_values("ddd_per_1000_patient_days",
                              ascending=False, na_position="last")
                 .reset_index(drop=True))
    else:
        table = pd.DataFrame([{
            "records": int(len(prepared)),
            "records_with_denominator": int(len(usable)),
            "ddd_total": total_ddd,
            "patient_days": total_days,
            "ddd_per_1000_patient_days": (
                total_ddd / total_days * DDD_MULTIPLIER if total_days > 0 else None),
        }])

    return PooledRate(table, int(len(prepared)), int(len(usable)),
                      total_ddd, total_days)


def naive_vs_pooled_amu(amu_df: pd.DataFrame, by: str) -> pd.DataFrame:
    """The mean-of-rates beside the pooled rate.

    Kept so the difference can be seen rather than asserted. Where reporting
    volume varies between groups -- which nationally it always does -- the two
    disagree, and the mean of rates is the one that has no denominator behind
    it.
    """
    prepared = prepare_amu(amu_df)
    if prepared.empty or by not in prepared.columns:
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    for group, chunk in prepared.groupby(by, dropna=False):
        contributing = chunk[chunk["_rate_usable"]]
        ddd = float(contributing["_ddd_total"].sum())
        days = float(contributing["_patient_days"].sum())
        naive = _numeric(chunk.get("ddd_per_1000", pd.Series(dtype=float))).mean()
        pooled = ddd / days * DDD_MULTIPLIER if days > 0 else None
        rows.append({
            by: "Not recorded" if pd.isna(group) else str(group),
            "mean_of_reported_rates": None if pd.isna(naive) else float(naive),
            "pooled_rate": pooled,
            "difference": (None if pooled is None or pd.isna(naive)
                           else float(naive) - pooled),
            "records": int(len(chunk)),
        })
    return pd.DataFrame(rows).sort_values("records", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# AMC
# ---------------------------------------------------------------------------

def prepare_amc(amc_df: pd.DataFrame) -> pd.DataFrame:
    """Add the active-ingredient numerator in milligrams.

    ``quantity_kg`` is taken to be active-ingredient mass. Where a submission
    reports product mass instead, this overstates consumption; the conversion is
    stated in the metric dictionary so the assumption is visible rather than
    buried.
    """
    if amc_df is None or amc_df.empty:
        return pd.DataFrame()

    out = amc_df.copy()
    quantity = _numeric(out.get("quantity_kg", pd.Series(dtype=float)))
    biomass = _numeric(out.get("biomass_kg", pd.Series(dtype=float)))

    out["_active_mg"] = quantity * MG_PER_KG
    out["_biomass_kg"] = biomass.where(biomass > 0)
    out["_rate_usable"] = out["_active_mg"].notna() & out["_biomass_kg"].notna()
    return out


def pooled_mg_per_kg(amc_df: pd.DataFrame, by: Optional[str] = None) -> PooledRate:
    """Milligrams of active ingredient per kilogram of biomass, pooled."""
    prepared = prepare_amc(amc_df)
    if prepared.empty:
        return PooledRate(pd.DataFrame(), 0, 0, 0.0, 0.0)

    usable = prepared[prepared["_rate_usable"]]
    total_mg = float(usable["_active_mg"].sum()) if not usable.empty else 0.0
    total_kg = float(usable["_biomass_kg"].sum()) if not usable.empty else 0.0

    if by and by in prepared.columns:
        rows: List[Dict[str, object]] = []
        for group, chunk in prepared.groupby(by, dropna=False):
            contributing = chunk[chunk["_rate_usable"]]
            mg = float(contributing["_active_mg"].sum())
            kg = float(contributing["_biomass_kg"].sum())
            rows.append({
                by: "Not recorded" if pd.isna(group) else str(group),
                "records": int(len(chunk)),
                "records_with_denominator": int(len(contributing)),
                "active_ingredient_kg": mg / MG_PER_KG,
                "biomass_kg": kg,
                "mg_per_kg_biomass": (mg / kg) if kg > 0 else None,
            })
        table = (pd.DataFrame(rows)
                 .sort_values("mg_per_kg_biomass", ascending=False,
                              na_position="last")
                 .reset_index(drop=True))
    else:
        table = pd.DataFrame([{
            "records": int(len(prepared)),
            "records_with_denominator": int(len(usable)),
            "active_ingredient_kg": total_mg / MG_PER_KG,
            "biomass_kg": total_kg,
            "mg_per_kg_biomass": (total_mg / total_kg) if total_kg > 0 else None,
        }])

    return PooledRate(table, int(len(prepared)), int(len(usable)),
                      total_mg, total_kg)


def naive_vs_pooled_amc(amc_df: pd.DataFrame, by: str) -> pd.DataFrame:
    """The mean-of-ratios beside the pooled ratio, for AMC."""
    prepared = prepare_amc(amc_df)
    if prepared.empty or by not in prepared.columns:
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    for group, chunk in prepared.groupby(by, dropna=False):
        contributing = chunk[chunk["_rate_usable"]]
        mg = float(contributing["_active_mg"].sum())
        kg = float(contributing["_biomass_kg"].sum())
        naive = _numeric(chunk.get("mg_per_kg_biomass",
                                   pd.Series(dtype=float))).mean()
        pooled = (mg / kg) if kg > 0 else None
        rows.append({
            by: "Not recorded" if pd.isna(group) else str(group),
            "mean_of_reported_ratios": None if pd.isna(naive) else float(naive),
            "pooled_ratio": pooled,
            "difference": (None if pooled is None or pd.isna(naive)
                           else float(naive) - pooled),
            "records": int(len(chunk)),
        })
    return pd.DataFrame(rows).sort_values("records", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Denominator coverage
# ---------------------------------------------------------------------------

def denominator_coverage(amu_df: Optional[pd.DataFrame] = None,
                         amc_df: Optional[pd.DataFrame] = None
                         ) -> pd.DataFrame:
    """How much of the submitted data can support a normalised rate at all.

    The review asked for missing denominators to be reported rather than
    absorbed. Without patient-days, antimicrobial use can only be described as a
    volume, and volumes are not comparable between facilities.
    """
    rows: List[Dict[str, object]] = []

    if amu_df is not None and not amu_df.empty:
        prepared = prepare_amu(amu_df)
        total = len(prepared)
        rows.append({
            "Dataset": "Antimicrobial use (human)",
            "Records": total,
            "With a usable denominator": int(prepared["_rate_usable"].sum()),
            "Percent": 100 * prepared["_rate_usable"].sum() / total if total else None,
            "Denominator": "Patient-days",
            "Consequence if missing": "Use can be reported as a volume only, "
                                      "and volumes cannot be compared between "
                                      "facilities or regions.",
        })

    if amc_df is not None and not amc_df.empty:
        prepared = prepare_amc(amc_df)
        total = len(prepared)
        rows.append({
            "Dataset": "Antimicrobial consumption (animal)",
            "Records": total,
            "With a usable denominator": int(prepared["_rate_usable"].sum()),
            "Percent": 100 * prepared["_rate_usable"].sum() / total if total else None,
            "Denominator": "Biomass at risk, kg",
            "Consequence if missing": "Consumption can be reported as a mass "
                                      "only, which reflects herd size as much "
                                      "as prescribing.",
        })

    return pd.DataFrame(rows)


__all__ = [
    "DDD_MULTIPLIER", "MG_PER_KG", "ConsumptionMetric", "METRICS",
    "metrics_frame", "PooledRate",
    "prepare_amu", "pooled_ddd", "naive_vs_pooled_amu",
    "prepare_amc", "pooled_mg_per_kg", "naive_vs_pooled_amc",
    "denominator_coverage",
]
