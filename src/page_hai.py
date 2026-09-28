"""
Hospital-Acquired Infection (HAI) Profile page module.
Dedicated HAI surveillance tab that GASS has — enhanced with:
• Nosocomial pathogen flagging (ESKAPE + extended)
• Collection-date vs admission surrogate analysis
• HAI-associated organism resistance profiles
• Ward/site-type breakdown
• MDRO in HAI context
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from src import db

# ── Known nosocomial / ESKAPE pathogens ─────────────────────────────────
ESKAPE_PATHOGENS = {
    "Enterococcus faecium",
    "Staphylococcus aureus",
    "Klebsiella pneumoniae",
    "Acinetobacter baumannii",
    "Pseudomonas aeruginosa",
    "Enterobacter",
}

# Extended nosocomial list (WHO critical + high priority organisms)
NOSOCOMIAL_KEYWORDS = [
    "enterococcus", "staphylococcus aureus", "klebsiella",
    "acinetobacter", "pseudomonas aeruginosa", "enterobacter",
    "escherichia coli", "serratia", "citrobacter", "proteus",
    "stenotrophomonas", "burkholderia", "clostridioides",
    "clostridium difficile", "candida",
]

# Site types that are hospital/clinical
HOSPITAL_SITE_TYPES = {
    "hospital", "clinic", "health center", "health centre",
    "teaching hospital", "regional hospital", "district hospital",
    "polyclinic", "medical centre", "medical center",
}

# ── Styling ─────────────────────────────────────────────────────────────
CARD_CSS = """
<style>
.kpi-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.kpi-card {
    flex: 1; min-width: 140px; padding: 1.2rem 1rem; border-radius: 12px;
    text-align: center; border: 1px solid rgba(0,0,0,0.08);
}
.kpi-card.blue   { background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); }
.kpi-card.green  { background: linear-gradient(135deg, #1a4d2e 0%, #0d2818 100%); }
.kpi-card.amber  { background: linear-gradient(135deg, #5c4a1e 0%, #3d3010 100%); }
.kpi-card.red    { background: linear-gradient(135deg, #5c1e1e 0%, #3d1010 100%); }
.kpi-card.purple { background: linear-gradient(135deg, #4a1e5c 0%, #2d1038 100%); }
.kpi-card .value { font-size: 2rem; font-weight: 700; color: #fff; }
.kpi-card .label { font-size: 0.82rem; color: rgba(255,255,255,0.65); margin-top: 0.25rem; }
.section-divider { border: none; border-top: 1px solid rgba(0,0,0,0.10); margin: 2rem 0 1.5rem; }
.hai-alert {
    background: linear-gradient(135deg, #fef2f2, #fee2e2);
    border-left: 4px solid #ef4444; border-radius: 10px;
    padding: 1rem 1.2rem; margin-bottom: 1rem;
    font-size: 0.92rem; color: #991b1b;
}
</style>
"""

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1e293b", size=13), margin=dict(l=40, r=20, t=50, b=40),
    title_font_size=17,
)


def _kpi(value, label, color="blue"):
    return f'<div class="kpi-card {color}"><div class="value">{value}</div><div class="label">{label}</div></div>'


def _is_nosocomial(organism: str) -> bool:
    """Check whether an organism is a known nosocomial pathogen."""
    org_lower = str(organism).lower()
    return any(kw in org_lower for kw in NOSOCOMIAL_KEYWORDS)


def _is_hospital_sample(row) -> bool:
    """Heuristic: sample came from a hospital/clinical setting."""
    site = str(row.get("site_type", "")).lower()
    source = str(row.get("source_category", "")).lower()
    return source == "human" or any(h in site for h in HOSPITAL_SITE_TYPES)


# MDR classification is delegated to src/mdr.py. A local copy of the class
# map used to live here -- the third in the codebase, after src/alerts.py and
# src/analytics.py -- and it carried the same three defects: one generic map
# applied to every organism where the agreed definitions are
# organism-specific; only 'R' counted, where the definitions use
# non-susceptible (I or R); and intrinsic resistance counted towards the
# total, so every Klebsiella scored a category for the ampicillin it was
# always resistant to.


def _classify_abx(name: str) -> str:
    """Antimicrobial category for display grouping.

    Enterobacterales categories are used as the label set, since this page is
    about hospital Gram-negatives; the MDR decision itself is organism-specific
    and comes from src.mdr.
    """
    from src import mdr as _mdr
    category = _mdr.categorise_agent(
        name, _mdr.CATEGORY_SETS["Enterobacterales"])
    return category or "Other"


def _mdr_isolate_ids(ast_df: pd.DataFrame) -> set:
    """Isolate ids meeting the MDR definition or worse.

    Uses the organism-specific category sets, counts non-susceptible rather
    than resistant only, and excludes intrinsic resistance.
    """
    from src import mdr as _mdr
    if ast_df.empty:
        return set()
    classified = _mdr.classify_frame(ast_df)
    if classified.empty:
        return set()
    multidrug = classified[classified['classification'].isin(
        [_mdr.CLASS_MDR, _mdr.CLASS_XDR, _mdr.CLASS_PDR])]
    return set(multidrug['isolate_id'].astype(str))


# ════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════

def render_hai_page():
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    st.header("Hospital-Acquired Infection (HAI) Profile")
    st.caption(
        "Surveillance of nosocomial pathogens, ESKAPE organisms, MDR in hospital "
        "settings, and HAI-associated resistance patterns."
    )

    # ── require dataset ─────────────────────────────────────────────────
    if not st.session_state.get("active_dataset_id"):
        st.warning("Please select a dataset in the **Data Management** page first.")
        return

    dataset_id = st.session_state.active_dataset_id
    all_ast = db.get_dataset_ast(dataset_id)
    all_samples = db.get_dataset_samples(dataset_id)

    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
        return

    # ── Filter to hospital / clinical samples ───────────────────────────
    all_samples = all_samples.copy()
    all_samples["_is_hospital"] = all_samples.apply(_is_hospital_sample, axis=1)
    hospital_samples = all_samples[all_samples["_is_hospital"]]

    if hospital_samples.empty:
        st.info("No hospital / clinical samples found. HAI analysis requires HUMAN source or hospital site_type data.")
        return

    hospital_ast = all_ast[all_ast["sample_id"].astype(str).isin(hospital_samples["sample_id"].astype(str))]

    if hospital_ast.empty:
        st.info("No AST results linked to hospital samples.")
        return

    # ── Clean result values ──────────────────────────────────────────────
    hospital_ast = hospital_ast.copy()
    hospital_ast = hospital_ast.dropna(subset=["result", "organism", "antibiotic", "isolate_id"])
    hospital_ast = hospital_ast[hospital_ast["result"].isin(["R", "I", "S"])]
    # Also strip empty strings that survive dropna
    for _col in ("organism", "antibiotic", "isolate_id"):
        hospital_ast[_col] = hospital_ast[_col].astype(str).str.strip()
        hospital_ast = hospital_ast[hospital_ast[_col] != ""]

    if hospital_ast.empty:
        st.info("No valid AST results linked to hospital samples.")
        return

    # ── Flag nosocomial organisms ───────────────────────────────────────
    hospital_ast["is_nosocomial"] = hospital_ast["organism"].apply(_is_nosocomial)
    nosocomial_ast = hospital_ast[hospital_ast["is_nosocomial"]]

    # ── MDR detection ───────────────────────────────────────────────────
    mdr_isolate_ids = _mdr_isolate_ids(hospital_ast)
    hospital_ast["is_mdr"] = hospital_ast["isolate_id"].isin(mdr_isolate_ids)

    # ── KPIs ────────────────────────────────────────────────────────────
    total_hospital_tests = len(hospital_ast)
    total_hospital_isolates = hospital_ast["isolate_id"].nunique()
    nosocomial_isolates = nosocomial_ast["isolate_id"].nunique()
    nosocomial_pct = nosocomial_isolates / max(1, total_hospital_isolates) * 100
    mdr_count = len(mdr_isolate_ids)
    mdr_pct = mdr_count / max(1, total_hospital_isolates) * 100
    overall_r = (hospital_ast["result"] == "R").sum() / max(1, total_hospital_tests) * 100

    st.markdown(
        '<div class="kpi-row">'
        + _kpi(f"{total_hospital_isolates:,}", "Hospital Isolates", "blue")
        + _kpi(f"{nosocomial_isolates:,}", f"Nosocomial Pathogens ({nosocomial_pct:.0f}%)", "amber")
        + _kpi(f"{mdr_count:,}", f"MDR Isolates ({mdr_pct:.0f}%)", "red")
        + _kpi(f"{overall_r:.1f}%", "Hospital Resistance Rate", "red" if overall_r >= 40 else "amber")
        + _kpi(hospital_ast["organism"].nunique(), "Organisms Detected", "purple")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Alert banner ────────────────────────────────────────────────────
    if mdr_pct >= 30:
        st.markdown(
            f'<div class="hai-alert">⚠️ <b>High MDR burden:</b> {mdr_pct:.0f}% of hospital isolates '
            f"are multi-drug resistant (≥3 antibiotic classes). Infection prevention review recommended.</div>",
            unsafe_allow_html=True,
        )

    # ── TABS ────────────────────────────────────────────────────────────
    tab_eskape, tab_resist, tab_mdr, tab_site, tab_trend = st.tabs([
        "ESKAPE Organisms", "Resistance Profile", "MDR Analysis",
        "Site / Lab Breakdown", "HAI Trends",
    ])

    # ── Tab 1: ESKAPE ───────────────────────────────────────────────────
    with tab_eskape:
        st.subheader("ESKAPE Pathogen Surveillance")
        st.markdown(
            "The **ESKAPE** group (*Enterococcus faecium, Staphylococcus aureus, "
            "Klebsiella pneumoniae, Acinetobacter baumannii, Pseudomonas aeruginosa, "
            "Enterobacter* spp.) are the leading cause of nosocomial infections worldwide."
        )

        eskape_data = []
        for org_key in ESKAPE_PATHOGENS:
            match = hospital_ast[hospital_ast["organism"].str.contains(org_key, case=False, na=False)]
            if match.empty:
                continue
            n_tests = len(match)
            n_r = int((match["result"] == "R").sum())
            n_isolates = match["isolate_id"].nunique()
            mdr_iso = match[match["is_mdr"]]["isolate_id"].nunique()
            eskape_data.append({
                "Organism": org_key,
                "Isolates": n_isolates,
                "Tests": n_tests,
                "Resistance %": round(n_r / n_tests * 100, 1) if n_tests else 0,
                "MDR Isolates": mdr_iso,
                "MDR %": round(mdr_iso / max(1, n_isolates) * 100, 1),
            })

        if eskape_data:
            eskape_df = pd.DataFrame(eskape_data).sort_values("Resistance %", ascending=False)
            st.dataframe(eskape_df, use_container_width=True, hide_index=True)

            # ESKAPE resistance chart
            fig = px.bar(
                eskape_df, x="Organism", y="Resistance %",
                color="Resistance %", color_continuous_scale="RdYlGn_r",
                text="Resistance %", hover_data=["Isolates", "MDR %"],
                title="ESKAPE Pathogen Resistance Rates",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(**CHART_LAYOUT, height=400, showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No ESKAPE pathogens detected in hospital samples.")

    # ── Tab 2: Resistance Profile ───────────────────────────────────────
    with tab_resist:
        st.subheader("Hospital Resistance Profile")

        # Top 15 organisms by test count
        org_stats = hospital_ast.groupby("organism").apply(
            lambda g: pd.Series({
                "Tests": len(g),
                "Resistance %": round((g["result"] == "R").sum() / len(g) * 100, 1),
                "Nosocomial": "Yes" if _is_nosocomial(g.name) else "No",
            }),
            include_groups=False,
        ).reset_index().sort_values("Tests", ascending=False).head(15)

        fig = px.bar(
            org_stats.sort_values("Resistance %", ascending=True),
            y="organism", x="Resistance %", orientation="h",
            color="Nosocomial",
            color_discrete_map={"Yes": "#ef4444", "No": "#94a3b8"},
            text="Resistance %",
            hover_data=["Tests"],
            title="Top 15 Organisms — Hospital Resistance",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(**CHART_LAYOUT, height=max(350, 28 * len(org_stats) + 80))
        st.plotly_chart(fig, use_container_width=True)

        # Nosocomial vs community comparison
        st.markdown("**Nosocomial vs Non-Nosocomial Resistance**")
        noso_r = (nosocomial_ast["result"] == "R").sum() / max(1, len(nosocomial_ast)) * 100 if not nosocomial_ast.empty else 0
        community_ast = hospital_ast[~hospital_ast["is_nosocomial"]]
        comm_r = (community_ast["result"] == "R").sum() / max(1, len(community_ast)) * 100 if not community_ast.empty else 0

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                _kpi(f"{noso_r:.1f}%", f"Nosocomial organisms ({nosocomial_ast['isolate_id'].nunique()} isolates)", "red"),
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                _kpi(f"{comm_r:.1f}%", f"Other organisms ({community_ast['isolate_id'].nunique()} isolates)", "green"),
                unsafe_allow_html=True,
            )

    # ── Tab 3: MDR Analysis ─────────────────────────────────────────────
    with tab_mdr:
        st.subheader("Multi-Drug Resistance in Hospital Setting")

        mdr_ast = hospital_ast[hospital_ast["is_mdr"]]
        if mdr_ast.empty:
            st.info("No MDR isolates detected in hospital samples.")
        else:
            # MDR organism distribution
            mdr_org = mdr_ast.groupby("organism")["isolate_id"].nunique().reset_index()
            mdr_org.columns = ["Organism", "MDR Isolates"]
            mdr_org = mdr_org.sort_values("MDR Isolates", ascending=False).head(15)

            fig = px.bar(
                mdr_org.sort_values("MDR Isolates", ascending=True),
                y="Organism", x="MDR Isolates", orientation="h",
                color="MDR Isolates", color_continuous_scale="Reds",
                text="MDR Isolates",
                title="MDR Organism Distribution",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(**CHART_LAYOUT, height=max(300, 28 * len(mdr_org) + 80),
                              showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

            # MDR class breakdown for top organism
            if not mdr_org.empty:
                top_mdr_org = mdr_org.iloc[0]["Organism"]
                st.markdown(f"**Antibiotic class resistance for top MDR organism: {top_mdr_org}**")
                top_mdr_data = mdr_ast[mdr_ast["organism"] == top_mdr_org]
                top_mdr_data = top_mdr_data.copy()
                top_mdr_data["abx_class"] = top_mdr_data["antibiotic"].apply(_classify_abx)
                class_stats = top_mdr_data.groupby("abx_class").apply(
                    lambda g: round((g["result"] == "R").sum() / len(g) * 100, 1) if len(g) else 0,
                    include_groups=False,
                ).reset_index(name="Resistance %").sort_values("Resistance %", ascending=False)
                class_stats.columns = ["Antibiotic Class", "Resistance %"]
                st.dataframe(class_stats, use_container_width=True, hide_index=True)

    # ── Tab 4: Site / Lab Breakdown ─────────────────────────────────────
    with tab_site:
        st.subheader("HAI by Sentinel Site / Laboratory")

        lab_col = "lab_name" if "lab_name" in hospital_samples.columns else None
        if lab_col:
            merged = hospital_ast.merge(hospital_samples[["sample_id", lab_col]], on="sample_id", how="left")
            merged = merged.dropna(subset=[lab_col])
            lab_stats = merged.groupby(lab_col).apply(
                lambda g: pd.Series({
                    "Tests": len(g),
                    "Isolates": g["isolate_id"].nunique(),
                    "Resistance %": round((g["result"] == "R").sum() / len(g) * 100, 1),
                    "MDR Isolates": g[g["is_mdr"]]["isolate_id"].nunique(),
                }),
                include_groups=False,
            ).reset_index().sort_values("Resistance %", ascending=False)

            # Rename the lab_name column
            lab_stats = lab_stats.rename(columns={lab_col: "Sentinel Site"})

            st.dataframe(lab_stats, use_container_width=True, hide_index=True)

            fig = px.bar(
                lab_stats.sort_values("Resistance %", ascending=True),
                y="Sentinel Site", x="Resistance %", orientation="h",
                color="Resistance %", color_continuous_scale="RdYlGn_r",
                text="Resistance %", hover_data=["Tests", "MDR Isolates"],
                title="Resistance by Sentinel Site",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(**CHART_LAYOUT, height=max(300, 30 * len(lab_stats) + 80),
                              showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sentinel site / lab information in the data.")

        # Region breakdown
        if "region" in hospital_samples.columns:
            st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
            st.markdown("**HAI by Region**")
            merged_r = hospital_ast.merge(hospital_samples[["sample_id", "region"]], on="sample_id", how="left")
            merged_r = merged_r.dropna(subset=["region"])
            region_stats = merged_r.groupby("region").apply(
                lambda g: pd.Series({
                    "Tests": len(g),
                    "Resistance %": round((g["result"] == "R").sum() / len(g) * 100, 1),
                    "MDR Isolates": g[g["is_mdr"]]["isolate_id"].nunique(),
                }),
                include_groups=False,
            ).reset_index().sort_values("Resistance %", ascending=False)

            st.dataframe(region_stats, use_container_width=True, hide_index=True)

    # ── Tab 5: HAI Trends ───────────────────────────────────────────────
    with tab_trend:
        st.subheader("Hospital Infection Trends")

        hospital_ast_t = hospital_ast.copy()
        hospital_ast_t["test_date"] = pd.to_datetime(hospital_ast_t["test_date"], errors="coerce")
        hospital_ast_t = hospital_ast_t.dropna(subset=["test_date"])

        if hospital_ast_t.empty:
            st.info("No date information available for trend analysis.")
        else:
            hospital_ast_t["month"] = hospital_ast_t["test_date"].dt.to_period("M")

            monthly = hospital_ast_t.groupby("month").apply(
                lambda g: pd.Series({
                    "pct_r": round((g["result"] == "R").sum() / len(g) * 100, 1),
                    "mdr_pct": round(g["is_mdr"].sum() / max(1, g["isolate_id"].nunique()) * 100, 1),
                    "nosocomial_pct": round(g["is_nosocomial"].sum() / max(1, len(g)) * 100, 1),
                    "n": len(g),
                }),
                include_groups=False,
            ).reset_index()
            monthly["month_str"] = monthly["month"].astype(str)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=monthly["month_str"], y=monthly["pct_r"],
                mode="lines+markers", name="Overall Resistance %",
                line=dict(color="#ef4444", width=3), marker=dict(size=7),
            ))
            fig.add_trace(go.Scatter(
                x=monthly["month_str"], y=monthly["mdr_pct"],
                mode="lines+markers", name="MDR %",
                line=dict(color="#8b5cf6", width=2, dash="dash"), marker=dict(size=6),
            ))
            fig.add_trace(go.Scatter(
                x=monthly["month_str"], y=monthly["nosocomial_pct"],
                mode="lines+markers", name="Nosocomial %",
                line=dict(color="#f59e0b", width=2, dash="dot"), marker=dict(size=6),
            ))
            fig.update_layout(
                **CHART_LAYOUT, height=420,
                title="Hospital Infection Trends — Monthly",
                xaxis_title="Month", yaxis_title="Percentage (%)",
                legend=dict(orientation="h", y=-0.15),
            )
            st.plotly_chart(fig, use_container_width=True)
