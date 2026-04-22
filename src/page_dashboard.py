"""
Home page for ICBB-AMRSS.
Clean overview: KPI metrics, resistance trend, top pathogens, sentinel alerts.
"""
import logging
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from src import db, analytics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour system — warm editorial palette, matches the app shell tokens
# ---------------------------------------------------------------------------
CLR_PRIMARY = "#194238"      # forest    – headings, chart lines
CLR_PRIMARY_SOFT = "rgba(25, 66, 56, 0.12)"
CLR_DANGER = "#741a10"       # oxide     – high resistance
CLR_WARN = "#a27117"          # ochre     – moderate
CLR_OK = "#2f5430"            # moss      – low / good
CLR_TEXT = "#12100a"          # warm ink  – primary text
CLR_TEXT_SEC = "#55503e"      # warm muted – secondary text
CLR_BORDER = "#c9bc98"        # warm 200  – borders
CLR_BG_SUBTLE = "#ddd1b4"     # paper-alt – subtle fills
CLR_SURFACE = "#f9f2e0"       # surface-alt – blend with paper


def _severity_colour(value, warn_at=25, danger_at=50):
    if value >= danger_at:
        return CLR_DANGER
    if value >= warn_at:
        return CLR_WARN
    return CLR_OK


# ---------------------------------------------------------------------------
# Single cached computation — all heavy work done once per 2 min
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120, show_spinner="Loading dashboard…")
def _compute(lab_filter: str = ""):
    samples = db.get_all_samples()
    ast = db.get_all_ast_results()

    if lab_filter:
        if not samples.empty and "lab_name" in samples.columns:
            mask = samples["lab_name"].astype(str).str.strip().str.lower() == lab_filter.strip().lower()
            samples = samples[mask]
            if not ast.empty:
                ast = ast[ast["sample_id"].astype(str).isin(samples["sample_id"].astype(str))]

    if ast.empty or samples.empty:
        return None

    ast = ast.dropna(subset=["organism", "antibiotic", "result"])
    ast = ast[ast["result"].isin(["R", "I", "S"])]
    if ast.empty:
        return None

    n_samples = len(samples)
    n_tests = len(ast)
    n_organisms = int(ast["organism"].nunique())
    n_antibiotics = int(ast["antibiotic"].nunique())
    n_regions = int(samples["region"].nunique()) if "region" in samples.columns else 0
    n_labs = int(samples["lab_name"].nunique()) if "lab_name" in samples.columns else 0
    r_count = int((ast["result"] == "R").sum())
    r_rate = round(r_count / max(n_tests, 1) * 100, 1)

    mdro = analytics.calculate_mdro_incidence(ast)
    mdr_rate = mdro.get("mdr_rate_pct", 0)

    try:
        conn = db.get_connection()
        alert_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE is_acknowledged = 0").fetchone()[0]
    except Exception:
        logger.exception("alert count query failed")
        alert_count = 0

    # Monthly resistance trend
    monthly = []
    if "test_date" in ast.columns:
        tmp = ast[["test_date", "result"]].copy()
        tmp["test_date"] = pd.to_datetime(tmp["test_date"], errors="coerce")
        tmp = tmp.dropna(subset=["test_date"])
        if not tmp.empty:
            tmp["month"] = tmp["test_date"].dt.to_period("M")
            g = tmp.groupby("month")["result"]
            mdf = pd.DataFrame({"total": g.count(), "resistant": g.apply(lambda x: (x == "R").sum())})
            mdf["pct"] = (mdf["resistant"] / mdf["total"].clip(lower=1) * 100).round(1)
            mdf = mdf.sort_index()
            monthly = [{"m": str(i), "p": float(r["pct"])} for i, r in mdf.iterrows()]

    # Top resistant organisms
    g2 = ast.groupby("organism")["result"]
    odf = pd.DataFrame({"total": g2.count(), "resistant": g2.apply(lambda x: (x == "R").sum())})
    odf["pct"] = (odf["resistant"] / odf["total"].clip(lower=1) * 100).round(1)
    top_orgs = [{"org": str(i), "pct": float(r["pct"]), "n": int(r["total"])}
                for i, r in odf.nlargest(5, "pct").iterrows()]

    # Sentinel phenotypes
    raw = analytics.detect_sentinel_phenotypes(ast)
    phenotypes = [
        {"label": p.get("label", ""), "code": p.get("code", ""),
         "tier": p.get("who_tier", ""), "count": int(p.get("isolate_count", 0)),
         "rate": float(p.get("resistance_rate", 0))}
        for p in (raw or [])[:5]
    ]

    # Admin stats
    try:
        conn = db.get_connection()
        n_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
        n_datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        row = conn.execute("SELECT uploaded_at FROM datasets ORDER BY uploaded_at DESC LIMIT 1").fetchone()
        last_upload = row[0][:10] if row and row[0] else "—"
    except Exception:
        logger.exception("admin stats query failed")
        n_users = n_datasets = 0
        last_upload = "—"

    return dict(
        n_samples=n_samples, n_tests=n_tests, n_organisms=n_organisms,
        n_antibiotics=n_antibiotics, n_regions=n_regions, n_labs=n_labs,
        r_rate=r_rate, mdr_rate=mdr_rate, alert_count=alert_count,
        monthly=monthly, top_orgs=top_orgs, phenotypes=phenotypes,
        n_users=n_users, n_datasets=n_datasets, last_upload=last_upload,
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render_dashboard_page():
    is_admin = st.session_state.get("is_admin", False)
    lab_name = st.session_state.get("lab_name")
    user_email = st.session_state.get("user_email", "")

    name = "Administrator" if is_admin else (lab_name or user_email.split("@")[0])
    scope = "National surveillance overview" if is_admin else f"Surveillance summary for {lab_name or 'your lab'}"

    st.markdown(f"## Welcome back, {name}")
    st.caption(scope)

    data = _compute("" if is_admin else (lab_name or ""))
    if data is None:
        st.info("No surveillance data yet. Upload data via **Upload & Data Quality** to get started.")
        return

    # ── KPI metrics row ───────────────────────────────────────────
    st.divider()
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Samples", f"{data['n_samples']:,}", help=f"{data['n_labs']} labs reporting")
    k2.metric("AST Tests", f"{data['n_tests']:,}", help=f"{data['n_antibiotics']} antibiotics tested")
    k3.metric("Organisms", f"{data['n_organisms']}")
    k4.metric("Resistance", f"{data['r_rate']}%")
    k5.metric("MDR Rate", f"{data['mdr_rate']}%")
    k6.metric("Alerts", f"{data['alert_count']}", help="Unacknowledged alerts")

    st.markdown("")

    # ── Row: Trend chart + Top pathogens ──────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        with st.container(border=True):
            st.markdown(f"**Resistance Trend (Monthly)**")
            monthly = data["monthly"]
            if monthly:
                months = [m["m"] for m in monthly]
                pcts = [m["p"] for m in monthly]
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=months, y=pcts,
                    mode="lines+markers",
                    line=dict(color=CLR_PRIMARY, width=2.5, shape="spline"),
                    marker=dict(size=5, color=CLR_PRIMARY),
                    fill="tozeroy",
                    fillcolor=CLR_PRIMARY_SOFT,
                    hovertemplate="%{x}<br>%{y:.1f}% resistant<extra></extra>",
                ))
                fig.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0), height=260,
                    xaxis=dict(showgrid=False, tickfont=dict(size=10, color=CLR_TEXT_SEC)),
                    yaxis=dict(showgrid=True, gridcolor=CLR_BORDER, ticksuffix="%",
                               tickfont=dict(size=10, color=CLR_TEXT_SEC)),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            else:
                st.caption("No dated test records available.")

    with col_right:
        with st.container(border=True):
            st.markdown(f"**Top Resistant Pathogens**")
            top = data["top_orgs"]
            if top:
                for item in top:
                    pct = item["pct"]
                    colour = _severity_colour(pct)
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;align-items:center;"
                        f"padding:7px 0;border-bottom:1px solid {CLR_BORDER};'>"
                        f"<span style='font-size:0.9em;color:{CLR_TEXT};max-width:65%;"
                        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{item['org']}</span>"
                        f"<span style='font-size:0.9em;font-weight:600;color:{colour};'>{pct}%</span></div>"
                        f"<div style='background:{CLR_BG_SUBTLE};border-radius:4px;height:5px;margin-bottom:2px;'>"
                        f"<div style='background:{colour};width:{min(pct,100)}%;height:100%;border-radius:4px;'></div></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No organism data available.")

    st.markdown("")

    # ── Row: Sentinel phenotypes + System summary  ────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        with st.container(border=True):
            st.markdown(f"**Sentinel Phenotypes Detected**")
            phenos = data["phenotypes"]
            if phenos:
                for ph in phenos:
                    tier = ph["tier"]
                    colour = CLR_DANGER if tier == "CRITICAL" else CLR_WARN if tier == "HIGH" else CLR_PRIMARY
                    bg = "rgba(116, 26, 16, 0.1)" if tier == "CRITICAL" else "rgba(162, 113, 23, 0.12)" if tier == "HIGH" else CLR_BG_SUBTLE
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;align-items:center;"
                        f"padding:8px 0;border-bottom:1px solid {CLR_BORDER};'>"
                        f"<div><div style='font-size:0.9em;font-weight:500;color:{CLR_TEXT};'>{ph['label']}</div>"
                        f"<div style='font-size:0.78em;color:{CLR_TEXT_SEC};'>{ph['code']} · {ph['rate']}% resistance</div></div>"
                        f"<span style='background:{bg};color:{colour};padding:2px 10px;"
                        f"border-radius:10px;font-size:0.8em;font-weight:600;'>{ph['count']} isolates</span></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No sentinel phenotypes detected in current data.")

    with col_b:
        with st.container(border=True):
            st.markdown(f"**Coverage & System**")
            m1, m2 = st.columns(2)
            m1.metric("Regions", data["n_regions"])
            m2.metric("Sentinel Sites", data["n_labs"])

            if is_admin:
                st.divider()
                s1, s2, s3 = st.columns(3)
                s1.metric("Active Users", data["n_users"])
                s2.metric("Datasets", data["n_datasets"])
                s3.metric("Last Upload", data["last_upload"])
