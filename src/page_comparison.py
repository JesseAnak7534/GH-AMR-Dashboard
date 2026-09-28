"""
Comparison page: resistance between groups, on one denominator.

What this replaces
------------------
Six comparison modes -- Category, Time Period, Source Type, Multi-Parameter,
Cross-Variable and Custom -- spread over a thousand lines. Five of them were the
same operation with a different grouping column, and the sixth split on time
instead. None deduplicated to one isolate per patient, none counted isolates
rather than susceptibility tests, none carried a confidence interval, and none
withheld a percentage when the groups were too small to support one. So the page
would happily report that one region was 12 points worse than another on
fourteen tests.

One tool does all six jobs: choose what to compare across, choose the groups,
and get counts, pooled rates, intervals and an explicit statement of whether the
difference is distinguishable from sampling variation.

Comparing is where surveillance data misleads most easily, so the guard rails
are tighter here than elsewhere: sectors are never pooled, small groups keep
their counts and lose their percentages, and two groups whose intervals overlap
are described as not distinguishable rather than ranked.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src import expert_rules
from src import surveillance as sv

ALL = "__all__"

#: What a comparison can be made across. Time is handled separately because it
#: splits one population rather than contrasting two.
COMPARISON_DIMENSIONS: Dict[str, str] = {
    "Laboratory": "lab_name",
    "Region": "region",
    "District": "district",
    "Ward type": "ward_type_at_collection",
    "Specimen type": "specimen_type",
    "Age band": "age_band_at_collection",
    "Sex": "sex",
    "Patient type": "patient_type",
    "Sampling purpose": "sampling_purpose",
    "Organism": "organism",
    "Facility": "facility_code",
}


def _format_percent(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}%"


def _interval(low, high) -> str:
    if low is None or high is None or pd.isna(low) or pd.isna(high):
        return "—"
    return f"{low:.1f} – {high:.1f}"


def _intervals_overlap(a: pd.Series, b: pd.Series) -> Optional[bool]:
    """Whether two Wilson intervals overlap.

    Not a hypothesis test. Non-overlapping intervals are strong evidence of a
    real difference; overlapping ones do not prove absence of one. Both are
    stated in those terms rather than as a verdict.
    """
    for row in (a, b):
        if pd.isna(row.get("ci_low")) or pd.isna(row.get("ci_high")):
            return None
    return not (a["ci_high"] < b["ci_low"] or b["ci_high"] < a["ci_low"])


def _comparison_table(table: pd.DataFrame, column: str, label: str,
                      value_column: str) -> pd.DataFrame:
    percent_label = ("% non-susceptible" if value_column == "percent_non_susceptible"
                     else "% susceptible")
    unit = "Observations" if "observations" in table.columns else "Isolates tested"
    unit_column = "observations" if "observations" in table.columns else "tested"
    out = {
        label: table[column],
        unit: table[unit_column],
        percent_label: table[value_column].map(_format_percent),
        "95% CI": [_interval(lo, hi)
                   for lo, hi in zip(table["ci_low"], table["ci_high"])],
    }
    if "isolates" in table.columns:
        out["Isolates"] = table["isolates"]
    if "distinct_pairs" in table.columns:
        out["Organism–agent pairs"] = table["distinct_pairs"]
    out["Status"] = table["status"]
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Comparison across a dimension
# ---------------------------------------------------------------------------

def _compare_groups(frame: pd.DataFrame) -> None:
    available = [name for name, column in COMPARISON_DIMENSIONS.items()
                 if column in frame.columns]
    if not available:
        st.info("No comparable dimension is present in this data.")
        return

    left, middle, right = st.columns(3)
    with left:
        dimension = st.selectbox("Compare across", available, key="cmp_dim")
    column = COMPARISON_DIMENSIONS[dimension]

    organisms = sorted(frame["organism"].dropna().unique())
    with middle:
        organism = st.selectbox(
            "Organism", [ALL] + organisms,
            format_func=lambda o: "All organisms" if o == ALL else o,
            key="cmp_org")
    scope = frame if organism == ALL else frame[frame["organism"] == organism]
    agents = sorted(scope["antibiotic"].dropna().unique())
    with right:
        antibiotic = st.selectbox(
            "Antibiotic", [ALL] + agents,
            format_func=lambda a: "All antibiotics" if a == ALL else a,
            key="cmp_abx")

    pooled = organism == ALL or antibiotic == ALL
    chosen_organism = None if organism == ALL else organism
    chosen_antibiotic = None if antibiotic == ALL else antibiotic

    if pooled:
        table = sv.stratified_resistance(
            frame, by=column, organism=chosen_organism,
            antibiotic=chosen_antibiotic)
        value_column = "percent_non_susceptible"
        st.caption(
            "Pooled across organism–agent pairs, so the unit is one isolate "
            "tested against one agent and the figure depends on which agents "
            "each group tested. Compare groups only where the pair counts are "
            "similar. Choosing one organism and one agent gives a clinically "
            "usable figure instead."
        )
    else:
        table = sv.stratified_susceptibility(
            frame, by=column, organism=chosen_organism,
            antibiotic=chosen_antibiotic)
        value_column = "percent_susceptible"
        st.caption(
            "One isolate per patient per organism, deduplicated to CLSI M39. "
            f"Percentages are withheld below {sv.MIN_ISOLATES_FOR_REPORTING} "
            "isolates; the counts are still shown."
        )

    if table.empty:
        st.info("No data for that combination.")
        return

    st.dataframe(_comparison_table(table, column, dimension, value_column),
                 use_container_width=True, hide_index=True)

    reportable = table[table["status"] == sv.STATUS_REPORTED]
    if reportable.empty:
        st.warning(
            "No group reaches the reporting threshold, so no comparison can be "
            "made. The counts above are real; a percentage computed on them "
            "would not be dependable."
        )
        return

    figure = px.bar(
        reportable, x=column, y=value_column,
        error_y=reportable["ci_high"] - reportable[value_column],
        error_y_minus=reportable[value_column] - reportable["ci_low"],
        labels={column: dimension,
                value_column: ("% non-susceptible" if pooled else "% susceptible")},
    )
    figure.update_layout(yaxis_range=[0, 100], margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(figure, use_container_width=True)

    _head_to_head(reportable, column, dimension, value_column,
                  key_prefix="cmp_groups")


def _head_to_head(reportable: pd.DataFrame, column: str, dimension: str,
                  value_column: str, key_prefix: str) -> None:
    """Two named groups, with an explicit statement about the difference.

    ``key_prefix`` keeps the two callers' widgets distinct. Both tabs render in
    the same pass, so sharing a key makes Streamlit raise on a duplicate.
    """
    if len(reportable) < 2:
        return

    st.markdown("##### Two groups, side by side")
    options = reportable[column].tolist()
    left, right = st.columns(2)
    with left:
        first = st.selectbox("First", options, index=0,
                             key=f"{key_prefix}_a")
    with right:
        second = st.selectbox("Second", options,
                              index=1 if len(options) > 1 else 0,
                              key=f"{key_prefix}_b")
    if first == second:
        st.caption("Choose two different groups.")
        return

    a = reportable[reportable[column] == first].iloc[0]
    b = reportable[reportable[column] == second].iloc[0]
    difference = a[value_column] - b[value_column]
    overlap = _intervals_overlap(a, b)

    one, two, three = st.columns(3)
    one.metric(str(first), _format_percent(a[value_column]),
               help=f"95% CI {_interval(a['ci_low'], a['ci_high'])}")
    two.metric(str(second), _format_percent(b[value_column]),
               help=f"95% CI {_interval(b['ci_low'], b['ci_high'])}")
    three.metric("Difference", f"{difference:+.1f} points")

    if overlap is None:
        st.info("One of the groups has no interval, so the difference cannot be "
                "assessed.")
    elif overlap:
        st.warning(
            f"The 95% intervals of {first} and {second} overlap, so this "
            f"{abs(difference):.1f}-point difference is not distinguishable "
            "from sampling variation at these sample sizes. Reporting it as a "
            "difference between the two groups would not be supportable."
        )
    else:
        st.success(
            f"The 95% intervals of {first} and {second} do not overlap, which "
            f"is strong evidence that the {abs(difference):.1f}-point "
            "difference is real. It does not explain why: case mix, specimen "
            "mix and testing practice differ between groups and are not "
            "adjusted for here."
        )


# ---------------------------------------------------------------------------
# Comparison over time
# ---------------------------------------------------------------------------

def _compare_periods(frame: pd.DataFrame) -> None:
    if frame.empty or "collection_datetime" not in frame.columns:
        st.info("No collection dates, so periods cannot be compared.")
        return

    collected = frame["collection_datetime"].dropna()
    if collected.empty:
        st.info("No collection dates recorded.")
        return

    earliest, latest = collected.min().date(), collected.max().date()
    st.caption(f"Specimens run from {earliest} to {latest}.")

    left, middle, right = st.columns(3)
    with left:
        months = st.selectbox("Period length", [3, 6, 12],
                              index=2, format_func=lambda m: f"{m} months",
                              key="cmp_months")
    organisms = sorted(frame["organism"].dropna().unique())
    with middle:
        organism = st.selectbox(
            "Organism", [ALL] + organisms,
            format_func=lambda o: "All organisms" if o == ALL else o,
            key="cmp_t_org")
    scope = frame if organism == ALL else frame[frame["organism"] == organism]
    agents = sorted(scope["antibiotic"].dropna().unique())
    with right:
        antibiotic = st.selectbox(
            "Antibiotic", [ALL] + agents,
            format_func=lambda a: "All antibiotics" if a == ALL else a,
            key="cmp_t_abx")

    window = pd.Timedelta(days=int(30.44 * months))
    boundary = collected.max() - window
    baseline_start = boundary - window

    recent = frame[frame["collection_datetime"] > boundary].copy()
    baseline = frame[(frame["collection_datetime"] > baseline_start)
                     & (frame["collection_datetime"] <= boundary)].copy()
    recent["_period"] = f"Most recent {months} months"
    baseline["_period"] = f"Preceding {months} months"
    combined = pd.concat([baseline, recent], ignore_index=True)

    if combined.empty:
        st.info("No specimens in either period.")
        return

    pooled = organism == ALL or antibiotic == ALL
    chosen_organism = None if organism == ALL else organism
    chosen_antibiotic = None if antibiotic == ALL else antibiotic

    if pooled:
        table = sv.stratified_resistance(
            combined, by="_period", organism=chosen_organism,
            antibiotic=chosen_antibiotic)
        value_column = "percent_non_susceptible"
    else:
        table = sv.stratified_susceptibility(
            combined, by="_period", organism=chosen_organism,
            antibiotic=chosen_antibiotic)
        value_column = "percent_susceptible"

    if table.empty:
        st.info("No data in these periods for that combination.")
        return

    st.dataframe(_comparison_table(table, "_period", "Period", value_column),
                 use_container_width=True, hide_index=True)

    reportable = table[table["status"] == sv.STATUS_REPORTED]
    if len(reportable) < 2:
        st.warning(
            "Both periods need at least "
            f"{sv.MIN_ISOLATES_FOR_REPORTING} isolates before a change can be "
            "reported. A change measured against a period that was too small to "
            "report is not a change, it is noise."
        )
        return
    _head_to_head(reportable, "_period", "Period", value_column,
                  key_prefix="cmp_periods")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_comparison_page() -> None:
    st.header("Comparative Analysis")
    st.caption(
        "Resistance between groups, on one denominator, with the uncertainty "
        "shown. Comparing is where surveillance data misleads most easily, so "
        "small groups keep their counts and lose their percentages, and two "
        "groups whose intervals overlap are described as not distinguishable "
        "rather than ranked."
    )

    dataset_id = st.session_state.get("active_dataset_id")

    try:
        counts = _sector_counts(dataset_id)
    except Exception as exc:                          # noqa: BLE001
        st.error(f"Could not load the surveillance data: {exc}")
        return

    if not counts:
        st.info(
            "No isolates in the traceability chain yet. Upload data using the "
            "current template on **Upload & Data Quality**."
        )
        return

    sector = st.selectbox(
        "Sector", list(counts),
        format_func=lambda s: f"{s.title()} — {counts[s]:,} isolates",
        key="cmp_sector",
        help="Sectors are compared separately. A human clinical culture and a "
             "wastewater grab are not interchangeable observations, so the "
             "platform will not pool them into one comparison.")

    frame = sv.load_surveillance_frame(dataset_id=dataset_id, sector=sector)
    if frame.empty:
        st.info("No susceptibility results for that sector.")
        return

    # Impossible combinations would otherwise distort every group they land in.
    frame, findings = expert_rules.drop_unreportable(frame)
    if not findings.empty:
        st.caption(
            f"{len(findings)} organism–agent pair(s) were excluded as "
            "unreportable before comparing. See **Data Coverage & Quality**."
        )

    groups, periods = st.tabs(["Between groups", "Over time"])
    with groups:
        _compare_groups(frame)
    with periods:
        _compare_periods(frame)


@st.cache_data(ttl=300, show_spinner=False)
def _sector_counts(dataset_id: Optional[str]) -> Dict[str, int]:
    frame = sv.load_surveillance_frame(dataset_id=dataset_id)
    if frame.empty:
        return {}
    isolates = frame.drop_duplicates(subset=["dataset_id", "isolate_id"])
    return {str(k): int(v) for k, v in
            isolates.groupby("sector", dropna=True).size().items()}


__all__ = ["render_comparison_page"]
