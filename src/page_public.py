"""
The public section pages.

The landing page is a door; these are the rooms. Each one answers a single
question, carries its own filters, and ends with a statement of what it does
not show. They are reachable without an account and written for a reader who
has had no briefing.

Everything here obeys the same three rules as the landing page.

**Aggregate only.** No patient, specimen or isolate identifier appears, and
every count passes through ``src.disclosure`` before it is drawn. The risk on a
public page is not the headline figures but the filtering: a visitor who narrows
by sector, region, laboratory and organism can reach a cell holding one person,
and each filter is another attribute attached to them. Counts below the
threshold are withheld, percentages computed over withheld counts go with them,
and a second cell goes when the first could be recovered by subtraction.

**No figure is stated more confidently than the data supports.** Percentages
carry their denominator and a Wilson interval. A rate on fewer than
``MIN_ISOLATES_FOR_REPORTING`` isolates is not published at all, following
CLSI M39 -- the count is, where it is large enough to show.

**Colour never carries a meaning on its own.** See ``src.palette``.

Laboratories are named. Attribution is the point of sentinel surveillance, and
a rate nobody can attribute is a rate nobody can act on.
"""

from __future__ import annotations

from html import escape
from typing import Callable, Dict, List, NamedTuple, Tuple
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import streamlit as st

from src import consumption, db, disclosure, genomics as gx, palette
from src import surveillance as sv

#: Every public page key carries this prefix, so the router in ``app.py`` can
#: recognise one without having to list them, and so a public key can never
#: collide with a sidebar page name.
PREFIX = "public:"


class Section(NamedTuple):
    """One card on the landing page, and the page behind it."""
    key: str
    icon: str
    title: str
    blurb: str
    colour: str
    #: Returns the figure shown on the card, as (number, unit). Cheap: it runs
    #: on every landing-page render, from one cached count query.
    stat: Callable[[Dict[str, object]], Tuple[str, str]]


# ---------------------------------------------------------------------------
# Shared loading and controls
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner="Loading surveillance data...")
def surveillance_frame() -> pd.DataFrame:
    return sv.load_surveillance_frame()


@st.cache_data(ttl=300, show_spinner="Loading sequencing results...")
def genomic_frame() -> pd.DataFrame:
    return gx.load_genomic_frame()


@st.cache_data(ttl=300, show_spinner=False)
def landing_counts() -> Dict[str, object]:
    """Every number the landing cards need, in one query.

    Six cards each running their own aggregate would open six connections on
    the page a first-time visitor sees, which is the one page that has to be
    fast. Scalar subqueries keep it to a single round trip.
    """
    sql = """
        SELECT
          (SELECT COUNT(*) FROM specimens)                         AS specimens,
          (SELECT COUNT(*) FROM isolates)                          AS isolates,
          (SELECT COUNT(DISTINCT organism) FROM isolates
             WHERE organism IS NOT NULL AND organism <> '')        AS organisms,
          (SELECT COUNT(*) FROM phenotypes)                        AS results,
          (SELECT COUNT(DISTINCT lab_name) FROM specimens
             WHERE lab_name IS NOT NULL AND lab_name <> '')        AS labs,
          (SELECT COUNT(DISTINCT sector) FROM subjects
             WHERE sector IS NOT NULL)                             AS sectors,
          (SELECT COUNT(DISTINCT region) FROM specimens
             WHERE region IS NOT NULL AND region <> '')            AS regions,
          (SELECT COUNT(*) FROM genomic_results)                   AS genomes,
          (SELECT COUNT(*) FROM amu_records)                       AS amu,
          (SELECT COUNT(*) FROM amc_records)                       AS amc,
          (SELECT COUNT(*) FROM pps_surveys)                       AS pps,
          (SELECT MIN(collection_datetime) FROM specimens)         AS first_collected,
          (SELECT MAX(collection_datetime) FROM specimens)         AS last_collected
    """
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    return dict(row) if row else {}


def go(page: str) -> None:
    """Navigate, and put it in the URL.

    Session state alone would make a section unlinkable: the reader could not
    bookmark it, could not send it to a colleague, and the browser's back
    button would leave the page where it was. So the URL carries the page and
    the session key follows it.
    """
    st.session_state.active_page = page
    try:
        if page == "Home":
            if "page" in st.query_params:
                del st.query_params["page"]
        else:
            st.query_params["page"] = page
    except Exception:                                 # noqa: BLE001
        pass
    st.rerun()


def _overview_href() -> str:
    """A link back to the landing page, keeping ``?admin=1`` if it is set."""
    params = {}
    try:
        for key, value in st.query_params.items():
            if key != "page":
                params[key] = value
    except Exception:                                 # noqa: BLE001
        params = {}
    return "?" + urlencode(params) if params else "?"


def _back_bar(title: str, subtitle: str) -> None:
    """The header every section page shares.

    The way back is an anchor rather than a button so it behaves like a link:
    it can be opened in a new tab, it shows its destination on hover, and it
    does not cost a server round trip to find out where it goes.
    """
    st.markdown(
        f"""
        <style>
          .amr-crumb {{
              display: inline-block;
              font-size: 0.84rem;
              font-weight: 600;
              color: #1d4d43 !important;
              text-decoration: none !important;
              margin-bottom: 0.35rem;
          }}
          .amr-crumb:hover {{ text-decoration: underline !important; }}
          .amr-page-title {{
              font-size: clamp(1.7rem, 3.4vw, 2.4rem);
              font-weight: 700;
              line-height: 1.12;
              letter-spacing: -0.015em;
              margin: 0 0 0.3rem 0;
              color: #1a170e;
          }}
          .amr-page-sub {{
              font-size: 1rem;
              line-height: 1.6;
              color: rgba(26, 23, 14, 0.66);
              max-width: 70ch;
              margin: 0 0 1.1rem 0;
          }}
        </style>
        <a class="amr-crumb" href="{escape(_overview_href())}" target="_self">
          &larr; All sections</a>
        <h1 class="amr-page-title">{escape(title)}</h1>
        <p class="amr-page-sub">{escape(subtitle)}</p>
        """,
        unsafe_allow_html=True)


