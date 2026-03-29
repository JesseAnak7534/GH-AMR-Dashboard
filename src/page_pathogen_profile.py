"""
Pathogen Profile page module.
Deep-dive per-organism analysis: resistance patterns, trends, mechanisms,
geographic spread, antibiogram row, and risk score — a feature GASS lacks.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from src import db
from src.analytics import (
    detect_resistance_mechanisms,
    calculate_organism_risk_score,
    generate_antibiotic_recommendations,
    calculate_trend_direction,
)

# ── Shared styling ──────────────────────────────────────────────────────
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
.risk-badge {
    display: inline-block; padding: 0.35rem 0.85rem; border-radius: 999px;
    font-size: 0.82rem; font-weight: 700; letter-spacing: 0.03em;
}
.risk-critical { background: #fecaca; color: #991b1b; }
.risk-high     { background: #fed7aa; color: #9a3412; }
.risk-moderate { background: #fef08a; color: #854d0e; }
.risk-low      { background: #bbf7d0; color: #166534; }
</style>
"""

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1e293b"), margin=dict(l=40, r=20, t=50, b=40),
    title_font_size=16,
)


def _kpi(value, label, color="blue"):
    return f'<div class="kpi-card {color}"><div class="value">{value}</div><div class="label">{label}</div></div>'


def _risk_badge(level):
    css = {"CRITICAL": "risk-critical", "HIGH": "risk-high",
           "MODERATE": "risk-moderate", "LOW": "risk-low"}.get(level, "risk-low")
    return f'<span class="risk-badge {css}">{level}</span>'


# ════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════

