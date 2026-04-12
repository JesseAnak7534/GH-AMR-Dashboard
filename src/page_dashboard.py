"""
Landing / Home page for ICBB-AMRSS.
Shows national KPI summary, sparkline trends, alert status,
and quick-access cards. Works for both admin and lab users.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from src import db, analytics


# ── Single cached function: load + compute everything once ────────────
@st.cache_data(ttl=120, show_spinner="Loading dashboard…")
def _compute_dashboard_data(lab_filter: str = ""):
    """Return all pre-computed values the dashboard needs.

    *lab_filter*: empty string for admin (all data), or lab_name for lab users.
    Returns a dict (all serialisable, no DataFrames in heavy sections).
    """
    all_samples = db.get_all_samples()
    all_ast = db.get_all_ast_results()

    # Lab filter
    if lab_filter:
        if not all_samples.empty and "lab_name" in all_samples.columns:
            mask = all_samples["lab_name"].astype(str).str.strip().str.lower() == lab_filter.strip().lower()
            all_samples = all_samples[mask]
            if not all_ast.empty:
                all_ast = all_ast[all_ast["sample_id"].astype(str).isin(all_samples["sample_id"].astype(str))]

    if all_ast.empty or all_samples.empty:
        return None  # sentinel: no data

    ast_clean = all_ast.dropna(subset=["organism", "antibiotic", "result"])
    ast_clean = ast_clean[ast_clean["result"].isin(["R", "I", "S"])]
    if ast_clean.empty:
        return None

    # ── KPIs ───────────────────────────────────────────────────
    total_samples = len(all_samples)
    total_tests = len(ast_clean)
    total_isolates = int(ast_clean["isolate_id"].nunique()) if "isolate_id" in ast_clean.columns else 0
    total_organisms = int(ast_clean["organism"].nunique())
    total_antibiotics = int(ast_clean["antibiotic"].nunique())
    r_count = int((ast_clean["result"] == "R").sum())
    overall_r_rate = round(r_count / max(total_tests, 1) * 100, 1)
    regions_covered = int(all_samples["region"].nunique()) if "region" in all_samples.columns else 0
    labs_reporting = int(all_samples["lab_name"].nunique()) if "lab_name" in all_samples.columns else 0
    source_cats = int(all_samples["source_category"].nunique()) if "source_category" in all_samples.columns else 0

    # MDR (iterates isolates — heavy, but now cached)
    mdro = analytics.calculate_mdro_incidence(ast_clean)
    mdr_rate = mdro.get("mdr_rate_pct", 0)

    # Alerts
    try:
        conn = db.get_connection()
        alert_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE is_acknowledged = 0"
        ).fetchone()[0]
    except Exception:
        alert_count = 0

    # ── Monthly trend (vectorised, no lambda) ──────────────────
    monthly_data = []
    if "test_date" in ast_clean.columns:
        _ast_t = ast_clean[["test_date", "result"]].copy()
        _ast_t["test_date"] = pd.to_datetime(_ast_t["test_date"], errors="coerce")
        _ast_t = _ast_t.dropna(subset=["test_date"])
        if not _ast_t.empty:
            _ast_t["month"] = _ast_t["test_date"].dt.to_period("M")
            grp = _ast_t.groupby("month")["result"]
            monthly = pd.DataFrame({
                "total": grp.count(),
                "resistant": grp.apply(lambda x: (x == "R").sum()),
            })
            monthly["r_pct"] = (monthly["resistant"] / monthly["total"].clip(lower=1) * 100).round(1)
            monthly = monthly.sort_index()
            monthly_data = [
                {"month": str(idx), "r_pct": float(row["r_pct"])}
                for idx, row in monthly.iterrows()
            ]

    # ── Source category breakdown ──────────────────────────────
    source_data = []
    if "source_category" in all_samples.columns:
        src_counts = all_samples["source_category"].value_counts()
        source_data = [{"cat": str(c), "n": int(v)} for c, v in src_counts.items()]

    # ── Top resistant organisms (vectorised) ───────────────────
    grp_org = ast_clean.groupby("organism")["result"]
    org_stats = pd.DataFrame({
        "total": grp_org.count(),
        "resistant": grp_org.apply(lambda x: (x == "R").sum()),
    })
    org_stats["r_pct"] = (org_stats["resistant"] / org_stats["total"].clip(lower=1) * 100).round(1)
    top_orgs = [
        {"org": str(idx), "pct": float(row["r_pct"])}
        for idx, row in org_stats.nlargest(6, "r_pct").iterrows()
    ]

    # ── Region breakdown ───────────────────────────────────────
    region_data = []
    if "region" in all_samples.columns:
        reg = all_samples["region"].value_counts().head(8)
        region_data = [{"region": str(r), "n": int(v)} for r, v in reg.items()]

    # ── Sentinel phenotypes (iterates isolates — heavy, cached) ─
    raw_pheno = analytics.detect_sentinel_phenotypes(ast_clean)
    pheno_data = [
        {
            "label": p.get("label", ""),
            "code": p.get("code", ""),
            "who_tier": p.get("who_tier", ""),
            "isolate_count": int(p.get("isolate_count", 0)),
            "resistance_rate": float(p.get("resistance_rate", 0)),
        }
        for p in (raw_pheno or [])[:6]
    ]

    # ── Admin stats ────────────────────────────────────────────
    try:
        conn = db.get_connection()
        total_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
        total_datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        last_upload = conn.execute("SELECT uploaded_at FROM datasets ORDER BY uploaded_at DESC LIMIT 1").fetchone()
        last_upload_str = last_upload[0][:10] if last_upload and last_upload[0] else "—"
    except Exception:
        total_users = total_datasets = 0
        last_upload_str = "—"

    return {
        "total_samples": total_samples, "total_tests": total_tests,
        "total_isolates": total_isolates, "total_organisms": total_organisms,
        "total_antibiotics": total_antibiotics, "overall_r_rate": overall_r_rate,
        "regions_covered": regions_covered, "labs_reporting": labs_reporting,
        "source_cats": source_cats, "mdr_rate": mdr_rate,
        "alert_count": alert_count,
        "monthly_data": monthly_data, "source_data": source_data,
        "top_orgs": top_orgs, "region_data": region_data,
        "pheno_data": pheno_data,
        "total_users": total_users, "total_datasets": total_datasets,
        "last_upload_str": last_upload_str,
    }


# ── Tiny sparkline helper ─────────────────────────────────────────────
def _sparkline(values: list, color: str = "#38bdf8", height: int = 40) -> go.Figure:
    """Return a minimal sparkline figure."""
    fig = go.Figure(go.Scatter(
        y=values, mode="lines",
        line=dict(color=color, width=2, shape="spline"),
        fill="tozeroy",
        fillcolor=color.replace(")", ",0.10)").replace("rgb", "rgba") if "rgb" in color else f"rgba(56,189,248,0.10)",
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=height, width=120,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── KPI card (HTML) ──────────────────────────────────────────────────
_CARD_HTML = """
<div style="
    background: linear-gradient(135deg, {bg1} 0%, {bg2} 100%);
    border-radius: 14px;
    padding: 1.25rem 1.4rem;
    border: 1px solid {border};
    min-height: 110px;
    display: flex; flex-direction: column; justify-content: space-between;
