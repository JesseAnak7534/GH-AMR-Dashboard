"""
Resistance Heat Map page module.
Interactive organism × antibiotic heatmap with filtering, clustering,
and threshold-based colour coding — surpassing GASS heatmap capabilities.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from src import db

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
.legend-box {
    display: flex; gap: 0.75rem; flex-wrap: wrap; justify-content: center;
    margin-bottom: 1rem; padding: 0.6rem 1rem; background: #f8fafc;
    border-radius: 10px; border: 1px solid #e2e8f0;
}
.legend-item { display: flex; align-items: center; gap: 0.3rem; font-size: 0.82rem; color: #334155; }
.legend-swatch { width: 18px; height: 14px; border-radius: 3px; display: inline-block; }
</style>
"""

def _kpi(value, label, color="blue"):
    return f'<div class="kpi-card {color}"><div class="value">{value}</div><div class="label">{label}</div></div>'


# ── Colour helpers (CLSI-style colour scale) ────────────────────────────
def _resistance_color(pct):
    """Return colour for a resistance percentage (CLSI antibiogram style)."""
    if pct >= 70:
        return "rgb(220, 38, 38)"     # red – high resistance
    elif pct >= 40:
        return "rgb(234, 88, 12)"     # orange – moderate
    elif pct >= 20:
        return "rgb(234, 179, 8)"     # yellow – low-moderate
    elif pct > 0:
        return "rgb(34, 197, 94)"     # green – low
    else:
        return "rgb(209, 213, 219)"   # grey – no resistance


def _build_colorscale():
    """Custom discrete-like colour scale for the heatmap."""
    return [
        [0.0,  "rgb(34, 197, 94)"],    # 0 %  – green
        [0.20, "rgb(34, 197, 94)"],
        [0.20, "rgb(234, 179, 8)"],     # 20 % – yellow
        [0.40, "rgb(234, 179, 8)"],
        [0.40, "rgb(234, 88, 12)"],     # 40 % – orange
        [0.70, "rgb(234, 88, 12)"],
        [0.70, "rgb(220, 38, 38)"],     # 70 % – red
        [1.0,  "rgb(220, 38, 38)"],
    ]


# ════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════