def render_pathogen_profile_page():
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    st.header("Pathogen Profile")
    st.caption(
        "Select an organism for a comprehensive deep-dive: resistance patterns, "
        "trend direction, detected mechanisms, geographic spread, antibiogram row, "
        "risk score, and treatment recommendations."
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

    # ── organism selector ───────────────────────────────────────────────
    org_counts = all_ast["organism"].value_counts()
    org_list = org_counts.index.tolist()

    if not org_list:
        st.info("No organisms found in the dataset.")
        return

    selected_org = st.selectbox(
        "Select Organism",
        org_list,
        format_func=lambda o: f"{o}  ({org_counts[o]:,} tests)",
        key="pp_org",
    )

    org_ast = all_ast[all_ast["organism"] == selected_org]
    org_samples = all_samples[all_samples["sample_id"].isin(org_ast["sample_id"])]

    if org_ast.empty:
        st.warning("No AST data for the selected organism.")
        return

    # ── KPI row ─────────────────────────────────────────────────────────
    total_tests = len(org_ast)
    n_resistant = int((org_ast["result"] == "R").sum())
    n_susceptible = int((org_ast["result"] == "S").sum())
    overall_r = n_resistant / total_tests * 100 if total_tests else 0
    unique_abx = org_ast["antibiotic"].nunique()
    unique_samples = org_ast["sample_id"].nunique()

    # Risk score
    try:
        org_risk = calculate_organism_risk_score(all_ast, selected_org)
        risk_score = org_risk.get("risk_score", 0)
        risk_level = org_risk.get("risk_level", "LOW")
    except Exception:
        risk_score = 0
        risk_level = "LOW"

    st.markdown(
        '<div class="kpi-row">'
        + _kpi(f"{total_tests:,}", "Total Tests", "blue")
        + _kpi(f"{overall_r:.1f}%", "Resistance Rate", "red" if overall_r >= 40 else "amber")
        + _kpi(unique_abx, "Antibiotics Tested", "green")
        + _kpi(unique_samples, "Isolates / Samples", "purple")
        + _kpi(f"{risk_score:.0f}/100", f"Risk: {risk_level}", "red" if risk_level == "CRITICAL" else "amber")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── TABS ────────────────────────────────────────────────────────────
    tab_abx, tab_trend, tab_mech, tab_geo, tab_rec = st.tabs([
        "Antimicrobial Profile", "Resistance Trends", "Mechanisms",
        "Geographic Spread", "Recommendations",
    ])

    # ── Tab 1: Antimicrobial Profile ────────────────────────────────────
    with tab_abx:
        st.subheader(f"Antimicrobial Susceptibility — {selected_org}")
        abx_stats = org_ast.groupby("antibiotic").apply(
            lambda g: pd.Series({
                "R": int((g["result"] == "R").sum()),
                "I": int((g["result"] == "I").sum()),
                "S": int((g["result"] == "S").sum()),
                "total": len(g),
            }),
            include_groups=False,
        ).reset_index()
        abx_stats["pct_r"] = (abx_stats["R"] / abx_stats["total"] * 100).round(1)
        abx_stats["pct_s"] = (abx_stats["S"] / abx_stats["total"] * 100).round(1)
        abx_stats = abx_stats.sort_values("pct_r", ascending=True)

        # Horizontal stacked bar S / I / R
        fig = go.Figure()
        for res, colour, label in [("S", "#22c55e", "Susceptible"), ("I", "#f59e0b", "Intermediate"), ("R", "#ef4444", "Resistant")]:
            fig.add_trace(go.Bar(
                y=abx_stats["antibiotic"],
                x=abx_stats[res] / abx_stats["total"] * 100,
                name=label,
                orientation="h",
                marker_color=colour,
                hovertemplate="%{y}: %{x:.1f}%<extra>" + label + "</extra>",
            ))
        fig.update_layout(
            **CHART_LAYOUT,
            barmode="stack",
            height=max(350, 24 * len(abx_stats) + 80),
            legend=dict(orientation="h", y=-0.12),
            xaxis_title="Percentage (%)",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Antibiogram-style table
        with st.expander("Antibiogram row", expanded=False):
            display_df = abx_stats[["antibiotic", "pct_s", "pct_r", "total"]].copy()
            display_df.columns = ["Antibiotic", "%S", "%R", "n"]
            display_df = display_df.sort_values("%R", ascending=False)
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Tab 2: Resistance Trends ────────────────────────────────────────
    with tab_trend:
        st.subheader(f"Resistance Trends — {selected_org}")
        org_ast_t = org_ast.copy()
        org_ast_t["test_date"] = pd.to_datetime(org_ast_t["test_date"], errors="coerce")
        org_ast_t = org_ast_t.dropna(subset=["test_date"])

        if org_ast_t.empty:
            st.info("No valid dates available for trend analysis.")
        else:
            # Monthly resistance %
            org_ast_t["month"] = org_ast_t["test_date"].dt.to_period("M")
            monthly = org_ast_t.groupby("month").apply(
                lambda g: pd.Series({
                    "pct_r": (g["result"] == "R").sum() / len(g) * 100,
                    "n": len(g),
                }),
                include_groups=False,
            ).reset_index()
            monthly["month_str"] = monthly["month"].astype(str)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=monthly["month_str"], y=monthly["pct_r"],
                mode="lines+markers",
                line=dict(color="#ef4444", width=3),
                marker=dict(size=8),
                name="Resistance %",
                hovertemplate="%{x}: %{y:.1f}% (n=%{customdata})<extra></extra>",
                customdata=monthly["n"],
            ))
            fig.update_layout(**CHART_LAYOUT, height=400, xaxis_title="Month", yaxis_title="Resistance %")
            st.plotly_chart(fig, use_container_width=True)

            # Trend direction per top antibiotic
            st.markdown("**Trend direction per antibiotic (last 6 months)**")
            top_abx = org_ast_t["antibiotic"].value_counts().head(10).index
            trend_rows = []
            for abx in top_abx:
                sub = org_ast_t[org_ast_t["antibiotic"] == abx]
                try:
                    td = calculate_trend_direction(sub)
                    trend_rows.append({
                        "Antibiotic": abx,
                        "Direction": td.get("direction", "STABLE"),
                        "Change %": round(td.get("change_percentage", 0), 1),
                        "Tests": len(sub),
                    })
                except Exception:
                    trend_rows.append({"Antibiotic": abx, "Direction": "N/A", "Change %": 0, "Tests": len(sub)})
            if trend_rows:
                st.dataframe(pd.DataFrame(trend_rows), use_container_width=True, hide_index=True)

    # ── Tab 3: Resistance Mechanisms ────────────────────────────────────
    with tab_mech:
        st.subheader(f"Detected Resistance Mechanisms — {selected_org}")
        try:
            mech_df = detect_resistance_mechanisms(org_ast)
            if mech_df.empty:
                st.info("No specific resistance mechanisms detected for this organism.")
            else:
                mech_summary = mech_df["resistance_mechanism"].value_counts().reset_index()
                mech_summary.columns = ["Mechanism", "Isolates"]

                fig = px.bar(
                    mech_summary, x="Mechanism", y="Isolates",
                    color="Mechanism",
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                fig.update_layout(**CHART_LAYOUT, height=350, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

                with st.expander("Mechanism detail table"):
                    st.dataframe(
                        mech_df[["isolate_id", "resistance_mechanism", "confidence"]].head(50),
                        use_container_width=True, hide_index=True,
                    )
        except Exception as e:
            st.warning(f"Mechanism detection error: {e}")

    # ── Tab 4: Geographic Spread ────────────────────────────────────────
    with tab_geo:
        st.subheader(f"Geographic Distribution — {selected_org}")
        if org_samples.empty or "region" not in org_samples.columns:
            st.info("No geographic information available for this organism.")
        else:
            region_counts = org_samples["region"].value_counts().reset_index()
            region_counts.columns = ["Region", "Isolates"]

            # Merge resistance rate per region
            merged = org_ast.merge(all_samples[["sample_id", "region"]], on="sample_id", how="left")
            merged = merged.dropna(subset=["region"])
            region_r = merged.groupby("region").apply(
                lambda g: round((g["result"] == "R").sum() / len(g) * 100, 1) if len(g) else 0,
                include_groups=False,
            ).reset_index(name="Resistance %")

            region_full = region_counts.merge(region_r, left_on="Region", right_on="region", how="left").drop(columns=["region"], errors="ignore")

            fig = px.bar(
                region_full.sort_values("Resistance %", ascending=True),
                y="Region", x="Resistance %", orientation="h",
                color="Resistance %",
                color_continuous_scale="RdYlGn_r",
                text="Resistance %",
                hover_data=["Isolates"],
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(
                **CHART_LAYOUT,
                height=max(300, 30 * len(region_full) + 80),
                showlegend=False, coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Source category breakdown
            if "source_category" in org_samples.columns:
                st.markdown("**Source category breakdown**")
                cat_counts = org_samples["source_category"].value_counts().reset_index()
                cat_counts.columns = ["Source", "Count"]
                fig2 = px.pie(cat_counts, names="Source", values="Count", hole=0.4,
                              color_discrete_sequence=px.colors.qualitative.Set2)
                fig2.update_layout(**CHART_LAYOUT, height=300)
                st.plotly_chart(fig2, use_container_width=True)

    # ── Tab 5: Recommendations ──────────────────────────────────────────
    with tab_rec:
        st.subheader(f"Treatment Recommendations — {selected_org}")
        try:
            recs = generate_antibiotic_recommendations(org_ast)
            if not recs:
                st.info("Not enough data to generate recommendations.")
            else:
                # Group by priority
                priority_map = {1: "PREFERRED", 2: "GOOD", 3: "CAUTION", 4: "AVOID"}
                for pri_num, (priority_label, colour) in enumerate([("PREFERRED", "#22c55e"), ("GOOD", "#84cc16"), ("CAUTION", "#f59e0b"), ("AVOID", "#ef4444")], 1):
                    group = [r for r in recs if r.get("priority") == pri_num]
                    if group:
                        st.markdown(f"**{priority_label}** ({len(group)} antibiotics)")
                        for r in group:
                            pct_s = r.get("susceptibility_rate", 0)
                            abx = r.get("antibiotic", "?")
                            n = r.get("tests", 0)
                            bar_width = max(5, pct_s)
                            st.markdown(
                                f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;">'
                                f'<span style="min-width:160px;font-size:0.9rem;color:#334155;">{abx}</span>'
                                f'<div style="flex:1;background:#e2e8f0;border-radius:6px;height:18px;overflow:hidden;">'
                                f'<div style="width:{bar_width}%;background:{colour};height:100%;border-radius:6px;"></div>'
                                f'</div>'
                                f'<span style="min-width:65px;font-size:0.82rem;color:#64748b;">{pct_s:.0f}% S (n={n})</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                        st.markdown("")
        except Exception as e:
            st.warning(f"Recommendation error: {e}")
