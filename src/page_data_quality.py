"""
Data Coverage & Quality page.

The critical review asked for this as a surveillance product in its own right,
not a maintenance screen:

    "Report site and sector coverage; expected versus received submissions;
    timeliness; completeness of core fields; duplicate, invalid and unlinked
    record rates; AST quality-control performance; sequence linkage; and missing
    denominators. Show reporting volume and uncertainty beside every rate, and
    allow users to distinguish 'no signal' from 'no data'."

It is currently the most informative page in the platform, because the fields
that make a result clinically interpretable -- ward, specimen type, age, sex --
are empty for every backfilled record, and this is the page that says so plainly
rather than drawing a confident chart of a single "Unknown" bar.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from src import expert_rules, surveillance as sv

_STATUS_COLOUR = {
    "complete": "#0e7490",
    "partial": "#b45309",
    "sparse": "#b91c1c",
    "not collected": "#7f1d1d",
    "column absent": "#475569",
    "no records in scope": "#475569",
}

_FRESHNESS_NOTE = {
    "current": "Data is current.",
    "lagging": "The most recent specimen is over a month old. Submissions are "
               "behind.",
    "stale": "The most recent specimen is over three months old. Figures on "
             "this platform describe the past, not the present, and should not "
             "be read as an early-warning signal.",
    "no data": "No specimens in scope.",
    "no collection dates": "No collection dates recorded, so currency cannot be "
                           "judged.",
}


def _percent(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}%"


def _completeness_section(report: sv.CoverageReport) -> None:
    st.subheader("Completeness of core fields")
    st.caption(
        "A field counts as recorded only when it holds an informative value. A "
        "stored 'Unknown' counts as missing, because it is a placeholder rather "
        "than an observation -- and treating it as data is how a coverage "
        "report comes to congratulate itself on a field nobody filled."
    )

    table = report.completeness
    if table.empty:
        st.info("No records in scope.")
        return

    not_collected = table[table["Status"] == "not collected"]
    if not not_collected.empty:
        names = ", ".join(not_collected["Field"].tolist())
        st.error(
            f"**Not collected at all: {names}.** These fields exist in the data "
            "model and are offered on the upload template, but no submission has "
            "populated them. Any breakdown by them will show a single 'Not "
            "recorded' group. This is the list to hand a laboratory when asking "
            "what to start capturing."
        )

    chart = table.dropna(subset=["Percent"]).copy()
    if not chart.empty:
        figure = px.bar(
            chart, x="Percent", y="Field", orientation="h", color="Status",
            color_discrete_map=_STATUS_COLOUR,
            labels={"Percent": "% of records with an informative value",
                    "Field": ""},
            hover_data=["Recorded", "Of", "Scope"],
        )
        figure.update_layout(xaxis_range=[0, 100],
                            height=max(320, 28 * len(chart)),
                            yaxis={"categoryorder": "total ascending"},
                            margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(figure, use_container_width=True)

    st.dataframe(
        table.assign(Percent=table["Percent"].map(_percent))
             .rename(columns={"Of": "Records in scope"}),
        use_container_width=True, hide_index=True)


def _coverage_section(report: sv.CoverageReport) -> None:
    st.subheader("Reporting coverage")
    a, b, c, d = st.columns(4)
    a.metric("Specimens", f"{report.specimens:,}")
    b.metric("Isolates", f"{report.isolates:,}")
    c.metric("Susceptibility results", f"{report.observations:,}")
    d.metric("Laboratories reporting", f"{report.labs:,}")

    if report.sectors:
        frame = pd.DataFrame(
            [{"Sector": k.title(), "Specimens": v}
             for k, v in report.sectors.items()])
        figure = px.bar(frame, x="Sector", y="Specimens", text="Specimens")
        figure.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=300)
        st.plotly_chart(figure, use_container_width=True)
        st.caption(
            "Sector coverage. A sector with few specimens cannot support a "
            "national statement about it, however confident the percentage "
            "elsewhere on the platform looks."
        )


def _freshness_section(report: sv.CoverageReport) -> None:
    st.subheader("Timeliness")
    freshness = report.freshness
    status = str(freshness.get("status", "no data"))

    a, b, c = st.columns(3)
    a.metric("Most recent specimen",
             str(freshness.get("latest_collection") or "—"))
    days = freshness.get("days_since_latest")
    b.metric("Age of most recent", f"{days} days" if days is not None else "—")
    turnaround = (report.quality or {}).get("turnaround") or {}
    median = turnaround.get("median_days")
    c.metric("Collection to laboratory receipt",
             f"{median:.1f} days" if median is not None else "not recorded",
             help="Median. A surveillance system that reports resistance weeks "
                  "after the specimen was taken cannot inform the treatment of "
                  "the patient it came from.")

    note = _FRESHNESS_NOTE.get(status, "")
    if status == "stale":
        st.error(note)
    elif status == "lagging":
        st.warning(note)
    else:
        st.info(note)

    if turnaround.get("measurable", 0) == 0:
        st.caption(
            "Turnaround cannot be measured: no specimen carries both a "
            "collection and a receipt time. Both are on the upload template."
        )


def _linkage_section(report: sv.CoverageReport) -> None:
    st.subheader("Chain linkage")
    st.caption(
        "The traceability chain is only useful where it is actually joined up. "
        "These are the joins, measured."
    )
    linkage = report.linkage or {}

    a, b, c, d = st.columns(4)
    positivity = linkage.get("culture_positivity_percent")
    a.metric("Culture positivity", _percent(positivity),
             help="Specimens yielding at least one isolate. Requires "
                  "culture-negative specimens to be submitted too; without "
                  "them this figure is meaningless.")
    total = linkage.get("specimens_total") or 0
    with_ward = linkage.get("specimens_with_ward") or 0
    b.metric("Specimens with a ward",
             _percent(100 * with_ward / total) if total else "—",
             help="Without a ward, a result cannot be attributed to a care "
                  "setting, and healthcare-association cannot be assessed.")
    isolates_total = linkage.get("isolates_total") or 0
    with_result = linkage.get("isolates_with_result") or 0
    c.metric("Isolates with a result",
             _percent(100 * with_result / isolates_total) if isolates_total else "—")
    d.metric("Isolates sequenced",
             _percent(linkage.get("percent_isolates_sequenced")),
             help="Genomic results linked to their isolate, which is what makes "
                  "a resistance gene resolvable back to a patient and ward.")

    if not linkage.get("genomic_results"):
        st.info(
            "No genomic results are linked yet. The chain supports them: a row "
            "on the **genomics** sheet of the upload template attaches to the "
            "same isolate_id as the susceptibility rows, which is what connects "
            "a sequence type or resistance gene to a ward and a patient."
        )


def _quality_section(report: sv.CoverageReport) -> None:
    st.subheader("Result quality and provenance")
    quality = report.quality or {}

    total = quality.get("qc_total") or 0
    recorded = quality.get("qc_recorded") or 0
    a, b, c = st.columns(3)
    a.metric("Results with QC recorded",
             _percent(100 * recorded / total) if total else "—")
    b.metric("QC failures", f"{quality.get('qc_fail', 0):,}",
             help="Excluded from cumulative reporting. A result from a failed "
                  "run is evidence about the run, not the isolate.")
    without_edition = quality.get("results_without_edition", 0)
    c.metric("Results with no breakpoint edition", f"{without_edition:,}",
             help="An S/I/R with no edition behind it cannot be reproduced, "
                  "because breakpoints move between editions.")

    if recorded == 0 and total:
        st.warning(
            "No result records whether its quality control passed. AST QC "
            "performance is a core surveillance measure and the field is on the "
            "upload template."
        )

    sources = quality.get("result_source") or {}
    if sources:
        st.markdown("##### How each result arrived")
        st.caption(
            "Measured results were read from a plate or instrument; "
            "rule-interpreted results were derived by the platform from a "
            "measurement; imported results arrived already interpreted, with "
            "provenance unknown. Conflating them hides how much of the evidence "
            "the platform generated itself."
        )
        frame = pd.DataFrame([{"Source": k, "Results": v}
                              for k, v in sources.items()])
        st.dataframe(frame, use_container_width=True, hide_index=True)


def _plausibility_section(dataset_id: Optional[str]) -> None:
    st.subheader("Implausible organism–agent combinations")
    st.caption(
        "Results recording susceptibility where it is not biologically "
        "possible, or where CLSI directs that the agent not be reported for "
        "that organism. These are data-quality findings, and the response is to "
        "correct them at source."
    )

    frame = sv.load_surveillance_frame(dataset_id=dataset_id)
    if frame.empty:
        st.info("No results in scope.")
        return

    findings = expert_rules.screen_frame(frame)
    if findings.empty:
        st.success(
            "No implausible organism–agent combination found. Every result is "
            "for a pair where susceptibility testing is meaningful."
        )
        return

    errors = findings[findings["severity"] == expert_rules.SEVERITY_ERROR]
    suppress = findings[findings["severity"] == expert_rules.SEVERITY_SUPPRESS]
    affected = int(findings["observations"].sum())

    a, b, c = st.columns(3)
    a.metric("Impossible pairs", f"{len(errors):,}")
    b.metric("Results affected", f"{affected:,}",
             help=f"{_percent(100 * affected / len(frame))} of all results")
    c.metric("Recorded susceptible", f"{int(errors['reported_susceptible'].sum()):,}",
             help="Susceptible results for pairs where that cannot occur. Each "
                  "is a testing, identification or data-entry error.")

    if not errors.empty and errors["reported_susceptible"].sum():
        st.error(
            f"{int(errors['reported_susceptible'].sum())} result(s) record an "
            "organism as susceptible to an agent it is intrinsically resistant "
            "to. A worked example: *Escherichia coli* cannot be susceptible to "
            "vancomycin, because the molecule does not cross the Gram-negative "
            "outer membrane. Such rows are excluded from antibiograms, but they "
            "indicate a problem upstream that suppression does not fix."
        )

    st.dataframe(
        findings.rename(columns={
            "organism": "Organism", "antibiotic": "Antibiotic",
            "severity": "Kind", "observations": "Results",
            "reported_susceptible": "Recorded S", "reason": "Why"}),
        use_container_width=True, hide_index=True)

    if not suppress.empty:
        st.info(
            f"{len(suppress)} pair(s) are active in vitro but must not be "
            "reported clinically -- typically *Salmonella* or *Shigella* with a "
            "first-generation cephalosporin or an aminoglycoside, which inhibit "
            "the organism on a plate and fail in the patient. These are not "
            "errors; they are excluded from clinical reporting and remain valid "
            "for surveillance."
        )

    st.caption(
        "The rule table is an abridged transcription of CLSI and EUCAST "
        "intrinsic-resistance guidance covering the organisms this platform "
        "sees. It must be verified against the current editions by the national "
        "reference laboratory before being relied on clinically."
    )


def _denominator_section() -> None:
    """Whether antimicrobial use and consumption can be normalised at all.

    The review listed missing denominators among the measures a national system
    should publish. Without patient-days, use is a volume; without biomass,
    animal consumption reflects herd size as much as prescribing. Neither is
    comparable between reporting units, so the coverage is the thing to know
    before reading any of it.
    """
    from src import consumption

    st.subheader("Denominators for use and consumption")
    st.caption(
        "A rate needs a denominator. These are the records that carry one, and "
        "what is lost where they do not."
    )

    try:
        amu = db.get_amu_records()
        amc = db.get_amc_records()
    except Exception as exc:                          # noqa: BLE001
        st.error(f"Could not read use and consumption records: {exc}")
        return

    table = consumption.denominator_coverage(amu, amc)
    if table.empty:
        st.info("No antimicrobial use or consumption records have been "
                "submitted yet.")
        return

    st.dataframe(
        table.assign(Percent=table["Percent"].map(_percent)),
        use_container_width=True, hide_index=True)

    incomplete = table[table["Percent"].fillna(0) < 100]
    if not incomplete.empty:
        for _, row in incomplete.iterrows():
            st.warning(
                f"**{row['Dataset']}.** {int(row['With a usable denominator']):,} "
                f"of {int(row['Records']):,} records carry "
                f"{str(row['Denominator']).lower()}. {row['Consequence if missing']}"
            )
    else:
        st.success(
            "Every record carries its denominator, so use and consumption can "
            "be reported as rates rather than volumes."
        )

    st.markdown("##### How these metrics are defined")
    st.caption(
        "Numerator, denominator, conversion and calculation for each. Pooled "
        "rates divide summed numerator by summed denominator; a mean of "
        "per-record rates has no denominator behind it and is not used."
    )
    st.dataframe(consumption.metrics_frame(), use_container_width=True,
                 hide_index=True)


def render_data_quality_page() -> None:
    st.header("Data Coverage & Quality")
    st.caption(
        "Whether the data can support the figures drawn from it. Every rate "
        "elsewhere on this platform should be read against this page."
    )

    dataset_id = st.session_state.get("active_dataset_id")

    try:
        report = sv.coverage_report(dataset_id=dataset_id)
    except Exception as exc:                          # noqa: BLE001
        st.error(f"Could not assemble the coverage report: {exc}")
        return

    if not report.specimens:
        st.info(
            "No specimens in the traceability chain yet. Upload data using the "
            "current template on **Upload & Data Quality**."
        )
        return

    st.markdown(f"**{report.headline}**")

    (coverage, completeness, timeliness, linkage, quality, plausibility,
     denominators) = st.tabs([
        "Coverage", "Field completeness", "Timeliness", "Chain linkage",
        "Result quality", "Implausible results", "Denominators",
    ])
    with coverage:
        _coverage_section(report)
    with completeness:
        _completeness_section(report)
    with timeliness:
        _freshness_section(report)
    with linkage:
        _linkage_section(report)
    with quality:
        _quality_section(report)
    with plausibility:
        _plausibility_section(dataset_id)
    with denominators:
        _denominator_section()


__all__ = ["render_data_quality_page"]
