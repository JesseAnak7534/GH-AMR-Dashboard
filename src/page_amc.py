"""
AMC (Antimicrobial Consumption) Dashboard – Animal Health & Aquaculture.
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
    font=dict(color="#e5e7eb"), margin=dict(l=40, r=20, t=50, b=40),
    title_font_size=16,
)


def render_amc_page():
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    st.header("Antimicrobial Consumption – Animal Health (AMC)")
    st.caption("Monitor antimicrobial consumption in animal health & aquaculture sectors (mg/kg biomass)")

    amc_df = db.get_amc_records()
    if amc_df.empty:
        st.info("No AMC data yet. Upload data via **Upload & Data Quality** using the unified template (fill the `amc_data` sheet).")
        return

    # ── KPIs ────────────────────────────────────────────────────────────
    total_records = len(amc_df)
    unique_species = amc_df['species'].nunique() if 'species' in amc_df.columns else 0
    total_kg = amc_df['quantity_kg'].sum()
    periods = amc_df['report_period'].nunique() if 'report_period' in amc_df.columns else 0

    st.markdown(
        '<div class="kpi-row">'
        + _kpi(f"{total_records:,}", "Total Records", "blue")
        + _kpi(unique_species, "Species Reported", "green")
        + _kpi(f"{total_kg:,.1f} kg", "Total Consumption", "amber")
        + _kpi(periods, "Reporting Periods", "purple")
        + '</div>', unsafe_allow_html=True
    )

    # ── Sector breakdown (donut) + Antibiotic class bar ─────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Consumption by Sector")
        sector_data = amc_df.groupby('sector')['quantity_kg'].sum().reset_index()
        fig1 = px.pie(
            sector_data, values='quantity_kg', names='sector',
            hole=0.45, color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig1.update_traces(textinfo='percent+label', textposition='outside')
        fig1.update_layout(**CHART_LAYOUT, showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)

    with col_b:
        st.subheader("By Antibiotic Class")
        class_data = amc_df.groupby('antibiotic_class')['quantity_kg'].sum().sort_values().tail(12)
        fig2 = px.bar(
            y=class_data.index, x=class_data.values, orientation='h',
            labels={'x': 'Consumption (kg)', 'y': ''},
            color_discrete_sequence=['#f59e0b'],
            text=class_data.values,
        )
        fig2.update_traces(texttemplate='%{text:,.1f}', textposition='outside')
        fig2.update_layout(**CHART_LAYOUT, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # ── mg/kg biomass intensity ─────────────────────────────────────────
    if 'mg_per_kg_biomass' in amc_df.columns and amc_df['mg_per_kg_biomass'].notna().any():
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.subheader("Consumption Intensity (mg/kg biomass)")
        if 'species' in amc_df.columns:
            intensity = amc_df.groupby('species')['mg_per_kg_biomass'].mean().sort_values().reset_index()
            fig3 = px.bar(
                intensity, y='species', x='mg_per_kg_biomass', orientation='h',
                labels={'mg_per_kg_biomass': 'mg/kg biomass', 'species': ''},
                color='mg_per_kg_biomass', color_continuous_scale='OrRd',
                text='mg_per_kg_biomass',
            )
            fig3.update_traces(texttemplate='%{text:,.1f}', textposition='outside')
            fig3.update_layout(**CHART_LAYOUT, showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig3, use_container_width=True)

    # ── Purpose breakdown (donut) + Regional bar ────────────────────────
    has_purpose = 'purpose' in amc_df.columns and amc_df['purpose'].notna().any()
    has_region = 'region' in amc_df.columns and amc_df['region'].notna().any()

    if has_purpose or has_region:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        cols = st.columns(2 if (has_purpose and has_region) else 1)

        if has_purpose:
            with cols[0]:
                st.subheader("Purpose of Use")
                purpose_data = amc_df.groupby('purpose')['quantity_kg'].sum().reset_index()
                fig4 = px.pie(
                    purpose_data, values='quantity_kg', names='purpose',
                    hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                fig4.update_traces(textinfo='percent+label', textposition='outside')
                fig4.update_layout(**CHART_LAYOUT, showlegend=False)
                st.plotly_chart(fig4, use_container_width=True)

        if has_region:
            target_col = cols[1] if has_purpose else cols[0]
            with target_col:
                st.subheader("Regional Comparison")
                region_data = amc_df.groupby('region')['quantity_kg'].sum().sort_values(ascending=False).reset_index()
                fig5 = px.bar(
                    region_data, x='region', y='quantity_kg',
                    labels={'quantity_kg': 'Consumption (kg)', 'region': ''},
                    color='quantity_kg', color_continuous_scale='Purples',
                    text='quantity_kg',
                )
                fig5.update_traces(texttemplate='%{text:,.1f}', textposition='outside')
                fig5.update_layout(**CHART_LAYOUT, showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig5, use_container_width=True)

    # ── Time trend ──────────────────────────────────────────────────────
    if 'report_period' in amc_df.columns and amc_df['report_period'].notna().any():
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.subheader("Consumption Trend Over Time")
        trend = amc_df.groupby('report_period')['quantity_kg'].sum().reset_index()
        fig6 = px.line(
            trend, x='report_period', y='quantity_kg',
            labels={'quantity_kg': 'Consumption (kg)', 'report_period': ''},
            markers=True, color_discrete_sequence=['#a78bfa'],
        )
        fig6.update_traces(line_width=3, marker_size=10)
        fig6.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig6, use_container_width=True)

    # ── Raw data ────────────────────────────────────────────────────────
    with st.expander("View Raw AMC Data"):
        st.dataframe(amc_df, use_container_width=True, hide_index=True)