">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:0.78em; font-weight:600; color:{label_color}; letter-spacing:0.04em; text-transform:uppercase;">{label}</span>
        <span style="font-size:1.3em;">{icon}</span>
    </div>
    <div style="font-size:1.9em; font-weight:700; color:{value_color}; margin:0.15rem 0;">{value}</div>
    <div style="font-size:0.78em; color:{sub_color};">{sub}</div>
</div>
"""


def _kpi_card(label, value, sub, icon, palette):
    st.markdown(
        _CARD_HTML.format(label=label, value=value, sub=sub, icon=icon, **palette),
        unsafe_allow_html=True,
    )


# Palette presets
_P_TEAL   = dict(bg1="#f0fdfa", bg2="#ccfbf1", border="#99f6e4", label_color="#0f766e", value_color="#0d9488", sub_color="#5eead4")
_P_BLUE   = dict(bg1="#eff6ff", bg2="#dbeafe", border="#93c5fd", label_color="#1e40af", value_color="#2563eb", sub_color="#60a5fa")
_P_AMBER  = dict(bg1="#fffbeb", bg2="#fef3c7", border="#fcd34d", label_color="#92400e", value_color="#d97706", sub_color="#fbbf24")
_P_RED    = dict(bg1="#fef2f2", bg2="#fee2e2", border="#fca5a5", label_color="#991b1b", value_color="#dc2626", sub_color="#f87171")
_P_PURPLE = dict(bg1="#faf5ff", bg2="#f3e8ff", border="#c4b5fd", label_color="#5b21b6", value_color="#7c3aed", sub_color="#a78bfa")
_P_GREEN  = dict(bg1="#f0fdf4", bg2="#dcfce7", border="#86efac", label_color="#166534", value_color="#16a34a", sub_color="#4ade80")


# ── Main render function ─────────────────────────────────────────────
def render_dashboard_page():
    is_admin = st.session_state.get("is_admin", False)
    lab_name = st.session_state.get("lab_name")
    user_email = st.session_state.get("user_email", "")

    # ── Header ────────────────────────────────────────────────────
    greeting = "Administrator" if is_admin else (lab_name or user_email.split("@")[0])
    st.markdown(f"""
        <div style="margin-bottom:1.5rem;">
            <h2 style="margin:0; color:#0f766e; font-weight:700;">Welcome back, {greeting}</h2>
            <p style="margin:0.3rem 0 0 0; color:#64748b; font-size:0.95em;">
                {'National surveillance overview — all sentinel sites' if is_admin else f'Surveillance summary for <strong>{lab_name or "your lab"}</strong>'}
            </p>
        </div>
    """, unsafe_allow_html=True)

    # ── Load ALL pre-computed data (single cache call) ────────────
    lab_filter = "" if is_admin else (lab_name or "")
    data = _compute_dashboard_data(lab_filter)

    if data is None:
        st.info("No surveillance data available yet. Upload data via **Upload & Data Quality** to get started.")
        return

    # Unpack
    total_samples = data["total_samples"]
    total_tests = data["total_tests"]
    total_isolates = data["total_isolates"]
    total_organisms = data["total_organisms"]
    total_antibiotics = data["total_antibiotics"]
    overall_r_rate = data["overall_r_rate"]
    regions_covered = data["regions_covered"]
    labs_reporting = data["labs_reporting"]
    source_cats = data["source_cats"]
    mdr_rate = data["mdr_rate"]
    alert_count = data["alert_count"]

    # ── KPI Row 1 — Core numbers ──────────────────────────────────
    st.markdown("#### At a Glance")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        _kpi_card("Samples", f"{total_samples:,}", f"{labs_reporting} labs reporting", "🧫", _P_TEAL)
    with c2:
        _kpi_card("AST Tests", f"{total_tests:,}", f"{total_antibiotics} antibiotics", "🔬", _P_BLUE)
    with c3:
        _kpi_card("Organisms", f"{total_organisms}", f"{total_isolates:,} isolates", "🦠", _P_PURPLE)
    with c4:
        _kpi_card("Resistance Rate", f"{overall_r_rate}%", "overall R / total tests", "📊", _P_RED if overall_r_rate >= 40 else _P_AMBER if overall_r_rate >= 20 else _P_GREEN)
    with c5:
        _kpi_card("MDR Rate", f"{mdr_rate}%", "≥3 classes resistant", "⚠️", _P_RED if mdr_rate >= 30 else _P_AMBER)
    with c6:
        _kpi_card("Active Alerts", f"{alert_count}", "unacknowledged", "🔔", _P_RED if alert_count >= 5 else _P_AMBER if alert_count > 0 else _P_GREEN)

    st.markdown("")

    # ── Row 2: Resistance trend sparkline + Source breakdown + Top pathogens
    col_trend, col_source, col_top = st.columns([1.2, 1, 1])

    with col_trend:
        st.markdown("""
            <div style="background:white; border-radius:14px; padding:1.2rem 1.4rem; border:1px solid #e2e8f0; min-height:280px;">
                <div style="font-size:0.82em; font-weight:600; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.8rem;">
                    Resistance Trend (Monthly)
                </div>
        """, unsafe_allow_html=True)
        monthly_data = data["monthly_data"]
        if monthly_data:
            months = [m["month"] for m in monthly_data]
            r_pcts = [m["r_pct"] for m in monthly_data]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=months, y=r_pcts,
                mode="lines+markers",
                line=dict(color="#0d9488", width=2.5, shape="spline"),
                marker=dict(size=5, color="#0d9488"),
                fill="tozeroy",
                fillcolor="rgba(13,148,136,0.08)",
                hovertemplate="%{x}<br>Resistance: %{y:.1f}%<extra></extra>",
            ))
            fig.update_layout(
                margin=dict(l=0, r=0, t=5, b=0),
                height=200,
                xaxis=dict(showgrid=False, tickfont=dict(size=10, color="#94a3b8"), dtick=3),
                yaxis=dict(showgrid=True, gridcolor="#f1f5f9", ticksuffix="%", tickfont=dict(size=10, color="#94a3b8")),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No dated test records available for trend")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_source:
        st.markdown("""
            <div style="background:white; border-radius:14px; padding:1.2rem 1.4rem; border:1px solid #e2e8f0; min-height:280px;">
                <div style="font-size:0.82em; font-weight:600; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.8rem;">
                    One Health Sources
                </div>
        """, unsafe_allow_html=True)
        source_data = data["source_data"]
        if source_data:
            src_labels = [s["cat"] for s in source_data]
            src_values = [s["n"] for s in source_data]
            colors = {"HUMAN": "#3b82f6", "ANIMAL": "#f59e0b", "FOOD": "#22c55e", "ENVIRONMENT": "#8b5cf6", "AQUACULTURE": "#06b6d4"}
            fig2 = go.Figure(go.Pie(
                labels=src_labels,
                values=src_values,
                hole=0.55,
                marker=dict(colors=[colors.get(str(c).upper(), "#94a3b8") for c in src_labels]),
                textinfo="label+percent",
                textfont=dict(size=11),
                hovertemplate="%{label}: %{value:,} samples (%{percent})<extra></extra>",
            ))
            fig2.update_layout(
                margin=dict(l=0, r=0, t=5, b=0),
                height=210,
                showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No source category data")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_top:
        st.markdown("""
            <div style="background:white; border-radius:14px; padding:1.2rem 1.4rem; border:1px solid #e2e8f0; min-height:280px;">
                <div style="font-size:0.82em; font-weight:600; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.8rem;">
                    Top Resistant Pathogens
                </div>
        """, unsafe_allow_html=True)
        top_orgs = data["top_orgs"]
        if top_orgs:
            for item in top_orgs:
                org, pct = item["org"], item["pct"]
                bar_color = "#dc2626" if pct >= 60 else "#f59e0b" if pct >= 30 else "#22c55e"
                st.markdown(f"""
                    <div style="margin-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.82em; color:#334155;">
                            <span style="max-width:70%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{org}</span>
                            <span style="font-weight:600; color:{bar_color};">{pct}%</span>
                        </div>
                        <div style="background:#f1f5f9; border-radius:4px; height:6px; margin-top:3px;">
                            <div style="background:{bar_color}; width:{min(pct, 100)}%; height:100%; border-radius:4px;"></div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    # ── Row 3: Regional coverage + Sentinel phenotypes + Quick links
    col_reg, col_pheno, col_links = st.columns([1, 1, 0.8])

    with col_reg:
        st.markdown("""
            <div style="background:white; border-radius:14px; padding:1.2rem 1.4rem; border:1px solid #e2e8f0; min-height:240px;">
                <div style="font-size:0.82em; font-weight:600; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.8rem;">
                    Geographic Coverage
                </div>
        """, unsafe_allow_html=True)
        region_data = data["region_data"]
        if region_data:
            reg_labels = [r["region"] for r in region_data]
            reg_values = [r["n"] for r in region_data]
            fig3 = go.Figure(go.Bar(
                y=reg_labels[::-1],
                x=reg_values[::-1],
                orientation="h",
                marker_color="#0d9488",
                hovertemplate="%{y}: %{x:,} samples<extra></extra>",
            ))
            fig3.update_layout(
                margin=dict(l=0, r=0, t=5, b=0),
                height=190,
                xaxis=dict(showgrid=True, gridcolor="#f1f5f9", tickfont=dict(size=10, color="#94a3b8")),
                yaxis=dict(tickfont=dict(size=10, color="#334155")),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
            st.markdown(f"<div style='font-size:0.78em; color:#64748b;'>{regions_covered} regions · {source_cats} One Health sources</div>", unsafe_allow_html=True)
        else:
            st.caption("No region data")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_pheno:
        st.markdown("""
            <div style="background:white; border-radius:14px; padding:1.2rem 1.4rem; border:1px solid #e2e8f0; min-height:240px;">
                <div style="font-size:0.82em; font-weight:600; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.8rem;">
                    Sentinel Phenotypes Detected
                </div>
        """, unsafe_allow_html=True)
        pheno_data = data["pheno_data"]
        if pheno_data:
            for ph in pheno_data:
                who_tier = ph.get("who_tier", "")
                badge_bg = "#fef2f2" if who_tier == "CRITICAL" else "#fffbeb" if who_tier == "HIGH" else "#eff6ff"
                badge_color = "#dc2626" if who_tier == "CRITICAL" else "#d97706" if who_tier == "HIGH" else "#2563eb"
                count_display = ph.get("isolate_count", 0)
                r_rate = ph.get("resistance_rate", 0)
                st.markdown(f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid #f1f5f9;">
                        <div>
                            <div style="font-size:0.85em; font-weight:500; color:#1e293b;">{ph.get('label', '')}</div>
                            <div style="font-size:0.72em; color:#64748b;">{ph.get('code', '')} · {r_rate}% resistance</div>
                        </div>
                        <div style="background:{badge_bg}; color:{badge_color}; padding:2px 8px; border-radius:10px; font-size:0.75em; font-weight:600;">
                            {count_display} isolates
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#64748b; font-size:0.85em; padding:1rem 0;'>No sentinel phenotypes detected in current data</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_links:
        st.markdown("""
            <div style="background:white; border-radius:14px; padding:1.2rem 1.4rem; border:1px solid #e2e8f0; min-height:240px;">
                <div style="font-size:0.82em; font-weight:600; color:#475569; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.8rem;">
                    Quick Actions
                </div>
        """, unsafe_allow_html=True)

        actions = [
            ("📤", "Upload Data", "Upload & Data Quality"),
            ("📊", "Resistance Overview", "Resistance Overview"),
            ("🗺️", "Map Hotspots", "Map Hotspots"),
            ("🧬", "Antibiogram", "Antibiogram"),
            ("📄", "Export Report", "Report Export"),
        ]
        if is_admin:
            actions.append(("👥", "Manage Users", "Admin - Users"))

        for icon, label, target_page in actions:
            if st.button(f"{icon}  {label}", key=f"dash_quick_{target_page}", use_container_width=True):
                st.session_state.active_page = target_page
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Admin-only: System health row ─────────────────────────────
    if is_admin:
        st.markdown("")
        st.markdown("#### System Health")
        a1, a2, a3, a4 = st.columns(4)

        total_users, total_datasets, last_upload_str = data["total_users"], data["total_datasets"], data["last_upload_str"]

        with a1:
            _kpi_card("Active Users", f"{total_users}", "registered accounts", "👥", _P_BLUE)
        with a2:
            _kpi_card("Datasets", f"{total_datasets}", f"last upload: {last_upload_str}", "📂", _P_TEAL)
        with a3:
            _kpi_card("Regions", f"{regions_covered}", f"{labs_reporting} sentinel sites", "🗺️", _P_PURPLE)
        with a4:
            _kpi_card("Sources", f"{source_cats}", "One Health categories", "🌍", _P_GREEN)
