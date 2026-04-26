"""
PPS (Point Prevalence Survey) Dashboard page module.
Classic, polished UI with styled KPI cards and clean chart layouts.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src import db

# ── Shared styling helpers ──────────────────────────────────────────────
CARD_CSS = """
<style>
.kpi-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.kpi-card {
    flex: 1; min-width: 160px; padding: 1.2rem 1rem; border-radius: 12px;
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
.gauge-container {
    background: linear-gradient(135deg, #1a1f2e 0%, #0f1318 100%);
    border-radius: 14px; padding: 1rem 0.5rem; margin-bottom: 0.5rem;
    border: 1px solid rgba(255,255,255,0.06);
}
</style>
"""

def _kpi(value, label, color="blue"):
    return f'<div class="kpi-card {color}"><div class="value">{value}</div><div class="label">{label}</div></div>'

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1e293b", size=13), margin=dict(l=40, r=20, t=50, b=40),
    title_font_size=17,
)


def render_pps_page():
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    st.header("Point Prevalence Survey (PPS)")
    st.caption("Monitor antibiotic prescribing practices across healthcare facilities")

    surveys = db.get_pps_surveys()
    if surveys.empty:
        st.info("No PPS data yet. Upload data via **Upload & Data Quality** using the unified template (fill the `pps_survey` and `prescriptions` sheets).")
        return

    # ── KPIs ────────────────────────────────────────────────────────────
    total_surveys = len(surveys)
    total_patients = int(surveys['total_patients'].sum())
    total_on_abx = int(surveys['patients_on_antibiotics'].sum())
    rate = (total_on_abx / total_patients * 100) if total_patients > 0 else 0

    st.markdown(
        '<div class="kpi-row">'
        + _kpi(total_surveys, "Surveys Completed", "blue")
        + _kpi(f"{total_patients:,}", "Total Patients Surveyed", "green")
        + _kpi(f"{total_on_abx:,}", "Patients on Antibiotics", "amber")
        + _kpi(f"{rate:.1f}%", "Prescribing Rate", "red" if rate > 50 else "amber")
        + '</div>', unsafe_allow_html=True
    )

    # ── Survey table ────────────────────────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    with st.expander("Survey Records", expanded=False):
        st.dataframe(surveys, use_container_width=True, hide_index=True)

    # ── Prescribing rate by facility ────────────────────────────────────
    if len(surveys) > 1:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.subheader("Prescribing Rate by Facility")
        surveys = surveys.copy()
        surveys['prescribing_rate'] = (surveys['patients_on_antibiotics'] / surveys['total_patients'] * 100).round(1)
        fig = px.bar(
            surveys.sort_values('prescribing_rate', ascending=True),
            y='facility_name', x='prescribing_rate', orientation='h',
            labels={'prescribing_rate': 'Rate (%)', 'facility_name': ''},
            color='prescribing_rate', color_continuous_scale='RdYlGn_r',
            text='prescribing_rate',
        )
        fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig.update_layout(**CHART_LAYOUT, showlegend=False, coloraxis_showscale=False,
                          yaxis=dict(tickfont=dict(color="#1e293b")),
                          xaxis=dict(tickfont=dict(color="#1e293b")))
        st.plotly_chart(fig, use_container_width=True)

    # ── Prescription detail analysis ────────────────────────────────────
    all_rx = db.get_pps_prescriptions()
    if all_rx.empty:
        return

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.subheader("Prescription Analysis")

    col_a, col_b = st.columns(2)
    with col_a:
        top_abx = all_rx['antibiotic_name'].value_counts().head(10).sort_values()
        fig2 = px.bar(
            y=top_abx.index, x=top_abx.values, orientation='h',
            labels={'x': 'Prescriptions', 'y': ''},
            color_discrete_sequence=['#3b82f6'],
        )
        fig2.update_layout(**CHART_LAYOUT, title="Top 10 Prescribed Antibiotics")
        st.plotly_chart(fig2, use_container_width=True)

    with col_b:
        route_dist = all_rx['route'].value_counts()
        fig3 = px.pie(
            values=route_dist.values, names=route_dist.index,
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.45,
        )
        fig3.update_layout(**CHART_LAYOUT, title="Route of Administration")
        st.plotly_chart(fig3, use_container_width=True)

    # ── Quality gauges ──────────────────────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.subheader("Prescribing Quality Indicators")

    total_rx = len(all_rx)
    col_c, col_d = st.columns(2)

    if 'guideline_compliant' in all_rx.columns:
        compliance = (all_rx['guideline_compliant'].sum() / total_rx * 100) if total_rx else 0
        with col_c:
            fig4 = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=compliance,
                number={'suffix': '%', 'font': {'size': 36, 'color': '#0f172a'}},
                title={'text': "Guideline Compliance", 'font': {'size': 14, 'color': '#475569'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickcolor': '#475569', 'tickfont': {'color': '#475569'}},
                    'bar': {'color': '#10b981'},
                    'bgcolor': '#f1f5f9',
                    'steps': [
                        {'range': [0, 50], 'color': 'rgba(239,68,68,0.25)'},
                        {'range': [50, 80], 'color': 'rgba(234,179,8,0.25)'},
                        {'range': [80, 100], 'color': 'rgba(16,185,129,0.25)'},
                    ],
                    'threshold': {'line': {'color': '#f59e0b', 'width': 2}, 'thickness': 0.8, 'value': 80},
                },
            ))
            fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#1e293b"), height=280, margin=dict(t=60, b=20))
            st.markdown('<div class="gauge-container">', unsafe_allow_html=True)
            st.plotly_chart(fig4, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    if 'indication_documented' in all_rx.columns:
        doc_rate = (all_rx['indication_documented'].sum() / total_rx * 100) if total_rx else 0
        with col_d:
            fig5 = go.Figure(go.Indicator(
                mode="gauge+number",
                value=doc_rate,
                number={'suffix': '%', 'font': {'size': 36, 'color': '#0f172a'}},
                title={'text': "Indication Documentation", 'font': {'size': 14, 'color': '#475569'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickcolor': '#475569', 'tickfont': {'color': '#475569'}},
                    'bar': {'color': '#3b82f6'},
                    'bgcolor': '#f1f5f9',
                    'steps': [
                        {'range': [0, 50], 'color': 'rgba(239,68,68,0.25)'},
                        {'range': [50, 80], 'color': 'rgba(234,179,8,0.25)'},
                        {'range': [80, 100], 'color': 'rgba(59,130,246,0.25)'},
                    ],
                    'threshold': {'line': {'color': '#f59e0b', 'width': 2}, 'thickness': 0.8, 'value': 80},
                },
            ))
            fig5.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#1e293b"), height=280, margin=dict(t=60, b=20))
            st.markdown('<div class="gauge-container">', unsafe_allow_html=True)
            st.plotly_chart(fig5, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Ward breakdown ──────────────────────────────────────────────────
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.subheader("Ward-Level Breakdown")
    ward_stats = all_rx.groupby('ward').agg(
        prescriptions=('antibiotic_name', 'count'),
        avg_duration=('duration_days', 'mean'),
    ).reset_index()
    ward_stats['avg_duration'] = ward_stats['avg_duration'].round(1)

    fig6 = px.bar(
        ward_stats.sort_values('prescriptions', ascending=True),
        y='ward', x='prescriptions', orientation='h',
        text='prescriptions',
        color_discrete_sequence=['#8b5cf6'],
        labels={'prescriptions': 'Total Prescriptions', 'ward': ''},
    )
    fig6.update_traces(textposition='outside')
    fig6.update_layout(**CHART_LAYOUT, title="Prescriptions by Ward", showlegend=False)
    st.plotly_chart(fig6, use_container_width=True)

    with st.expander("Ward Statistics Table"):
        st.dataframe(ward_stats.rename(columns={'avg_duration': 'Avg Duration (days)'}), use_container_width=True, hide_index=True)