class Scope(NamedTuple):
    """The reader's selection, and what it leaves them looking at."""
    frame: pd.DataFrame
    threshold: int
    sectors: List[str]
    single_sector: bool


def _controls(frame: pd.DataFrame, key: str, *,
              sector_default_human: bool = False) -> Scope:
    """The filter bar every section page shares.

    Sector defaults to one sector on pages where pooling would be misleading,
    rather than defaulting to everything and warning afterwards: the first
    figure a visitor sees should be one that means something.
    """
    columns = st.columns([2, 2, 2, 1])

    sectors = sorted(frame["sector"].dropna().unique().tolist())
    if sector_default_human and "human" in sectors:
        default = ["human"]
    else:
        default = sectors
    chosen_sectors = columns[0].multiselect(
        "Sector", sectors, default=default, key=f"{key}_sector",
        help="Human, animal, food, environmental and aquaculture isolates mean "
             "different things. Selecting more than one pools them, and the "
             "page says so where that matters.")

    regions = sorted(frame["region"].dropna().unique().tolist())
    chosen_regions = columns[1].multiselect(
        "Region", regions, default=regions, key=f"{key}_region")

    labs = sorted(frame["lab_name"].dropna().unique().tolist())
    chosen_labs = columns[2].multiselect(
        "Laboratory", labs, default=labs, key=f"{key}_lab")

    threshold = columns[3].number_input(
        "Minimum cell", min_value=disclosure.MIN_PUBLIC_CELL, max_value=50,
        value=disclosure.MIN_PUBLIC_CELL, step=5, key=f"{key}_threshold",
        help="Counts resting on fewer records than this are withheld. It can be "
             "raised, never lowered.")

    working = frame
    for column, chosen in (("sector", chosen_sectors),
                           ("region", chosen_regions),
                           ("lab_name", chosen_labs)):
        if chosen:
            working = working[working[column].isin(chosen)]

    effective = chosen_sectors or sectors
    return Scope(working, int(threshold), effective, len(effective) == 1)


def _show(frame: pd.DataFrame) -> None:
    """Draw a table that has been through disclosure control.

    Every published table goes through here rather than straight to
    ``st.dataframe``, because a column holding both counts and the word
    "withheld" has object dtype and Arrow -- which Streamlit uses to ship a
    table to the browser -- refuses to serialise it. The table is correct and
    simply never arrives. ``disclosure.for_display`` renders such a column as
    text instead of dropping the marker, since a blank cell reads as zero and
    withheld is not zero.
    """
    st.dataframe(disclosure.for_display(frame), use_container_width=True,
                 hide_index=True)


def _nothing_matches() -> None:
    st.warning(
        "Nothing matches that selection. Widen one of the filters above, or "
        "return to the overview.")


def _footer(note: str) -> None:
    st.markdown("---")
    st.caption(note)
    st.caption(
        "Every figure on this page is an aggregate. No patient identifier, "
        "specimen identifier or individual result is shown, and counts below "
        "the minimum cell are withheld rather than drawn. Withheld is not zero: "
        "it means too few records to publish, not none found.")


# ---------------------------------------------------------------------------
# Resistance
# ---------------------------------------------------------------------------

def _antibiogram_chart(reported: pd.DataFrame, threshold: int) -> None:
    """Lowest-susceptibility pairs, with the interval drawn rather than noted.

    A bar at 92% from 31 isolates and one at 92% from 900 look identical until
    the interval is on the chart, and the point of publishing the denominator
    is lost if the reader has to go and find it in the table.
    """
    shown, _ = disclosure.apply_disclosure_control(
        reported, ["tested"], threshold=threshold,
        also_blank=["percent_susceptible", "ci_low", "ci_high"])
    drawable = shown[shown["tested"] != disclosure.WITHHELD].copy()
    drawable = drawable.dropna(subset=["percent_susceptible", "ci_low", "ci_high"])
    if drawable.empty:
        return

    drawable = drawable.sort_values("percent_susceptible").head(20)
    drawable["pair"] = (drawable["organism"].astype(str) + " / "
                        + drawable["antibiotic"].astype(str))
    drawable["low"] = drawable["percent_susceptible"] - drawable["ci_low"]
    drawable["high"] = drawable["ci_high"] - drawable["percent_susceptible"]

    figure = px.scatter(
        drawable, x="percent_susceptible", y="pair",
        error_x="high", error_x_minus="low",
        color_discrete_sequence=[palette.BLUE],
        labels={"percent_susceptible": "% susceptible", "pair": ""},
        hover_data={"tested": True})
    figure.update_traces(marker=dict(size=10))
    figure.update_layout(
        height=max(340, 28 * len(drawable)), margin=dict(t=10, b=10, l=10),
        paper_bgcolor="rgba(0,0,0,0)", xaxis_range=[0, 100])
    st.plotly_chart(figure, use_container_width=True)
    st.caption(
        "The combinations with the lowest susceptibility in this selection. "
        "The bar through each point is the 95% confidence interval: a long bar "
        "means few isolates, not a disputed figure.")


