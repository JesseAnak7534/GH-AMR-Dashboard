"""
AMU (Antimicrobial Use) Dashboard page module.
Classic, polished UI with styled KPI cards and clean chart layouts.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src import db

# ── Shared styling ──────────────────────────────────────────────────────
CARD_CSS = """
<style>
.kpi-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.kpi-card {
    flex: 1; min-width: 160px; padding: 1.2rem 1rem; border-radius: 12px;
    text-align: center; border: 1px solid rgba(255,255,255,0.08);
}
.kpi-card.blue   { background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); }
.kpi-card.green  { background: linear-gradient(135deg, #1a4d2e 0%, #0d2818 100%); }
.kpi-card.amber  { background: linear-gradient(135deg, #5c4a1e 0%, #3d3010 100%); }
.kpi-card.purple { background: linear-gradient(135deg, #3b1e5c 0%, #25103d 100%); }
.kpi-card .value { font-size: 2rem; font-weight: 700; color: #fff; }
.kpi-card .label { font-size: 0.82rem; color: rgba(255,255,255,0.65); margin-top: 0.25rem; }
.section-divider { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 2rem 0 1.5rem; }
</style>
"""

def _kpi(value, label, color="blue"):
    return f'<div class="kpi-card {color}"><div class="value">{value}</div><div class="label">{label}</div></div>'

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1e293b", size=13), margin=dict(l=40, r=20, t=50, b=40),
    title_font_size=17,
)


def render_amu_page():
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    st.header("Antimicrobial Use (AMU)")
    st.caption("Track antimicrobial consumption at facility level — Defined Daily Doses (DDD)")

    amu_df = db.get_amu_records()
    if amu_df.empty:
        st.info("No AMU data yet. Upload data via **Upload & Data Quality** using the unified template (fill the `amu_data` sheet).")
        return

    # ── KPIs ────────────────────────────────────────────────────────────
    total_records = len(amu_df)
    facilities = amu_df['facility_name'].nunique()
    periods = amu_df['report_period'].nunique()
    total_dispensed = int(amu_df['quantity_dispensed'].sum())

    st.markdown(
        '<div class="kpi-row">'
        + _kpi(f"{total_records:,}", "Total Records", "blue")
        + _kpi(facilities, "Facilities Reporting", "green")
        + _kpi(periods, "Reporting Periods", "purple")
        + _kpi(f"{total_dispensed:,}", "Total Units Dispensed", "amber")
        + '</div>', unsafe_allow_html=True
    )

    # ── Top antibiotics ─────────────────────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.subheader("Top Antibiotics by Quantity Dispensed")
    top_abx = amu_df.groupby('antibiotic_name')['quantity_dispensed'].sum().sort_values().tail(15)
    fig1 = px.bar(
        y=top_abx.index, x=top_abx.values, orientation='h',
        labels={'x': 'Quantity Dispensed', 'y': ''},
        color_discrete_sequence=['#3b82f6'],
        text=top_abx.values,
    )
    fig1.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig1.update_layout(**CHART_LAYOUT, showlegend=False)
    st.plotly_chart(fig1, use_container_width=True)

    # ── Regional comparison ─────────────────────────────────────────────
    if 'region' in amu_df.columns and amu_df['region'].notna().any():
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.subheader("Regional AMU Comparison")
        region_data = amu_df.groupby('region')['quantity_dispensed'].sum().sort_values(ascending=False).reset_index()
        fig2 = px.bar(
            region_data, x='region', y='quantity_dispensed',
            labels={'quantity_dispensed': 'Quantity Dispensed', 'region': ''},
            color='quantity_dispensed', color_continuous_scale='Blues',
            text='quantity_dispensed',
        )
        fig2.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig2.update_layout(**CHART_LAYOUT, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    # ── DDD trend ───────────────────────────────────────────────────────
    if 'ddd_per_1000' in amu_df.columns and amu_df['ddd_per_1000'].notna().any():
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.subheader("DDD per 1,000 Patient-Days Over Time")
        ddd_trend = amu_df.groupby('report_period')['ddd_per_1000'].mean().reset_index()
        fig3 = px.line(
            ddd_trend, x='report_period', y='ddd_per_1000',
            labels={'ddd_per_1000': 'DDD/1,000 PD', 'report_period': ''},
            markers=True, color_discrete_sequence=['#10b981'],
        )
        fig3.update_traces(line_width=3, marker_size=10)
        fig3.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig3, use_container_width=True)

    # ── Facility comparison ─────────────────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.subheader("Facility-Level Comparison")
    fac = amu_df.groupby('facility_name')['quantity_dispensed'].sum().sort_values().reset_index()
    fig4 = px.bar(
        fac, y='facility_name', x='quantity_dispensed', orientation='h',
        labels={'quantity_dispensed': 'Quantity', 'facility_name': ''},
        color_discrete_sequence=['#8b5cf6'],
        text='quantity_dispensed',
    )
    fig4.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig4.update_layout(**CHART_LAYOUT, showlegend=False)
    st.plotly_chart(fig4, use_container_width=True)

    # ── Raw data ────────────────────────────────────────────────────────
    with st.expander("View Raw AMU Data"):
        st.dataframe(amu_df, use_container_width=True, hide_index=True)