def render_heatmap_page():
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    st.header("Resistance Heat Map")
    st.caption(
        "Interactive organism × antibiotic resistance matrix with threshold-based "
        "colour coding.  Filter by source, region, site, and resistance tier."
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

    # ── sidebar filters ─────────────────────────────────────────────────
    st.sidebar.markdown("### Heat Map Filters")

    # Source category
    cats = sorted(all_samples["source_category"].dropna().unique())
    sel_cats = st.sidebar.multiselect("Source Category", ["All"] + cats, default=["All"], key="hm_cat")
    if "All" not in sel_cats and sel_cats:
        all_samples = all_samples[all_samples["source_category"].isin(sel_cats)]

    # Region
    regions = sorted(all_samples["region"].dropna().unique())
    sel_regions = st.sidebar.multiselect("Region", ["All"] + regions, default=["All"], key="hm_reg")
    if "All" not in sel_regions and sel_regions:
        all_samples = all_samples[all_samples["region"].isin(sel_regions)]

    # Lab / sentinel site
    labs = sorted(all_samples["lab_name"].dropna().unique()) if "lab_name" in all_samples.columns else []
    if labs:
        sel_labs = st.sidebar.multiselect("Sentinel Site", ["All"] + labs, default=["All"], key="hm_lab")
        if "All" not in sel_labs and sel_labs:
            all_samples = all_samples[all_samples["lab_name"].isin(sel_labs)]

    # Filter AST to remaining samples
    all_ast = all_ast[all_ast["sample_id"].astype(str).isin(all_samples["sample_id"].astype(str))]

    if all_ast.empty:
        st.warning("No AST data matches the selected filters.")
        return

    # ── min-isolate threshold ───────────────────────────────────────────
    min_tests = st.sidebar.slider("Minimum tests per cell", 1, 50, 10, key="hm_min")

    # Top-N controls
    top_org = st.sidebar.slider("Top organisms", 5, 40, 15, key="hm_top_org")
    top_abx = st.sidebar.slider("Top antibiotics", 5, 40, 20, key="hm_top_abx")

    # Resistance tier filter
    tier = st.sidebar.selectbox(
        "Highlight tier",
        ["All", "Critical (≥70%)", "High (40-69%)", "Moderate (20-39%)", "Low (<20%)"],
        key="hm_tier",
    )

    # ── compute resistance matrix ───────────────────────────────────────
    all_ast = all_ast.dropna(subset=["organism", "antibiotic", "result"])
    all_ast = all_ast[all_ast["result"].isin(["R", "I", "S"])]
    combo = all_ast.groupby(["organism", "antibiotic", "result"]).size().reset_index(name="n")
    pivot = combo.pivot_table(index=["organism", "antibiotic"], columns="result", values="n", fill_value=0)
    pivot = pivot.reset_index()
    for c in ("R", "I", "S"):
        if c not in pivot.columns:
            pivot[c] = 0
    pivot["total"] = pivot["R"] + pivot["I"] + pivot["S"]
    pivot = pivot[pivot["total"] >= min_tests]
    pivot["pct_r"] = (pivot["R"] / pivot["total"] * 100).round(1)

    if pivot.empty:
        st.warning("Not enough data with the selected minimum-test threshold.")
        return

    # Apply tier filter
    if tier.startswith("Critical"):
        pivot = pivot[pivot["pct_r"] >= 70]
    elif tier.startswith("High"):
        pivot = pivot[(pivot["pct_r"] >= 40) & (pivot["pct_r"] < 70)]
    elif tier.startswith("Moderate"):
        pivot = pivot[(pivot["pct_r"] >= 20) & (pivot["pct_r"] < 40)]
    elif tier.startswith("Low"):
        pivot = pivot[pivot["pct_r"] < 20]

    if pivot.empty:
        st.info("No combinations match the selected resistance tier.")
        return

    # Select top organisms & antibiotics by frequency
    org_counts = pivot.groupby("organism")["total"].sum().nlargest(top_org)
    abx_counts = pivot.groupby("antibiotic")["total"].sum().nlargest(top_abx)
    pivot = pivot[pivot["organism"].isin(org_counts.index) & pivot["antibiotic"].isin(abx_counts.index)]

    # Build the matrix
    matrix = pivot.pivot_table(index="organism", columns="antibiotic", values="pct_r")
    count_matrix = pivot.pivot_table(index="organism", columns="antibiotic", values="total")

    # Sort organisms by mean resistance (highest first)
    matrix = matrix.loc[matrix.mean(axis=1).sort_values(ascending=False).index]
    # Sort antibiotics by mean resistance (highest first)
    col_order = matrix.mean(axis=0).sort_values(ascending=False).index
    matrix = matrix[col_order]
    count_matrix = count_matrix.reindex(index=matrix.index, columns=matrix.columns)

    # ── KPI row ─────────────────────────────────────────────────────────
    n_orgs = matrix.shape[0]
    n_abx = matrix.shape[1]
    overall_r = pivot["pct_r"].mean()
    n_critical = int((pivot["pct_r"] >= 70).sum())
    n_combos = int(pivot.shape[0])

    st.markdown(
        '<div class="kpi-row">'
        + _kpi(n_orgs, "Organisms", "blue")
        + _kpi(n_abx, "Antibiotics", "green")
        + _kpi(f"{overall_r:.1f}%", "Mean Resistance", "red" if overall_r >= 40 else "amber")
        + _kpi(n_critical, "Critical Combos (≥70%)", "red")
        + _kpi(f"{n_combos:,}", "Total Combinations", "purple")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── colour legend ───────────────────────────────────────────────────
    st.markdown(
        '<div class="legend-box">'
        '<div class="legend-item"><span class="legend-swatch" style="background:rgb(34,197,94)"></span> &lt;20 % (Low)</div>'
        '<div class="legend-item"><span class="legend-swatch" style="background:rgb(234,179,8)"></span> 20-39 % (Moderate)</div>'
        '<div class="legend-item"><span class="legend-swatch" style="background:rgb(234,88,12)"></span> 40-69 % (High)</div>'
        '<div class="legend-item"><span class="legend-swatch" style="background:rgb(220,38,38)"></span> ≥70 % (Critical)</div>'
        '<div class="legend-item"><span class="legend-swatch" style="background:rgb(209,213,219)"></span> No data</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Plotly heatmap ──────────────────────────────────────────────────
    # Build hover text with counts
    hover = []
    for org in matrix.index:
        row_text = []
        for abx in matrix.columns:
            val = matrix.loc[org, abx]
            cnt = count_matrix.loc[org, abx] if pd.notna(count_matrix.loc[org, abx]) else 0
            if pd.isna(val):
                row_text.append(f"<b>{org}</b> vs <b>{abx}</b><br>No data")
            else:
                row_text.append(
                    f"<b>{org}</b> vs <b>{abx}</b><br>"
                    f"Resistance: {val:.1f}%<br>"
                    f"Tests: {int(cnt)}"
                )
        hover.append(row_text)

    # Annotation text (show % inside cells)
    annotations = []
    z_vals = matrix.values
    for i, org in enumerate(matrix.index):
        for j, abx in enumerate(matrix.columns):
            val = z_vals[i][j]
            if pd.notna(val):
                annotations.append(
                    dict(
                        x=abx, y=org,
                        text=f"{val:.0f}",
                        font=dict(color="white" if val >= 40 else "#1e293b", size=10),
                        showarrow=False,
                        xref="x", yref="y",
                    )
                )

    fig = go.Figure(
        data=go.Heatmap(
            z=z_vals,
            x=list(matrix.columns),
            y=list(matrix.index),
            colorscale=_build_colorscale(),
            zmin=0,
            zmax=100,
            hovertext=hover,
            hoverinfo="text",
            colorbar=dict(
                title="Resistance %",
                tickvals=[0, 20, 40, 70, 100],
                ticktext=["0%", "20%", "40%", "70%", "100%"],
            ),
            xgap=2,
            ygap=2,
        )
    )

    fig.update_layout(
        annotations=annotations,
        height=max(450, 28 * n_orgs + 120),
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title=dict(text="Organism × Antibiotic Resistance Heat Map", font=dict(size=16, color="#0f766e")),
        xaxis=dict(
            side="top",
            tickangle=-45,
            tickfont=dict(size=10, color="#334155"),
            dtick=1,
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=10, color="#334155"),
            dtick=1,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Resistance tier summary table ───────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.subheader("Resistance Tier Summary")

    tier_data = pivot.copy()
    tier_data["tier"] = pd.cut(
        tier_data["pct_r"],
        bins=[-1, 20, 40, 70, 101],
        labels=["Low (<20%)", "Moderate (20-39%)", "High (40-69%)", "Critical (≥70%)"],
    )
    tier_counts = tier_data["tier"].value_counts().reindex(
        ["Critical (≥70%)", "High (40-69%)", "Moderate (20-39%)", "Low (<20%)"]
    ).fillna(0).astype(int)

    cols = st.columns(4)
    tier_colors = ["red", "amber", "green", "blue"]
    for col, (tier_name, cnt), clr in zip(cols, tier_counts.items(), tier_colors):
        with col:
            pct_of_total = cnt / max(1, len(tier_data)) * 100
            st.markdown(
                f'<div class="kpi-card {clr}">'
                f'<div class="value">{cnt}</div>'
                f'<div class="label">{tier_name} ({pct_of_total:.0f}%)</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Top critical combinations table ─────────────────────────────────
    critical = tier_data[tier_data["pct_r"] >= 40].sort_values("pct_r", ascending=False)
    if not critical.empty:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.subheader("High-Risk Pathogen-Antibiotic Combinations")
        display = critical[["organism", "antibiotic", "pct_r", "R", "total"]].copy()
        display.columns = ["Organism", "Antibiotic", "Resistance %", "Resistant", "Total Tests"]
        st.dataframe(display.head(30), use_container_width=True, hide_index=True)

    # ── CSV download ────────────────────────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    csv = pivot[["organism", "antibiotic", "pct_r", "R", "I", "S", "total"]].copy()
    csv.columns = ["Organism", "Antibiotic", "Resistance %", "Resistant", "Intermediate", "Susceptible", "Total"]
    st.download_button(
        "Download Heat Map Data (CSV)",
        csv.to_csv(index=False).encode("utf-8"),
        "resistance_heatmap.csv",
        "text/csv",
        use_container_width=True,
    )