def render_resistance() -> None:
    _back_bar("Resistance",
              "How often the organisms being isolated still respond to the "
              "antibiotics used against them.")

    frame = surveillance_frame()
    if frame.empty:
        st.info("No susceptibility results have been published yet.")
        return

    scope = _controls(frame, "res", sector_default_human=True)
    if scope.frame.empty:
        _nothing_matches()
        return
    if not scope.single_sector:
        st.info(
            "More than one sector is selected, so the percentages below pool "
            f"{', '.join(scope.sectors)} isolates together. Resistance means "
            "something different in each, and a pooled figure is best read as "
            "a summary of this selection rather than as a rate for anywhere.")

    table, provenance = sv.cumulative_antibiogram(
        scope.frame, period_months=None,
        allow_cross_sector=not scope.single_sector)
    if table.empty:
        st.info("No susceptibility results are available for this selection.")
        return

    reported = table[table["status"] == sv.STATUS_REPORTED].copy()
    suppressed = int((table["status"] == sv.STATUS_SUPPRESSED).sum())

    top = st.columns(4)
    top[0].metric("Organism-antibiotic pairs", f"{len(table):,}")
    top[1].metric("Published as a rate", f"{len(reported):,}")
    top[2].metric("Too few to publish", f"{suppressed:,}")
    top[3].metric("Isolates", f"{scope.frame['isolate_id'].nunique():,}")

    if reported.empty:
        st.warning(
            "No combination in this selection reaches "
            f"{sv.MIN_ISOLATES_FOR_REPORTING} isolates, which is the minimum "
            "this platform will put a percentage on. A percentage over a "
            "handful of results is not a measurement, so none is shown.")
        _footer(str(provenance.get("deduplication_summary", "")))
        return

    _antibiogram_chart(reported, scope.threshold)

    st.subheader("Every published combination")
    shown, suppression = disclosure.apply_disclosure_control(
        reported, ["tested"], threshold=scope.threshold,
        also_blank=["percent_susceptible", "ci_low", "ci_high"])
    columns = [c for c in ("organism", "antibiotic", "tested",
                           "percent_susceptible", "ci_low", "ci_high",
                           "breakpoints") if c in shown.columns]
    _show(
        shown[columns].rename(columns={
            "organism": "Organism", "antibiotic": "Antibiotic",
            "tested": "Isolates tested",
            "percent_susceptible": "% susceptible",
            "ci_low": "95% CI low", "ci_high": "95% CI high",
            "breakpoints": "Breakpoints"}))
    if suppression.withheld:
        st.caption(suppression.summary)

    # -- where the resistance sits --------------------------------------
    st.subheader("Resistance by setting")
    st.caption(
        "The same results split by where the specimen came from. The unit here "
        "is one isolate against one agent, not the isolate, because an isolate "
        "tested against twelve agents cannot be the denominator for twelve "
        "results. Two settings are only comparable when similar panels were "
        "tested, so the number of distinct organism-antibiotic pairs is shown "
        "beside each.")
    choices = [c for c in ("specimen_type", "ward_type_at_collection",
                           "age_band_at_collection", "patient_type", "region")
               if c in scope.frame.columns]
    if choices:
        by = st.selectbox(
            "Split by", choices, key="res_by",
            format_func=lambda c: c.replace("_at_collection", "")
                                   .replace("_", " ").capitalize())
        strata = sv.stratified_resistance(
            scope.frame, by=by, allow_cross_sector=not scope.single_sector)
        if strata.empty:
            st.info("Nothing to split on for this selection.")
        else:
            shown, suppression = disclosure.apply_disclosure_control(
                strata, ["isolates"], threshold=scope.threshold,
                also_blank=["percent_non_susceptible", "ci_low", "ci_high"])
            drawable = shown[(shown["isolates"] != disclosure.WITHHELD)
                             & shown["percent_non_susceptible"].notna()].copy()
            if not drawable.empty:
                figure = px.bar(
                    drawable, x=by, y="percent_non_susceptible",
                    error_y=(drawable["ci_high"]
                             - drawable["percent_non_susceptible"]),
                    error_y_minus=(drawable["percent_non_susceptible"]
                                   - drawable["ci_low"]),
                    color_discrete_sequence=[palette.VERMILLION],
                    labels={"percent_non_susceptible": "% non-susceptible",
                            by: ""})
                figure.update_layout(height=360, margin=dict(t=10, b=10),
                                     paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(figure, use_container_width=True)
            _show(shown)
            if suppression.withheld:
                st.caption(suppression.summary)

    _footer(
        f"**Method.** {provenance.get('deduplication_summary', '')} "
        f"Percentages are not published below {sv.MIN_ISOLATES_FOR_REPORTING} "
        "isolates (CLSI M39). Intervals are Wilson intervals, which behave "
        "properly near 0% and 100% where the ordinary approximation does not. "
        "Quality-control failures excluded: "
        f"{provenance.get('qc_failures_excluded', 0):,}.")


# ---------------------------------------------------------------------------
# Organisms
# ---------------------------------------------------------------------------

def render_organisms() -> None:
    _back_bar("Organisms",
              "What is actually being isolated, counted as isolates rather "
              "than as test results.")

    frame = surveillance_frame()
    if frame.empty:
        st.info("No isolates have been published yet.")
        return

    scope = _controls(frame, "org")
    if scope.frame.empty:
        _nothing_matches()
        return

    deduplicated, dedup = sv.select_first_isolates(scope.frame,
                                                   period_months=None)
    distribution = sv.pathogen_distribution(deduplicated,
                                            allow_cross_sector=True)
    if distribution.empty:
        st.info("No organisms to show for this selection.")
        return

    top = st.columns(3)
    top[0].metric("Distinct organisms", f"{len(distribution):,}")
    top[1].metric("Isolates", f"{int(distribution['isolates'].sum()):,}")
    top[2].metric("Laboratories", f"{scope.frame['lab_name'].nunique():,}")

    shown, suppression = disclosure.apply_disclosure_control(
        distribution, ["isolates"], threshold=scope.threshold,
        also_blank=["percent"])
    visible = shown[shown["isolates"] != disclosure.WITHHELD].copy()
    if not visible.empty:
        visible["isolates"] = visible["isolates"].astype(int)
        head = visible.head(15).sort_values("isolates")
        figure = px.bar(head, x="isolates", y="organism", orientation="h",
                        color_discrete_sequence=[palette.BLUE],
                        labels={"isolates": "Isolates", "organism": ""})
        figure.update_layout(height=max(340, 28 * len(head)),
                             margin=dict(t=10, b=10),
                             paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(figure, use_container_width=True)
        st.caption(
            f"The {len(head)} most frequently isolated organisms in this "
            "selection. Each patient's first isolate of an organism is counted "
            "once, so repeat sampling of one patient does not weight the "
            "ranking.")

    st.subheader("Every organism")
    _show(
        shown.rename(columns={"organism": "Organism", "isolates": "Isolates",
                              "percent": "% of isolates"}))
    if suppression.withheld:
        st.caption(suppression.summary)

    # -- where they came from -------------------------------------------
    if "specimen_type" in deduplicated.columns:
        st.subheader("Specimen types behind these isolates")
        by_type = (deduplicated
                   .drop_duplicates(["dataset_id", "isolate_id"])
                   .groupby("specimen_type", dropna=False)
                   .size().reset_index(name="isolates")
                   .sort_values("isolates", ascending=False))
        by_type["specimen_type"] = by_type["specimen_type"].fillna("Not recorded")
        shown_types, type_suppression = disclosure.apply_disclosure_control(
            by_type, ["isolates"], threshold=scope.threshold)
        _show(
            shown_types.rename(columns={"specimen_type": "Specimen type",
                                        "isolates": "Isolates"}))
        if type_suppression.withheld:
            st.caption(type_suppression.summary)
        try:
            sterile = sv.sterile_site_share(deduplicated)
        except Exception:                             # noqa: BLE001
            sterile = {}
        if sterile.get("percent") is not None:
            st.caption(
                f"{sterile['percent']:.1f}% of these isolates came from "
                "a normally sterile site. That share matters when reading any "
                "resistance figure: an isolate from blood or cerebrospinal "
                "fluid is almost certainly causing disease, while one from a "
                "wound swab may be colonising it.")

    _footer(
        f"**Method.** {dedup.summary} Counts are isolates, not susceptibility "
        "results: an organism tested against more agents does not outrank one "
        "tested against fewer.")


# ---------------------------------------------------------------------------
# One Health
# ---------------------------------------------------------------------------

def render_one_health() -> None:
    _back_bar("One Health",
              "The same surveillance across human, animal, food, "
              "environmental and aquaculture sources, counted separately.")

    frame = surveillance_frame()
    if frame.empty:
        st.info("No isolates have been published yet.")
        return

    scope = _controls(frame, "oh")
    if scope.frame.empty:
        _nothing_matches()
        return

    st.info(
        "Nothing on this page pools sectors into a single national percentage. "
        "A rate mixing hospital isolates with river water describes neither, "
        "and the platform refuses to compute one: each sector is counted on "
        "its own and compared side by side.")

    deduplicated, dedup = sv.select_first_isolates(scope.frame,
                                                   period_months=None)
    isolates = deduplicated.drop_duplicates(["dataset_id", "isolate_id"])

    per_sector = isolates.groupby("organism")["sector"].nunique()
    top = st.columns(4)
    top[0].metric("Sectors in this selection", f"{isolates['sector'].nunique():,}")
    top[1].metric("Isolates", f"{len(isolates):,}")
    top[2].metric("Organisms", f"{isolates['organism'].nunique():,}")
    top[3].metric("Found in more than one sector",
                  f"{int((per_sector > 1).sum()):,}")

    by_sector = (isolates.groupby("sector", dropna=False)
                 .size().reset_index(name="isolates")
                 .sort_values("isolates", ascending=False))
    shown, suppression = disclosure.apply_disclosure_control(
        by_sector, ["isolates"], threshold=scope.threshold)
    visible = shown[shown["isolates"] != disclosure.WITHHELD].copy()
    if not visible.empty:
        visible["isolates"] = visible["isolates"].astype(int)
        figure = px.bar(visible, x="sector", y="isolates", color="sector",
                        color_discrete_map=palette.SECTOR, text="isolates",
                        labels={"sector": "", "isolates": "Isolates"})
        figure.update_traces(textposition="outside")
        figure.update_layout(showlegend=False, height=360,
                             margin=dict(t=20, b=10),
                             paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(figure, use_container_width=True)
    _show(shown.rename(columns={"sector": "Sector",
                                       "isolates": "Isolates"}))
    if suppression.withheld:
        st.caption(suppression.summary)

    # -- organisms found in more than one sector ------------------------
    st.subheader("Organisms found in more than one sector")
    st.caption(
        "An organism appearing in people, animals and food is not evidence "
        "that it moved between them -- that needs sequencing, and the genomics "
        "section is where it is attempted. It is the reason to look.")
    cross = (isolates.groupby(["organism", "sector"], dropna=False)
             .size().reset_index(name="isolates"))
    if cross.empty:
        st.info("No organisms to compare for this selection.")
    else:
        sector_count = cross.groupby("organism")["sector"].nunique()
        shared = sector_count[sector_count > 1].index.tolist()
        if not shared:
            st.info(
                "No organism in this selection was isolated from more than one "
                "sector. With more than one sector selected above, that is a "
                "finding; with one, it is arithmetic.")
        else:
            subset = cross[cross["organism"].isin(shared)]
            shown_cross, cross_suppression = disclosure.apply_disclosure_control(
                subset, ["isolates"], group_by="organism",
                threshold=scope.threshold)
            drawable = shown_cross[
                shown_cross["isolates"] != disclosure.WITHHELD].copy()
            if not drawable.empty:
                drawable["isolates"] = drawable["isolates"].astype(int)
                figure = px.bar(
                    drawable, x="isolates", y="organism", color="sector",
                    orientation="h", barmode="group",
                    color_discrete_map=palette.SECTOR,
                    labels={"isolates": "Isolates", "organism": "",
                            "sector": "Sector"})
                figure.update_layout(
                    height=max(360, 34 * drawable["organism"].nunique()),
                    margin=dict(t=10, b=10), paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(figure, use_container_width=True)
            # A sector-by-organism grid, formatted cell by cell. Three states
            # have to stay distinguishable here and a numeric column cannot
            # hold all three: a count, "withheld" where the count was too
            # small to publish, and "none found" where the organism genuinely
            # did not appear in that sector under this selection. Collapsing
            # the last two is exactly the error this platform refuses to make.
            pivot = shown_cross.pivot_table(
                index="organism", columns="sector", values="isolates",
                aggfunc="first")
            pivot = pivot.apply(lambda column: column.map(disclosure.cell_text))
            pivot = pivot.replace("", "none found").reset_index()
            pivot.columns.name = None
            _show(pivot)
            if cross_suppression.withheld:
                st.caption(cross_suppression.summary)

    _footer(
        f"**Method.** {dedup.summary} Sector counts are isolates. Where "
        "withholding one sector's count would let it be recovered by "
        "subtracting the others from an organism's total, a second count is "
        "withheld too.")


# ---------------------------------------------------------------------------
# Genomics
# ---------------------------------------------------------------------------

def render_genomics() -> None:
    _back_bar("Genomics",
              "What sequencing adds: the mechanisms behind the resistance, and "
              "how often they explain it.")

    genomic = genomic_frame()
    if genomic.empty:
        st.info(
            "No sequencing results have been published yet. When they are, "
            "this page will show which resistance determinants were found, how "
            "often they explain the measured resistance, and how much of the "
            "collection has been sequenced.")
        return

    surveillance = surveillance_frame()
    total_isolates = (int(surveillance["isolate_id"].nunique())
                      if not surveillance.empty else None)
    coverage = gx.sequencing_coverage(genomic, total_isolates=total_isolates)

    top = st.columns(4)
    top[0].metric("Genomes", f"{coverage.get('sequenced', 0):,}")
    top[1].metric("Passed quality control", f"{coverage.get('passed_qc', 0):,}")
    top[2].metric("Typed", f"{coverage.get('typed', 0):,}")
    percent = coverage.get("percent_sequenced")
    top[3].metric("Of all isolates",
                  f"{percent:.1f}%" if percent is not None else "not known")
    st.caption(
        "Sequencing coverage is the limit on every statement on this page. A "
        "gene frequency drawn from a tenth of the collection is a statement "
        "about that tenth, and the proportion belongs beside it rather than in "
        "a footnote.")

    threshold = st.number_input(
        "Minimum cell", min_value=disclosure.MIN_PUBLIC_CELL, max_value=50,
        value=disclosure.MIN_PUBLIC_CELL, step=5, key="gx_threshold",
        help="Determinants carried by fewer genomes than this are withheld.")

    # -- what was found -------------------------------------------------
    st.subheader("Resistance determinants found")
    frequency = gx.determinant_frequency(genomic)
    if frequency.empty:
        st.info("No determinants were reported on these genomes.")
    else:
        shown, suppression = disclosure.apply_disclosure_control(
            frequency, ["isolates"], threshold=int(threshold),
            also_blank=["percent"])
        visible = shown[shown["isolates"] != disclosure.WITHHELD].copy()
        if not visible.empty:
            visible["isolates"] = visible["isolates"].astype(int)
            head = visible.head(15).sort_values("isolates")
            figure = px.bar(
                head, x="isolates", y="determinant", orientation="h",
                color_discrete_sequence=[palette.GREEN],
                hover_data={"mechanism": True, "percent": True},
                labels={"isolates": "Genomes carrying it", "determinant": ""})
            figure.update_layout(height=max(340, 28 * len(head)),
                                 margin=dict(t=10, b=10),
                                 paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(figure, use_container_width=True)
        _show(
            shown[[c for c in ("determinant", "mechanism", "isolates",
                               "genomes_examined", "percent", "database")
                   if c in shown.columns]].rename(columns={
                       "determinant": "Determinant", "mechanism": "Mechanism",
                       "isolates": "Genomes carrying it",
                       "genomes_examined": "Genomes examined",
                       "percent": "% of genomes", "database": "Database"}))
        st.caption(
            "The denominator is genomes examined, not determinants counted, so "
            "each figure reads as the proportion of sequenced isolates that "
            "carried it. Every row names the database and version behind the "
            "call: a gene result without them cannot be reproduced, for the "
            "same reason an S/I/R without its breakpoint edition cannot.")
        if suppression.withheld:
            st.caption(suppression.summary)

    # -- does it explain the phenotype ----------------------------------
    st.subheader("Do the genes explain the laboratory result?")
    try:
        table = gx.concordance(genomic)
    except Exception:                                 # noqa: BLE001
        table = pd.DataFrame()
    if table.empty:
        st.info(
            "No isolate in this selection has both a sequencing result and a "
            "susceptibility result for an agent the determinant panel covers, "
            "so there is nothing to compare.")
    else:
        summary = gx.concordance_summary(table)
        cells = st.columns(4)
        agreement = summary.get("agreement_percent")
        cells[0].metric("Agreement",
                        f"{agreement:.1f}%" if agreement is not None
                        else "not known")
        cells[1].metric("Resistance explained",
                        f"{summary.get('explained_resistance', 0):,}")
        cells[2].metric("Resistance unexplained",
                        f"{summary.get('resistance_unexplained', 0):,}")
        cells[3].metric("Gene present, tested susceptible",
                        f"{summary.get('determinant_but_susceptible', 0):,}")

        verdicts = (table["verdict"].value_counts()
                    .rename_axis("verdict").reset_index(name="pairs"))
        figure = px.bar(
            verdicts, x="pairs", y="verdict", orientation="h", color="verdict",
            color_discrete_sequence=palette.ramp(len(verdicts)),
            labels={"pairs": "Isolate-antibiotic pairs", "verdict": ""})
        figure.update_layout(showlegend=False, height=300,
                             margin=dict(t=10, b=10),
                             paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(figure, use_container_width=True)
        st.caption(
            "Absence of a known gene is not absence of a mechanism. Efflux, "
            "porin loss, a promoter change or a determinant the panel does not "
            "carry all produce resistance with nothing to find, which is why "
            "unexplained resistance is reported as its own category rather "
            "than counted as a sequencing error. A gene present on an isolate "
            "that tested susceptible is the mirror image: the gene may not be "
            "expressed, or the breakpoint may sit above what it confers.")

        agents = (table.groupby("antibiotic")
                  .agg(pairs=("verdict", "size"))
                  .reset_index().sort_values("pairs", ascending=False))
        shown_agents, agent_suppression = disclosure.apply_disclosure_control(
            agents, ["pairs"], threshold=int(threshold))
        _show(
            shown_agents.rename(columns={"antibiotic": "Antibiotic",
                                         "pairs": "Pairs compared"}))
        if agent_suppression.withheld:
            st.caption(agent_suppression.summary)

    # -- clustering -----------------------------------------------------
    st.subheader("Genomes that look alike")
    try:
        report = gx.clusters(genomic)
    except Exception:                                 # noqa: BLE001
        report = None
    # ``report.clusters`` is the per-cluster summary, not a count: one row per
    # cluster, already aggregated, with no isolate identifier on it. That is
    # what makes it publishable -- ``report.members`` is the record-level frame
    # and is deliberately not touched here.
    summary_table = getattr(report, "clusters", None)
    if summary_table is None or summary_table.empty:
        st.info(
            "No clustering has been reported on these genomes. Cluster "
            "membership is read from the sequencing pipeline rather than "
            "recomputed here, so it appears only once the pipeline has "
            "assigned it. "
            + (report.summary if report is not None else ""))
    else:
        multi = summary_table[summary_table["isolates"] > 1]
        crossing = int((summary_table["sectors"] > 1).sum())
        cells = st.columns(4)
        cells[0].metric("Clusters assigned", f"{len(summary_table):,}")
        cells[1].metric("Holding more than one genome", f"{len(multi):,}")
        cells[2].metric("Spanning more than one sector", f"{crossing:,}")
        cells[3].metric("Genomes with no cluster",
                        f"{getattr(report, 'unclustered', 0):,}")

        columns = [c for c in ("cluster_id", "method", "isolates", "organism",
                               "sector_mix", "sequence_types", "labs",
                               "span_days")
                   if c in summary_table.columns]
        # A small cluster is dropped from the table altogether rather than
        # listed with its count withheld. Withholding the number would leave
        # the row -- organism, sector, sequence type, the laboratories it
        # spans -- and a row describing two genomes is close enough to
        # describing two specimens that the count was never the disclosive
        # part. The number of dropped clusters is reported instead, so the
        # reader still knows how much of the picture is missing.
        publishable = summary_table[
            summary_table["isolates"] >= int(threshold)]
        held_back = len(summary_table) - len(publishable)
        if publishable.empty:
            st.info(
                f"Every cluster in this selection holds fewer than "
                f"{int(threshold)} genomes, so none is published. A cluster of "
                "two describes two specimens, and withholding only its size "
                "would leave the rest of the row describing them.")
            shown_clusters = pd.DataFrame()
        else:
            shown_clusters = publishable[columns]
        if held_back:
            st.caption(
                f"{held_back:,} of {len(summary_table):,} clusters are "
                f"withheld for holding fewer than {int(threshold)} genomes. "
                "Withheld is not zero: those clusters exist and are counted in "
                "the figures above.")
        if not shown_clusters.empty:
            _show(shown_clusters.rename(columns={
                "cluster_id": "Cluster", "method": "Method",
                "isolates": "Genomes", "organism": "Organism(s)",
                "sector_mix": "Sectors", "sequence_types": "Sequence type(s)",
                "labs": "Laboratories", "span_days": "Days spanned"}))
        st.caption(
            "A cluster spanning two sectors is the strongest signal this "
            "platform produces, and still not proof of transmission: cluster "
            "membership is symmetric, so it says these genomes are closely "
            "related, not which way anything moved. Direction needs dated "
            "sampling and a phylogeny.")

    _footer(
        "**Method.** Determinant calls come from the sequencing pipeline and "
        "are interpreted against a documented rule set; the mechanism column "
        "says where a determinant is not in that rule set rather than dropping "
        "it. Genomes failing quality control are excluded from frequencies and "
        "counted separately above.")


# ---------------------------------------------------------------------------
# Antimicrobial use
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _use_frames():
    return (db.get_amu_records(), db.get_amc_records(),
            db.get_pps_surveys(), db.get_pps_prescriptions())


def _pooled_block(rate, label: str, unit: str, by: str, colour: str,
                  threshold: int) -> None:
    """One pooled rate, with the share of records behind it stated."""
    table = getattr(rate, "table", None)
    if table is None or table.empty:
        st.info(f"No {label} records in scope.")
        return
    candidates = [c for c in table.columns
                  if c.startswith("ddd_per_1000") or c.startswith("mg_per_kg")]
    value = candidates[0] if candidates else None

    shown, suppression = disclosure.apply_disclosure_control(
        table, ["records"], threshold=threshold,
        also_blank=[c for c in (value,) if c])
    drawable = shown[shown["records"] != disclosure.WITHHELD].copy()
    if value and value in drawable.columns:
        drawable = drawable[drawable[value].notna()]
    if not drawable.empty and value and by in drawable.columns:
        figure = px.bar(drawable.head(20), x=by, y=value,
                        color_discrete_sequence=[colour],
                        labels={value: unit, by: ""})
        figure.update_layout(height=360, margin=dict(t=10, b=10),
                             paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(figure, use_container_width=True)
    _show(shown)
    st.caption(rate.caveat)
    if suppression.withheld:
        st.caption(suppression.summary)


def render_use() -> None:
    _back_bar("Antimicrobial use",
              "How much antimicrobial is being used, in people and in animals, "
              "and how it is prescribed.")

    amu, amc, surveys, prescriptions = _use_frames()
    if all(f is None or f.empty for f in (amu, amc, surveys)):
        st.info("No consumption or prescribing data has been published yet.")
        return

    threshold = st.number_input(
        "Minimum cell", min_value=disclosure.MIN_PUBLIC_CELL, max_value=50,
        value=disclosure.MIN_PUBLIC_CELL, step=5, key="use_threshold",
        help="Groups resting on fewer records than this are withheld.")

    st.info(
        "Every rate here is **pooled**: the numerators are added, the "
        "denominators are added, and one is divided by the other. Averaging "
        "each facility's own rate instead would give a small facility the same "
        "weight as a large one, and is the most common way a consumption "
        "figure goes wrong.")

    tabs = st.tabs(["Human use (AMU)", "Veterinary use (AMC)",
                    "Prescribing (PPS)"])

    with tabs[0]:
        st.subheader("Defined daily doses per 1,000 patient-days")
        if amu is None or amu.empty:
            st.info("No human consumption records have been published yet.")
        else:
            options = [c for c in ("region", "antibiotic_name",
                                   "report_period", "facility_name")
                       if c in amu.columns]
            by = st.selectbox(
                "Split by", options, key="amu_by",
                format_func=lambda c: c.replace("_", " ").capitalize())
            _pooled_block(consumption.pooled_ddd(amu, by=by), "human use",
                          "DDD per 1,000 patient-days", by, palette.BLUE,
                          int(threshold))
            st.caption(
                "A defined daily dose is an assumed average adult maintenance "
                "dose, not a dose anyone was given. It makes volumes "
                "comparable between agents and facilities; it does not "
                "describe the treatment of any individual patient.")

    with tabs[1]:
        st.subheader("Milligrams per kilogram of biomass")
        if amc is None or amc.empty:
            st.info("No veterinary consumption records have been published yet.")
        else:
            options = [c for c in ("species", "region", "antibiotic_class",
                                   "report_period")
                       if c in amc.columns]
            by = st.selectbox(
                "Split by", options, key="amc_by",
                format_func=lambda c: c.replace("_", " ").capitalize())
            _pooled_block(consumption.pooled_mg_per_kg(amc, by=by),
                          "veterinary use", "mg per kg biomass", by,
                          palette.ORANGE, int(threshold))
            st.caption(
                "Biomass is the denominator because animal populations differ "
                "enormously in weight: the same tonnage of antibiotic means "
                "something different across poultry than across cattle.")

    with tabs[2]:
        st.subheader("Point prevalence of antibiotic use")
        if surveys is None or surveys.empty:
            st.info("No point prevalence surveys have been published yet.")
        else:
            patients = pd.to_numeric(surveys.get("total_patients"),
                                     errors="coerce")
            on_antibiotics = pd.to_numeric(
                surveys.get("patients_on_antibiotics"), errors="coerce")
            usable = patients.notna() & on_antibiotics.notna() & (patients > 0)
            cells = st.columns(3)
            cells[0].metric("Surveys", f"{len(surveys):,}")
            cells[1].metric(
                "Patients surveyed",
                f"{int(patients[usable].sum()):,}" if usable.any()
                else "not known")
            if usable.any() and patients[usable].sum() > 0:
                prevalence = (100.0 * on_antibiotics[usable].sum()
                              / patients[usable].sum())
                cells[2].metric("On an antibiotic", f"{prevalence:.1f}%")
            else:
                cells[2].metric("On an antibiotic", "not known")
            st.caption(
                "Prevalence is pooled across surveys rather than averaged over "
                "them, so a 400-bed hospital does not count the same as a "
                "40-bed one.")

            if prescriptions is not None and not prescriptions.empty:
                for column, heading in (
                        ("indication", "Why the antibiotic was prescribed"),
                        ("route", "How it was given"),
                        ("antibiotic_name", "Which agents")):
                    if column not in prescriptions.columns:
                        continue
                    st.markdown(f"**{heading}**")
                    counts = (prescriptions.groupby(column, dropna=False)
                              .size().reset_index(name="prescriptions")
                              .sort_values("prescriptions", ascending=False))
                    counts[column] = counts[column].fillna("Not recorded")
                    shown, suppression = disclosure.apply_disclosure_control(
                        counts, ["prescriptions"], threshold=int(threshold))
                    _show(
                        shown.rename(columns={column: heading,
                                              "prescriptions": "Prescriptions"}))
                    if suppression.withheld:
                        st.caption(suppression.summary)

                documented = pd.to_numeric(
                    prescriptions.get("indication_documented"),
                    errors="coerce").fillna(0)
                if len(documented):
                    st.caption(
                        "An indication was recorded in the notes for "
                        f"{100.0 * documented.gt(0).mean():.1f}% of "
                        "prescriptions. That figure is about documentation, "
                        "not about whether the prescription was appropriate.")

    _footer(
        "**Method.** Rates are pooled, never averaged over facilities. A "
        "record carrying no usable denominator is excluded from the rate and "
        "reported as excluded, rather than counted as zero use.")


# ---------------------------------------------------------------------------
# About the data
# ---------------------------------------------------------------------------

def render_about() -> None:
    _back_bar("About this data",
              "Where these figures come from, how they are calculated, and "
              "what they do not show.")

    counts = landing_counts()
    frame = surveillance_frame()

    cells = st.columns(4)
    cells[0].metric("Specimens", f"{int(counts.get('specimens') or 0):,}")
    cells[1].metric("Isolates", f"{int(counts.get('isolates') or 0):,}")
    cells[2].metric("Susceptibility results",
                    f"{int(counts.get('results') or 0):,}")
    cells[3].metric("Laboratories", f"{int(counts.get('labs') or 0):,}")

    st.markdown(f"""
### How these figures are built

**One isolate per patient per organism.** A patient sampled four times in a
fortnight would otherwise contribute four results and shift the percentage on
their own. Following CLSI M39, the first isolate of each organism from each
patient is counted and the rest are set aside. Where the data cannot identify
the patient behind a specimen, that is said rather than quietly skipped --
reporting "0% duplicates removed" on unlinkable data looks identical to a
properly deduplicated antibiogram, and means something entirely different.

**No percentage below {sv.MIN_ISOLATES_FOR_REPORTING} isolates.** A proportion
calculated on a handful of results is not a measurement. The count is still
reported where it is large enough to publish.

**Every percentage carries a confidence interval**, computed by the Wilson
method, which stays inside 0 to 100% near the extremes where the ordinary
normal approximation does not.

**Rates are pooled, not averaged.** Numerators are summed and denominators are
summed. Averaging each facility's own rate gives a ten-bed clinic the same
weight as a teaching hospital.

**Sectors are not pooled.** Human, animal, food, environmental and aquaculture
results are counted separately unless a page says explicitly that it is
combining them.

### What is withheld

Any count resting on fewer than {disclosure.MIN_PUBLIC_CELL} records is
withheld, and so is any percentage calculated over it. Where withholding one
value would let it be recovered by subtracting the rest from a published total,
a second value is withheld as well.

**Withheld is not zero.** It means too few records to publish, not none found.
The two are shown differently throughout, because treating the first as the
second is how a suppressed table becomes a misleading one.

The minimum can be raised on any page. It cannot be lowered.

### What this does not show

No patient identifier, specimen identifier or individual result appears
anywhere on the public pages. What is published is an aggregate of records held
under the surveillance system's own access controls.

Resistance measured here describes the isolates that reached a participating
laboratory. Who gets cultured is not random: specimens arrive more often from
severe infections, from patients who have already failed treatment, and from
facilities with a laboratory on site. These figures therefore describe
laboratory-based sentinel surveillance, not the burden of resistance in the
general population.

**Laboratories are named.** Attribution is the point of sentinel surveillance,
and a rate nobody can attribute is a rate nobody can act on.
    """)

    st.subheader("Completeness of the fields these figures depend on")
    st.caption(
        "A figure can only be as complete as the field behind it. This is the "
        "part that lets a reader judge everything else: a ward-level breakdown "
        "resting on a ward field completed half the time should be read as "
        "such.")
    try:
        report = sv.coverage_report()
        completeness = getattr(report, "completeness", None)
        if completeness is not None and not completeness.empty:
            _show(completeness)
        else:
            st.info("No completeness report is available.")
    except Exception:                                 # noqa: BLE001
        st.info("The completeness report could not be produced for this data.")

    if not frame.empty:
        collected = frame["collection_datetime"].dropna()
        if not collected.empty:
            st.caption(
                "Specimens in these figures were collected between "
                f"{collected.min():%B %Y} and {collected.max():%B %Y}.")

    st.subheader("What each metric means")
    try:
        _show(sv.metric_dictionary_frame())
    except Exception:                                 # noqa: BLE001
        pass

    _footer(
        "**Method.** Every definition above is implemented once, in "
        "src/surveillance.py, and applied identically on every page. A figure "
        "that appears in two places is the same calculation in both.")


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def _stat_resistance(counts: Dict[str, object]) -> Tuple[str, str]:
    return f"{int(counts.get('results') or 0):,}", "susceptibility results"


def _stat_organisms(counts: Dict[str, object]) -> Tuple[str, str]:
    return f"{int(counts.get('organisms') or 0):,}", "organisms identified"


def _stat_one_health(counts: Dict[str, object]) -> Tuple[str, str]:
    return f"{int(counts.get('sectors') or 0):,}", "sectors under surveillance"


def _stat_genomics(counts: Dict[str, object]) -> Tuple[str, str]:
    return f"{int(counts.get('genomes') or 0):,}", "genomes sequenced"


def _stat_use(counts: Dict[str, object]) -> Tuple[str, str]:
    total = (int(counts.get("amu") or 0) + int(counts.get("amc") or 0)
             + int(counts.get("pps") or 0))
    return f"{total:,}", "use and prescribing records"


def _stat_about(counts: Dict[str, object]) -> Tuple[str, str]:
    return f"{int(counts.get('labs') or 0):,}", "contributing laboratories"


SECTIONS: List[Section] = [
    Section(PREFIX + "resistance", "AST", "Resistance",
            "Susceptibility by organism and antibiotic, with the number of "
            "isolates behind every figure, and where the resistance sits.",
            palette.BLUE, _stat_resistance),
    Section(PREFIX + "organisms", "ORG", "Organisms",
            "What is being isolated, counted as isolates rather than as test "
            "results, and the specimens they came from.",
            palette.VERMILLION, _stat_organisms),
    Section(PREFIX + "one-health", "OH", "One Health",
            "Human, animal, food, environmental and aquaculture surveillance "
            "side by side, never pooled into one national rate.",
            palette.GREEN, _stat_one_health),
    Section(PREFIX + "genomics", "WGS", "Genomics",
            "The mechanisms behind the resistance, how often they explain the "
            "laboratory result, and which genomes look alike.",
            palette.PURPLE, _stat_genomics),
    Section(PREFIX + "use", "AMU", "Antimicrobial use",
            "Human and veterinary consumption and hospital prescribing, as "
            "pooled rates with their denominators.",
            palette.ORANGE, _stat_use),
    Section(PREFIX + "about", "DOC", "About this data",
            "How every figure is calculated, what is withheld and why, and "
            "what laboratory-based surveillance cannot tell you.",
            palette.SKY, _stat_about),
]

RENDERERS: Dict[str, Callable[[], None]] = {
    PREFIX + "resistance": render_resistance,
    PREFIX + "organisms": render_organisms,
    PREFIX + "one-health": render_one_health,
    PREFIX + "genomics": render_genomics,
    PREFIX + "use": render_use,
    PREFIX + "about": render_about,
}


def render_public_page(key: str) -> bool:
    """Render one public section page. False if the key is not one of ours."""
    renderer = RENDERERS.get(key)
    if renderer is None:
        return False
    renderer()
    return True


__all__ = ["PREFIX", "Section", "SECTIONS", "RENDERERS", "render_public_page",
           "landing_counts", "surveillance_frame", "genomic_frame", "go"]
