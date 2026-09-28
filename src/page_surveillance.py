"""
Surveillance analysis page: pathogen distribution, cumulative antibiograms and
clinical stratification.

This is where the traceability chain becomes visible. Every figure on the page
counts isolates, states the period it covers, says whether deduplication was
applied and what it removed, and refuses to print a percentage it cannot
support.

The sector selector is not a convenience. Pooling a human blood culture, a farm
sampling round and a wastewater grab into one resistance percentage produces a
number that describes no population, so the page requires one sector to be
chosen and the analytics refuse to run across several.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from src import expert_rules, surveillance as sv

_SECTOR_LABELS = {
    "human": "Human clinical",
    "animal": "Animal",
    "food": "Food",
    "environment": "Environment",
    "aquaculture": "Aquaculture",
}

_STATUS_NOTE = {
    sv.STATUS_REPORTED: "",
    sv.STATUS_SUPPRESSED: (
        f"fewer than {sv.MIN_ISOLATES_FOR_REPORTING} isolates, so the "
        "percentage is withheld"),
    sv.STATUS_NO_DATA: "no tested isolates",
}


# ---------------------------------------------------------------------------
# Small presentation helpers
# ---------------------------------------------------------------------------

def _as_of(frame: pd.DataFrame) -> None:
    """State how current the data is, beside the figures drawn from it.

    The review found a headline tile reading "182d ago" with nothing to indicate
    that this mattered for a surveillance system.
    """
    if frame.empty or "collection_datetime" not in frame.columns:
        return
    collected = frame["collection_datetime"].dropna()
    if collected.empty:
        st.caption("No collection dates recorded, so currency cannot be judged.")
        return
    latest = collected.max()
    earliest = collected.min()
    days = int((pd.Timestamp.now(tz="UTC") - latest).days)
    freshness = ("current" if days <= 31 else
                 "lagging" if days <= 92 else "stale")
    st.caption(
        f"Specimens collected {earliest.date()} to {latest.date()}. "
        f"Most recent specimen is {days} days old ({freshness})."
    )


def _format_percent(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}%"


def _susceptibility_table(table: pd.DataFrame,
                          label_column: str) -> pd.DataFrame:
    """Render a susceptibility table with counts, interval and a stated reason
    wherever a percentage is absent."""
    display = pd.DataFrame({
        label_column: table[label_column],
        "Isolates tested": table["tested"],
        "S": table["susceptible"],
        "I": table["intermediate"],
        "R / NS": table["resistant"],
        "% susceptible": table["percent_susceptible"].map(_format_percent),
        "95% CI": [
            "—" if pd.isna(lo) or pd.isna(hi) else f"{lo:.1f} – {hi:.1f}"
            for lo, hi in zip(table["ci_low"], table["ci_high"])
        ],
        "Why not reported": [_STATUS_NOTE.get(s, "") for s in table["status"]],
    })
    return display


def _provenance_block(provenance: Dict[str, object]) -> None:
    """Show how the table above was produced. A table without this is not
    auditable, which was the review's objection to the previous antibiogram."""
    with st.expander("How this table was produced", expanded=False):
        period = "not determined"
        if provenance.get("period_start") and provenance.get("period_end"):
            period = (f"{provenance['period_start']} to "
                      f"{provenance['period_end']}")
        rows = [
            ("Analysis period", period),
            ("Sectors included", ", ".join(provenance.get("sectors") or []) or "none"),
            ("Deduplication", provenance.get("deduplication_summary", "not applied")),
            ("Reporting threshold",
             f"{provenance.get('min_isolates')} isolates; below this the count "
             "is shown and the percentage withheld"),
            ("QC failures excluded",
             f"{provenance.get('qc_failures_excluded', 0)} result(s) from runs "
             "whose quality control failed"),
            ("Organism-agent pairs",
             f"{provenance.get('pairs_total', 0)} present, "
             f"{provenance.get('pairs_reportable', 0)} reportable"),
        ]
        for name, value in rows:
            st.markdown(f"**{name}.** {value}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def _tab_distribution(frame: pd.DataFrame) -> None:
    st.subheader("Pathogen distribution")
    st.caption(
        "Counted on isolates. One organism recovered from one specimen is one "
        "isolate, however many agents were tested against it."
    )

    strata = ["(none)"] + [
        name for name, column in sv.STRATIFICATIONS.items()
        if column in frame.columns and column != "organism"
    ]
    choice = st.selectbox("Break down by", strata, key="sv_dist_by")
    by = None if choice == "(none)" else sv.STRATIFICATIONS[choice]

    table = sv.pathogen_distribution(frame, by=by, top=15 if by else None)
    if table.empty:
        st.info("No isolates in scope.")
        return

    if by is None:
        total = int(table["isolates"].sum())
        st.metric("Isolates", f"{total:,}")
        figure = px.bar(
            table.head(20), x="isolates", y="organism", orientation="h",
            labels={"isolates": "Isolates", "organism": ""},
            text="isolates",
        )
        figure.update_layout(height=max(320, 26 * min(len(table), 20)),
                            yaxis={"categoryorder": "total ascending"},
                            margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(figure, use_container_width=True)
        st.dataframe(
            table.assign(percent=table["percent"].map(_format_percent))
                 .rename(columns={"organism": "Organism", "isolates": "Isolates",
                                  "percent": "Share"}),
            use_container_width=True, hide_index=True)
    else:
        labelled = table.copy()
        labelled[by] = labelled[by].fillna("Not recorded").replace(
            {"Unknown": "Not recorded"})
        figure = px.bar(labelled, x="isolates", y=by, color="organism",
                        orientation="h", labels={"isolates": "Isolates", by: ""})
        figure.update_layout(height=max(360, 30 * labelled[by].nunique()),
                            margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(figure, use_container_width=True)

        if labelled[by].nunique() == 1 and labelled[by].iloc[0] == "Not recorded":
            st.warning(
                f"Every isolate reads 'Not recorded' for {choice.lower()}. The "
                "field exists in the data model but nothing has been collected "
                "into it yet, so this breakdown cannot say anything. See "
                "**Data Coverage & Quality** for which fields are populated."
            )
        st.dataframe(labelled.rename(columns={"organism": "Organism",
                                              "isolates": "Isolates"}),
                     use_container_width=True, hide_index=True)


def _tab_antibiogram(frame: pd.DataFrame) -> None:
    st.subheader("Cumulative antibiogram")
    st.caption(
        "Deduplicated to the first isolate of each organism per subject per "
        "period, following CLSI M39. Percentages are withheld below "
        f"{sv.MIN_ISOLATES_FOR_REPORTING} isolates."
    )

    left, right, third = st.columns(3)
    with left:
        window = st.selectbox(
            "Analysis period", ["12 months", "24 months", "All available"],
            key="sv_ab_period")
    with right:
        deduplicate = st.checkbox(
            "Apply CLSI M39 deduplication", value=True, key="sv_ab_dedup",
            help="Keeps the first isolate of each organism per subject. Without "
                 "it, a patient cultured repeatedly counts several times and "
                 "the table shifts towards the most heavily treated patients.")
    with third:
        screen = st.checkbox(
            "Exclude combinations that cannot be reported", value=True,
            key="sv_ab_screen",
            help="Removes organism-agent pairs where susceptibility is "
                 "biologically impossible or clinically unreportable.")

    months = {"12 months": 12, "24 months": 24, "All available": None}[window]

    working = frame
    findings = pd.DataFrame()
    if screen:
        working, findings = expert_rules.drop_unreportable(working)

    table, provenance = sv.cumulative_antibiogram(
        working, deduplicate=deduplicate, period_months=months)

    if table.empty:
        st.info("No susceptibility results in scope for this period.")
        _provenance_block(provenance)
        return

    reportable = table[table["status"] == sv.STATUS_REPORTED]
    a, b, c = st.columns(3)
    a.metric("Organism–agent pairs", f"{len(table):,}")
    b.metric("Reportable", f"{len(reportable):,}",
             help=f"At least {sv.MIN_ISOLATES_FOR_REPORTING} isolates tested")
    c.metric("Subjects", f"{provenance.get('patients', 0):,}")

    if reportable.empty:
        st.warning(
            "No organism–agent pair reaches the "
            f"{sv.MIN_ISOLATES_FOR_REPORTING}-isolate reporting threshold for "
            "this period and sector. That is a statement about the volume of "
            "data, not about resistance: the counts below are real, but a "
            "percentage computed on them would not be dependable. Widening the "
            "period or accumulating more submissions is what changes it."
        )

    st.markdown("##### Reportable pairs")
    if reportable.empty:
        st.caption("None.")
    else:
        st.dataframe(
            _susceptibility_table(reportable.sort_values(
                ["organism", "antibiotic"]), "organism")
            .rename(columns={"organism": "Organism"})
            .assign(Antibiotic=reportable.sort_values(
                ["organism", "antibiotic"])["antibiotic"].values),
            use_container_width=True, hide_index=True)

    with st.expander(f"Pairs below the reporting threshold "
                     f"({int((table['status'] == sv.STATUS_SUPPRESSED).sum())})"):
        suppressed = table[table["status"] == sv.STATUS_SUPPRESSED]
        if suppressed.empty:
            st.caption("None.")
        else:
            st.caption(
                "Counts are shown; percentages are withheld. A rate on a "
                "handful of isolates invites a decision the data cannot carry."
            )
            st.dataframe(
                suppressed[["organism", "antibiotic", "tested", "susceptible",
                            "intermediate", "resistant"]]
                .rename(columns={"organism": "Organism",
                                 "antibiotic": "Antibiotic",
                                 "tested": "Isolates tested",
                                 "susceptible": "S", "intermediate": "I",
                                 "resistant": "R / NS"}),
                use_container_width=True, hide_index=True)

    if not findings.empty:
        errors = findings[findings["severity"] == expert_rules.SEVERITY_ERROR]
        with st.expander(
                f"Excluded as unreportable ({len(findings)} pairs)"):
            st.caption(
                "Combinations removed before the table was built. An 'error' is "
                "biologically impossible and indicates a data problem; a "
                "'suppress' is real in vitro but must not guide treatment."
            )
            st.dataframe(
                findings.rename(columns={
                    "organism": "Organism", "antibiotic": "Antibiotic",
                    "severity": "Kind", "observations": "Results",
                    "reported_susceptible": "Reported S", "reason": "Reason"}),
                use_container_width=True, hide_index=True)
            if not errors.empty and errors["reported_susceptible"].sum():
                st.error(
                    f"{int(errors['reported_susceptible'].sum())} result(s) "
                    "record susceptibility for a combination where that is not "
                    "biologically possible. These are data-entry or "
                    "identification errors and should be corrected at source."
                )

    _provenance_block(provenance)


def _tab_stratified(frame: pd.DataFrame) -> None:
    st.subheader("Susceptibility by stratum")
    st.caption(
        "An overall percentage can describe no one. The same organism and agent "
        "may be 80% susceptible in outpatients and 30% in intensive care, and "
        "the average of those is not a clinical fact about either."
    )

    working, _ = expert_rules.drop_unreportable(frame)
    if working.empty:
        st.info("No reportable results in scope.")
        return

    organisms = sorted(working["organism"].dropna().unique())
    if not organisms:
        st.info("No organisms in scope.")
        return

    left, middle, right = st.columns(3)
    with left:
        organism = st.selectbox("Organism", organisms, key="sv_st_org")
    agents = sorted(working.loc[working["organism"] == organism,
                                "antibiotic"].dropna().unique())
    with middle:
        antibiotic = st.selectbox("Antibiotic", agents, key="sv_st_abx")
    available = [name for name, column in sv.STRATIFICATIONS.items()
                 if column in working.columns and column != "organism"]
    with right:
        stratum = st.selectbox("Break down by", available, key="sv_st_by")

    column = sv.STRATIFICATIONS[stratum]
    table = sv.stratified_susceptibility(working, by=column, organism=organism,
                                        antibiotic=antibiotic)
    if table.empty:
        st.info("No isolates for that combination.")
        return

    st.dataframe(_susceptibility_table(table, column)
                 .rename(columns={column: stratum}),
                 use_container_width=True, hide_index=True)

    reported = table[table["status"] == sv.STATUS_REPORTED]
    if len(reported) >= 2:
        figure = px.bar(reported, x=column, y="percent_susceptible",
                        error_y=reported["ci_high"] - reported["percent_susceptible"],
                        error_y_minus=reported["percent_susceptible"] - reported["ci_low"],
                        labels={column: stratum,
                                "percent_susceptible": "% susceptible"})
        figure.update_layout(yaxis_range=[0, 100],
                            margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(figure, use_container_width=True)
        st.caption("Bars carry 95% Wilson intervals. Overlapping intervals mean "
                   "the strata are not distinguishable at this sample size.")
    elif len(table):
        only = table.iloc[0]
        if str(only[column]) == "Not recorded":
            st.warning(
                f"Every isolate reads 'Not recorded' for {stratum.lower()}, so "
                "this breakdown has one group and tells you nothing about it. "
                "The field is in the data model; it has not been collected. "
                "**Data Coverage & Quality** lists which fields are populated."
            )
        else:
            st.info(
                "Only one stratum reaches the reporting threshold, so there is "
                "nothing to compare against."
            )

    # Infection-prevention view: high-acuity wards against the rest.
    comparison = sv.high_acuity_comparison(working, organism=organism,
                                           antibiotic=antibiotic)
    if not comparison.empty and comparison["ward_group"].nunique() > 1:
        st.markdown("##### High-acuity wards compared with the rest")
        st.caption(
            "ICU, neonatal, surgical, burns and haemato-oncology wards, where "
            "device- and procedure-associated infection concentrates."
        )
        st.dataframe(_susceptibility_table(comparison, "ward_group")
                     .rename(columns={"ward_group": "Ward group"}),
                     use_container_width=True, hide_index=True)


def _tab_dictionary() -> None:
    st.subheader("Metric dictionary")
    st.caption(
        "What each figure on this page means, how it is calculated, and what it "
        "must not be used for. The review asked for this to be frozen and "
        "published rather than implied."
    )
    st.dataframe(sv.metric_dictionary_frame(), use_container_width=True,
                 hide_index=True)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_surveillance_page() -> None:
    st.header("Surveillance Analysis")
    st.caption(
        "Isolate-level analysis over the traceability chain, with CLSI M39 "
        "deduplication and explicit reporting thresholds."
    )

    dataset_id = st.session_state.get("active_dataset_id")

    # Sector first. The analytics refuse to pool sectors, so the page asks
    # rather than silently picking one.
    counts = _sector_counts(dataset_id)
    if not counts:
        st.info(
            "No isolates in the traceability chain yet. Upload data using the "
            "current template on **Upload & Data Quality**, and it will appear "
            "here linked to its specimen, ward and patient."
        )
        return

    options = [s for s in _SECTOR_LABELS if s in counts]
    labels = {s: f"{_SECTOR_LABELS[s]} — {counts[s]:,} isolates" for s in options}
    sector = st.selectbox(
        "Sector", options, format_func=lambda s: labels[s], key="sv_sector",
        help="Sectors are analysed separately. A human clinical culture, a farm "
             "sampling round and a wastewater grab are not interchangeable "
             "observations, so the platform will not pool them into one rate.",
    )

    frame = sv.load_surveillance_frame(dataset_id=dataset_id, sector=sector)
    if frame.empty:
        st.info("No susceptibility results for that sector.")
        return

    _as_of(frame)

    distribution, antibiogram, stratified, dictionary = st.tabs([
        "Pathogen distribution", "Cumulative antibiogram",
        "By ward, specimen and age", "Metric dictionary",
    ])
    with distribution:
        _tab_distribution(frame)
    with antibiogram:
        _tab_antibiogram(frame)
    with stratified:
        _tab_stratified(frame)
    with dictionary:
        _tab_dictionary()


@st.cache_data(ttl=300, show_spinner=False)
def _sector_counts(dataset_id: Optional[str]) -> Dict[str, int]:
    """Isolates per sector, for the selector."""
    frame = sv.load_surveillance_frame(dataset_id=dataset_id)
    if frame.empty:
        return {}
    isolates = frame.drop_duplicates(subset=["dataset_id", "isolate_id"])
    return {str(k): int(v) for k, v in
            isolates.groupby("sector", dropna=True).size().items()}


__all__ = ["render_surveillance_page"]
