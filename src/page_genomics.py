"""
Genomics page.

The platform could store sequencing results long before it could read them.
``genomic_results`` carried provenance, quality metrics, typing, resistance
determinants and clustering, and the only thing any page did with it was count
how many isolates had one. This page is the reading.

It is arranged around what the data can answer, hardest question first.

**Concordance** comes first because it is the only cross-check the platform
has. A gene call and a susceptibility result measure the same property by
different means, so where they disagree something is wrong, or the biology is
more interesting than either captures. The page shows the two kinds of
disagreement separately, because they mean opposite things: a determinant on a
susceptible isolate points at the laboratory or the assembly, while resistance
with no determinant points at the database or at a mechanism nobody has named.

**Determinants** reports what is circulating, always beside the database and
version that produced the calls -- a gene call without them is no more
reproducible than an S/I/R without its breakpoint edition.

**Clusters** is what separates "resistant isolates are accumulating here" from
"this is one clone". The page says plainly that cluster membership shows
relatedness and not direction, because the distance between those two readings
is the distance between a correct and an incorrect outbreak response.

Quality gating runs underneath all three. A thin assembly misses genes that are
present, so admitting it understates every determinant it failed to find, in the
direction that looks reassuring.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from src import genomics as gx

_VERDICT_COLOUR = {
    gx.CONCORDANT_RESISTANT: "#0e7490",
    gx.CONCORDANT_SUSCEPTIBLE: "#64748b",
    gx.GENOTYPE_ONLY: "#b91c1c",
    gx.PHENOTYPE_ONLY: "#b45309",
}


def _metric_row(coverage: dict) -> None:
    columns = st.columns(5)
    columns[0].metric("Genomes", f"{coverage.get('sequenced', 0):,}")
    percent = coverage.get("percent_sequenced")
    columns[1].metric(
        "Of isolates",
        f"{percent:.0f}%" if percent is not None else "-",
        help="Sequencing coverage limits every statement on this page. A gene "
             "frequency drawn from a fraction of the collection describes that "
             "fraction.")
    columns[2].metric("Passed quality", f"{coverage.get('passed_qc', 0):,}")
    columns[3].metric(
        "Failed quality", f"{coverage.get('failed_qc', 0):,}",
        help="Excluded from gene frequencies and concordance. A poorly covered "
             "assembly misses genes that are present.")
    columns[4].metric("Typed", f"{coverage.get('typed', 0):,}")


def render_genomics_page() -> None:
    st.header("Genomics")

    frame = gx.load_genomic_frame()
    if frame.empty:
        st.info(
            "No sequencing results have been loaded. The platform stores "
            "genomes against isolates in the specimen chain, so they arrive "
            "either on the genomics sheet of an upload or from a sequencing "
            "pipeline. Until then the pages below have nothing to read.")
        return

    total_isolates: Optional[int] = None
    try:
        from src import db
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) AS n FROM isolates")
        row = cur.fetchone()
        total_isolates = row["n"] if hasattr(row, "keys") else row[0]
        conn.close()
    except Exception:                                 # noqa: BLE001
        total_isolates = None

    coverage = gx.sequencing_coverage(frame, total_isolates)
    _metric_row(coverage)

    not_assessable = coverage.get("not_assessable", 0)
    if not_assessable:
        st.warning(
            f"{not_assessable:,} genome(s) carry no quality metrics at all. "
            "They are neither passed nor failed here: an assembly nobody "
            "measured cannot be vouched for, and treating unmeasured as "
            "acceptable is how an unvetted genome reaches a national figure.")

    tabs = st.tabs(["Concordance", "Determinants", "Clusters", "Quality"])

    # ── concordance ────────────────────────────────────────────────────
    with tabs[0]:
        table = gx.concordance(frame)
        if table.empty:
            st.info("No isolate has both a genome and a susceptibility result "
                    "for an agent the determinant rules speak to.")
        else:
            summary = gx.concordance_summary(table)
            cols = st.columns(4)
            cols[0].metric("Pairs compared", f"{summary['pairs']:,}",
                           help="One isolate, one antibiotic. Only agents some "
                                "determinant in the rule set predicts.")
            cols[1].metric("Agreement", f"{summary['agreement_percent']}%")
            cols[2].metric("Determinant, tested susceptible",
                           f"{summary['determinant_but_susceptible']:,}")
            cols[3].metric("Resistance unexplained",
                           f"{summary['resistance_unexplained']:,}")

            st.caption(
                "Agreement is reported beside the two kinds of disagreement "
                "rather than instead of them. On its own it hides whether the "
                "misses are mechanisms the database cannot see or genes that "
                "are not being expressed, and those call for different work.")

            counts = (table["verdict"].value_counts()
                      .rename_axis("verdict").reset_index(name="pairs"))
            figure = px.bar(counts, x="pairs", y="verdict", orientation="h",
                            color="verdict", color_discrete_map=_VERDICT_COLOUR)
            figure.update_layout(showlegend=False, height=260,
                                 margin=dict(t=10, b=10),
                                 paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(figure, use_container_width=True)

            st.subheader("Worth re-checking")
            st.caption(
                "A determinant that strongly predicts resistance, on an isolate "
                "that tested susceptible. Each is either a mislabelled isolate, "
                "a contaminated assembly or a testing error. Genes that only "
                "raise an MIC without usually crossing the breakpoint are not "
                "listed here, because flagging them would bury these.")
            contradictions = gx.contradictions(table)
            if contradictions.empty:
                st.success("No strong determinant contradicts its phenotype.")
            else:
                st.dataframe(contradictions, use_container_width=True,
                             hide_index=True)

            st.subheader("Resistance with no determinant identified")
            st.caption(
                "A statement about the method rather than about the organism. "
                "The usual explanations are efflux or porin loss, a determinant "
                "the database does not carry, or a region the assembly did not "
                "cover.")
            unexplained = gx.unexplained_resistance(table)
            if unexplained.empty:
                st.success("Every non-susceptible result has a determinant "
                           "behind it.")
            else:
                st.dataframe(unexplained, use_container_width=True,
                             hide_index=True)

    # ── determinants ───────────────────────────────────────────────────
    with tabs[1]:
        split = st.selectbox(
            "Break down by",
            ["All sequenced isolates", "organism", "sector", "specimen_type",
             "lab_name", "region"],
            help="The denominator is always genomes examined, so a figure reads "
                 "as the proportion of sequenced isolates carrying the "
                 "determinant.")
        by = None if split == "All sequenced isolates" else split
        frequency = gx.determinant_frequency(frame, by=by)
        if frequency.empty:
            st.info("No determinants were called on the genomes that passed "
                    "quality.")
        else:
            st.dataframe(frequency, use_container_width=True, hide_index=True)
            top = frequency.nlargest(min(15, len(frequency)), "percent")
            figure = px.bar(top, x="percent", y="determinant",
                            color="mechanism", orientation="h")
            figure.update_layout(height=max(320, 22 * len(top)),
                                 margin=dict(t=10, b=10),
                                 paper_bgcolor="rgba(0,0,0,0)",
                                 xaxis_title="% of genomes examined")
            st.plotly_chart(figure, use_container_width=True)

        unmapped = gx.determinants_not_in_rules(frame)
        if unmapped:
            st.info(
                f"{len(unmapped)} determinant(s) found in the data are not in "
                "the rule set, so they explain nothing in the concordance tab "
                "and some unexplained resistance may simply be an unmapped "
                f"gene: {', '.join(unmapped)}.")

        markers = gx.non_resistance_markers_found(frame)
        if markers:
            with st.expander(
                    f"{len(markers)} marker(s) present that confer no antibiotic "
                    "resistance"):
                st.caption(
                    "Real findings, reported here rather than among the "
                    "determinants. No susceptibility result corresponds to "
                    "them, so they can neither agree nor disagree with a "
                    "phenotype, and counting them as resistance genes would "
                    "overstate what is circulating.")
                for gene, explanation in markers.items():
                    st.markdown(f"- **{gene}** - {explanation}")

    # ── clusters ───────────────────────────────────────────────────────
    with tabs[2]:
        report = gx.clusters(frame)
        st.write(report.summary)
        if report.clusters.empty:
            st.info("Nothing further to show until clustering has been run.")
        else:
            st.dataframe(report.clusters, use_container_width=True,
                         hide_index=True)
            choices = report.clusters["cluster_id"].tolist()
            chosen = st.selectbox("Members of", choices)
            members = report.members[report.members["cluster_id"] == chosen]
            st.dataframe(members, use_container_width=True, hide_index=True)
            st.caption(
                "Shared cluster membership shows that these isolates are closely "
                "related. It does not show which came first, or which direction "
                "anything moved: cluster membership is symmetric, and direction "
                "needs dated sampling and a phylogeny.")

    # ── quality ────────────────────────────────────────────────────────
    with tabs[3]:
        thresholds = gx.DEFAULT_THRESHOLDS
        st.caption(
            f"Working thresholds: depth >= {thresholds.min_mean_depth:g}x, "
            f"coverage >= {thresholds.min_coverage_breadth:g}%, contamination "
            f"<= {thresholds.max_contamination_pct:g}%, N50 >= "
            f"{thresholds.min_n50:,.0f}, contigs <= {thresholds.max_contigs:,}. "
            "These are ordinary working values rather than a standard, and are "
            "meant to be argued with.")
        columns = [c for c in ("genomic_id", "isolate_id", "organism",
                               "qc_verdict", "qc_reason", "mean_depth",
                               "coverage_breadth", "contamination_pct", "n50",
                               "contig_count", "pipeline_name", "amr_db_name",
                               "amr_db_version", "review_status")
                   if c in frame.columns]
        failed = frame[frame["qc_verdict"] != gx.QC_PASS]
        if failed.empty:
            st.success("Every genome passed.")
        else:
            st.dataframe(failed[columns], use_container_width=True,
                         hide_index=True)
