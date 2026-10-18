"""
Public landing page.

What an anonymous visitor sees, and the only page written on the assumption
that the reader has no account, no briefing and no obligation to stay. It has
to answer three questions in the first screen -- what this is, what the data
says, and how much of it there is -- before offering anything to explore.

Two rules shape everything on it.

**Nothing identifies a person.** No patient pseudonym, no specimen identifier,
no record-level row, and every count passes through
``src.disclosure`` before it is drawn. That module exists because the risk here
is not the headline figures but the filtering: a visitor who narrows by ward,
organism, region and period can reach a cell holding one patient, and each
filter is another attribute attached to them. Counts below the threshold are
withheld, rates computed over withheld counts go with them, and a second cell
goes when the first could be recovered by subtracting the rest from the total.

**Nothing is stated more confidently than the data supports.** Rates carry their
denominator and a confidence interval. A figure resting on too few isolates is
withheld rather than drawn faintly. The coverage note at the foot is not a
disclaimer; it is the part that lets a reader judge everything above it.

Laboratory identity is shown deliberately. It is in the data, attribution is the
point of sentinel surveillance, and a rate nobody can attribute is a rate nobody
can act on.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from src import disclosure, surveillance as sv

_SECTOR_COLOUR = {
    "human": "#0e7490",
    "animal": "#b45309",
    "food": "#15803d",
    "environment": "#4338ca",
    "aquaculture": "#0891b2",
}


@st.cache_data(ttl=300, show_spinner="Loading surveillance data…")
def _frame() -> pd.DataFrame:
    return sv.load_surveillance_frame()


def _headline(frame: pd.DataFrame) -> None:
    isolates = frame["isolate_id"].nunique()
    specimens = frame["specimen_id"].nunique()
    labs = frame["lab_name"].nunique()
    sectors = frame["sector"].nunique()
    collected = frame["collection_datetime"].dropna()

    columns = st.columns(5)
    columns[0].metric("Specimens", f"{specimens:,}")
    columns[1].metric("Isolates", f"{isolates:,}")
    columns[2].metric("Susceptibility results", f"{len(frame):,}")
    columns[3].metric("Laboratories", f"{labs:,}")
    columns[4].metric("Sectors", f"{sectors:,}")

    if not collected.empty:
        st.caption(
            f"Specimens collected between {collected.min():%B %Y} and "
            f"{collected.max():%B %Y}. Figures below count each patient's first "
            "isolate of an organism once, following CLSI M39, so repeat "
            "sampling of one patient does not weight the result.")


def _resistance_table(human: pd.DataFrame, threshold: int) -> None:
    table, report = sv.cumulative_antibiogram(human, period_months=None)
    if table.empty:
        st.info("No susceptibility results are available for this selection.")
        return

    reported = table[table["status"] == sv.STATUS_REPORTED].copy()
    if reported.empty:
        st.warning(
            "No organism and antibiotic combination in this selection reaches "
            f"{sv.MIN_ISOLATES_FOR_REPORTING} isolates, which is the minimum "
            "this platform will publish a percentage on. Counts are shown "
            "elsewhere; a rate is not, because a percentage over a handful of "
            "results is not a measurement.")
        return

    shown, suppression = disclosure.apply_disclosure_control(
        reported, ["tested"], threshold=threshold,
        also_blank=["percent_susceptible", "ci_low", "ci_high"])

    columns = [c for c in ("organism", "antibiotic", "tested",
                           "percent_susceptible", "ci_low", "ci_high")
               if c in shown.columns]
    display = shown[columns].rename(columns={
        "tested": "Isolates tested",
        "percent_susceptible": "% susceptible",
        "ci_low": "95% CI low",
        "ci_high": "95% CI high",
    })
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(report.summary)
    if suppression.withheld:
        st.caption(suppression.summary)


def render_home_page() -> None:
    st.title("Antimicrobial resistance in Ghana")
    st.markdown(
        "Surveillance across human, animal, food, environmental and "
        "aquaculture sources, reported together. Everything on this page is "
        "aggregate: no individual patient, specimen or result is shown."
    )

    frame = _frame()
    if frame.empty:
        st.info(
            "No surveillance data has been published yet. This page will show "
            "resistance rates, the organisms behind them and how much data "
            "stands behind each figure, once data is available.")
        return

    _headline(frame)
    st.markdown("---")

    # ── what the reader can change ─────────────────────────────────────
    controls = st.columns([2, 2, 2, 1])
    sectors = sorted(frame["sector"].dropna().unique().tolist())
    chosen_sectors = controls[0].multiselect(
        "Sector", sectors, default=sectors,
        help="Human, animal, food, environmental and aquaculture isolates are "
             "never pooled into one rate unless you ask for it: resistance "
             "means different things in each.")
    regions = sorted(frame["region"].dropna().unique().tolist())
    chosen_regions = controls[1].multiselect("Region", regions, default=regions)
    labs = sorted(frame["lab_name"].dropna().unique().tolist())
    chosen_labs = controls[2].multiselect("Laboratory", labs, default=labs)
    threshold = controls[3].number_input(
        "Minimum cell", min_value=disclosure.MIN_PUBLIC_CELL, max_value=50,
        value=disclosure.MIN_PUBLIC_CELL, step=5,
        help="Counts below this are withheld. It can be raised, never lowered.")

    working = frame
    for column, chosen in (("sector", chosen_sectors), ("region", chosen_regions),
                           ("lab_name", chosen_labs)):
        if chosen:
            working = working[working[column].isin(chosen)]

    if working.empty:
        st.warning("Nothing matches that selection.")
        return

    deduplicated, dedup_report = sv.select_first_isolates(
        working, period_months=None)

    tabs = st.tabs(["Resistance", "Organisms", "One Health", "About this data"])

    # ── resistance ─────────────────────────────────────────────────────
    with tabs[0]:
        st.subheader("Susceptibility by organism and antibiotic")
        st.caption(
            "Each row is the proportion of tested isolates that remained "
            "susceptible, with the number tested and a 95% confidence interval. "
            "A wide interval means few isolates, not a wide range of opinion.")
        human = deduplicated[deduplicated["sector"] == "human"]
        source = human if not human.empty else deduplicated
        if human.empty:
            st.caption("No human isolates in this selection; showing all "
                       "sectors together, which should be read with care.")
        _resistance_table(source, int(threshold))

    # ── organisms ──────────────────────────────────────────────────────
    with tabs[1]:
        st.subheader("What is being isolated")
        try:
            distribution = sv.pathogen_distribution(
                deduplicated, allow_cross_sector=True)
        except Exception:                             # noqa: BLE001
            distribution = pd.DataFrame()
        if distribution.empty:
            st.info("No organisms to show for this selection.")
        else:
            shown, suppression = disclosure.apply_disclosure_control(
                distribution, ["isolates"], threshold=int(threshold),
                also_blank=["percent"])
            visible = shown[shown["isolates"] != disclosure.WITHHELD]
            if not visible.empty:
                figure = px.bar(
                    visible.head(12), x="isolates", y="organism",
                    orientation="h", color_discrete_sequence=["#0e7490"])
                figure.update_layout(
                    height=max(320, 26 * min(12, len(visible))),
                    margin=dict(t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="Isolates", yaxis_title="")
                st.plotly_chart(figure, use_container_width=True)
            st.dataframe(shown, use_container_width=True, hide_index=True)
            if suppression.withheld:
                st.caption(suppression.summary)

    # ── one health ─────────────────────────────────────────────────────
    with tabs[2]:
        st.subheader("Across sectors")
        st.caption(
            "Resistance does not stay where it is looked for. These are the "
            "same organisms counted in each sector separately, never pooled "
            "into a single national percentage, because a rate mixing hospital "
            "isolates with river water describes nothing.")
        by_sector = (deduplicated
                     .drop_duplicates(["dataset_id", "isolate_id"])
                     .groupby("sector", dropna=False)
                     .size().reset_index(name="isolates"))
        shown, suppression = disclosure.apply_disclosure_control(
            by_sector, ["isolates"], threshold=int(threshold))
        visible = shown[shown["isolates"] != disclosure.WITHHELD]
        if not visible.empty:
            figure = px.bar(visible, x="sector", y="isolates", color="sector",
                            color_discrete_map=_SECTOR_COLOUR)
            figure.update_layout(showlegend=False, height=320,
                                 margin=dict(t=10, b=10),
                                 paper_bgcolor="rgba(0,0,0,0)",
                                 xaxis_title="", yaxis_title="Isolates")
            st.plotly_chart(figure, use_container_width=True)
        st.dataframe(shown, use_container_width=True, hide_index=True)
        if suppression.withheld:
            st.caption(suppression.summary)

    # ── about ──────────────────────────────────────────────────────────
    with tabs[3]:
        st.subheader("How to read these figures")
        st.markdown(
            f"""
**Deduplication.** {dedup_report.summary}

**What is withheld.** Any figure resting on fewer than {int(threshold)} records
is withheld rather than shown, and so is any percentage calculated over it.
Withheld is not zero: it means too few to publish, not none found. Where
withholding one value would let it be recovered by subtracting the rest from a
total, a second value is withheld as well.

**Confidence intervals.** Every percentage carries one. It is calculated by the
Wilson method, which behaves properly near nought and one hundred per cent where
the ordinary approximation does not.

**Suppression below {sv.MIN_ISOLATES_FOR_REPORTING} isolates.** A percentage is
not published on fewer, following CLSI M39. The count is still reported where it
is large enough to show.

**Laboratories are named.** Attribution is the point of sentinel surveillance,
and a rate nobody can attribute is a rate nobody can act on.

**No individual is shown.** No patient identifier, specimen identifier or
individual result appears on this page.
            """
        )
        coverage = sv.coverage_report()
        if getattr(coverage, "completeness", None) is not None:
            st.caption("Completeness of the fields these figures depend on:")
            st.dataframe(coverage.completeness, use_container_width=True,
                         hide_index=True)
