"""
AMR Surveillance Dashboard for Multi-source Surveillance (Environment, Food, Human, Animal, Aquaculture)
Main Streamlit application with multi-page support.
"""
import streamlit as st
import pandas as pd
import numpy as np
import os
import uuid
import bcrypt
import secrets
import json
from dotenv import load_dotenv
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import plotly.express as px
import urllib.parse

# Import modules
from src import db, validate, plots, report, analytics
from src import email_utils
from src.lab_management import (
    get_lab_email_map,
    is_lab_user,
    KoboToolboxManager,
    kobo_submissions_to_frames,
    save_kobo_form_id,
    load_kobo_form_id
)
from src.page_pps import render_pps_page
from src.page_amu import render_amu_page
from src.page_amc import render_amc_page
from src.page_heatmap import render_heatmap_page
from src.page_pathogen_profile import render_pathogen_profile_page
from src.page_hai import render_hai_page

# Page configuration
st.set_page_config(
    page_title="ICBB-AMRSS",
    page_icon="🔬",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Initialize database
db.init_database()

# ── Keep-alive: prevent idle WebSocket disconnection ────────────────────
st.markdown(
    """
    <script>
    // Ping the Streamlit server every 2 minutes to keep the WebSocket alive
    (function keepAlive() {
        setInterval(function() {
            fetch(window.location.href, {method: 'HEAD', cache: 'no-store'})
                .catch(function(){});
        }, 120000);
    })();
    </script>
    """,
    unsafe_allow_html=True,
)

# Email verification via magic link is disabled

def _get_session_timeout_minutes():
    timeout_value = None
    try:
        if hasattr(st, "secrets") and "SESSION_TIMEOUT_MINUTES" in st.secrets:
            timeout_value = st.secrets.get("SESSION_TIMEOUT_MINUTES")
    except Exception:
        pass
    if timeout_value is None:
        timeout_value = os.getenv("SESSION_TIMEOUT_MINUTES")
    if timeout_value is None:
        return None
    try:
        timeout_minutes = int(timeout_value)
    except (TypeError, ValueError):
        return None
    return timeout_minutes if timeout_minutes > 0 else None


# Session timeout is disabled by default.
# To enable it, set SESSION_TIMEOUT_MINUTES in env or Streamlit secrets.
SESSION_TIMEOUT_MINUTES = _get_session_timeout_minutes()

# Authentication check
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.is_admin = False
    st.session_state.lab_name = None
    st.session_state.last_activity_time = None
    st.session_state.active_dataset_id = None  # Track selected dataset for filtering dashboards

# Check for session timeout
if SESSION_TIMEOUT_MINUTES and st.session_state.authenticated and st.session_state.last_activity_time:
    time_elapsed = (datetime.now() - st.session_state.last_activity_time).total_seconds() / 60
    if time_elapsed > SESSION_TIMEOUT_MINUTES:
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.is_admin = False
        st.session_state.last_activity_time = None
        st.session_state.lab_name = None
        st.warning("Session expired due to inactivity. Please log in again.")
        st.stop()
    else:
        # Update last activity time on each interaction
        st.session_state.last_activity_time = datetime.now()
else:
    # Set initial activity time on login
    if st.session_state.authenticated:
        st.session_state.last_activity_time = datetime.now()

def _get_admin_config():
    admin_email = None
    admin_password = None
    try:
        if hasattr(st, "secrets"):
            if "ADMIN_EMAIL" in st.secrets and "ADMIN_PASSWORD" in st.secrets:
                admin_email = st.secrets["ADMIN_EMAIL"]
                admin_password = st.secrets["ADMIN_PASSWORD"]
    except Exception:
        pass
    load_dotenv()
    admin_email = admin_email or os.getenv("ADMIN_EMAIL")
    admin_password = admin_password or os.getenv("ADMIN_PASSWORD")
    return admin_email, admin_password


def _get_lab_email_mapping() -> Dict[str, str]:
    return get_lab_email_map()


def _apply_lab_filter(samples_df: pd.DataFrame, ast_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    lab_name = st.session_state.get("lab_name")
    if st.session_state.get("is_admin") or not lab_name:
        return samples_df, ast_df
    if samples_df.empty:
        return samples_df, ast_df
    lab_mask = samples_df['lab_name'].astype(str).str.strip().str.lower() == lab_name.strip().lower()
    filtered_samples = samples_df[lab_mask]
    if ast_df.empty:
        return filtered_samples, ast_df
    filtered_ast = ast_df[ast_df['sample_id'].astype(str).isin(filtered_samples['sample_id'].astype(str))]
    return filtered_samples, filtered_ast

ADMIN_EMAIL, ADMIN_PASSWORD = _get_admin_config()
if ADMIN_EMAIL and ADMIN_PASSWORD:
    try:
        admin_user = db.get_user_by_email(ADMIN_EMAIL)
        password_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        if not admin_user:
            db.create_user(ADMIN_EMAIL, password_hash, is_admin=True)
        else:
            if not admin_user.get("is_admin"):
                db.set_user_admin(ADMIN_EMAIL, True)
            if not admin_user.get("is_active"):
                db.update_user_status(admin_user["user_id"], True)
            db.update_user_password(ADMIN_EMAIL, password_hash)
        try:
            db.set_user_verified(ADMIN_EMAIL, True)
        except Exception:
            pass
    except Exception:
        pass

def _get_flag(name: str) -> bool:
    val = None
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            val = st.secrets.get(name)
    except Exception:
        pass
    if val is None:
        val = os.getenv(name)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return False

try:
    if _get_flag("PURGE_NON_ADMIN_ON_DEPLOY"):
        flag_path = os.path.join("db", "purge_non_admin.flag")
        if not os.path.exists(flag_path):
            deleted_count, msg = db.delete_non_admin_users(ADMIN_EMAIL)
            os.makedirs("db", exist_ok=True)
            with open(flag_path, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} - {msg}")
            st.info(f"Startup maintenance: {msg}")
except Exception:
    pass

# If not authenticated, show login page
if not st.session_state.authenticated:
    # Render login page with professional styling
    
    st.markdown("""
        <style>
        /* Import Google Fonts */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        /* Main background with microbiology-themed image */
        .stApp {
            background: linear-gradient(135deg, rgba(6, 78, 59, 0.93) 0%, rgba(7, 89, 133, 0.93) 50%, rgba(14, 116, 144, 0.93) 100%),
                        url('https://images.unsplash.com/photo-1576086213369-97a306d36557?w=1920&q=80');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            font-family: 'Inter', sans-serif;
        }
        
        /* Hide default Streamlit elements */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Force centered, fixed-width login layout (even in wide mode) */
        .main {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }

        .main .block-container {
            max-width: 460px !important;
            width: 100% !important;
            margin: 0 auto !important;
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
        }
        
        /* Login card effect */
        .stTabs {
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(22px);
            border-radius: 22px;
            padding: 2.2rem;
            box-shadow: 0 30px 60px -20px rgba(0, 0, 0, 0.45);
            border: 1px solid rgba(255, 255, 255, 0.35);
        }

        .stTabs [data-baseweb="tab-panel"] {
            padding-top: 0.5rem;
        }
        
        /* Title styling */
        .login-title {
            text-align: center;
            font-size: 2.8em;
            font-weight: 700;
            background: linear-gradient(135deg, #0f766e 0%, #0891b2 50%, #0ea5e9 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.3rem;
            letter-spacing: -0.02em;
        }
        
        .login-subtitle {
            text-align: center;
            color: #e2e8f0;
            font-size: 1.05em;
            font-weight: 400;
            margin-bottom: 1rem;
            text-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
        }

        .login-badge {
            display: inline-block;
            text-align: center;
            margin: 0 auto 1.6rem auto;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            color: #0f172a;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.7);
            letter-spacing: 0.02em;
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25);
        }
        
        .login-icon {
            text-align: center;
            font-size: 3.6em;
            margin-bottom: 0.8rem;
            filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.25));
        }
        
        /* Form inputs */
        .stTextInput > div {
            max-width: 360px;
            margin: 0 auto;
        }

        .stTextInput > div > div > input {
            background: #f8fafc;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            padding: 0.8rem 1rem;
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        
        .stTextInput > div > div > input:focus {
            border-color: #14b8a6;
            box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.15);
        }
        
        /* Primary button styling */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #0d9488 0%, #0891b2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 0.8rem 2rem;
            font-weight: 600;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(13, 148, 136, 0.4);
        }

        .stButton > button[kind="primary"] {
            width: 100%;
            max-width: 360px;
            margin: 0.4rem auto 0;
            display: block;
        }
        
        .stButton > button[kind="primary"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(13, 148, 136, 0.5);
        }
        
        /* Tab styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            background: #f8fafc;
            border-radius: 999px;
            padding: 6px;
            border: 1px solid #e2e8f0;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.9rem;
            color: #64748b;
            padding: 0.35rem 1rem;
        }

        .stTabs [aria-selected="true"] {
            background: #0f766e;
            color: white;
            box-shadow: 0 6px 16px rgba(15, 118, 110, 0.35);
        }
        
        /* Footer text */
        .login-footer {
            text-align: center;
            color: rgba(255, 255, 255, 0.85);
            font-size: 0.85em;
            margin-top: 2rem;
            padding: 1rem;
        }
        
        .login-footer p {
            margin: 0.3rem 0;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Centered login form
    st.markdown('<div class="login-icon">🔬</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-title">ICBB-AMRSS</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">ICBB AMR Surveillance System</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;"><span class="login-badge">Secure Access Portal</span></div>', unsafe_allow_html=True)
    
    # Create tabs for login and info
    tab1, tab2 = st.tabs(["Login", "Information"])
    
    with tab1:
        st.subheader("Welcome Back")
        
        login_email = st.text_input("Email Address", placeholder="Enter your email", key="login_email")
        login_password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password")
        
        if st.button("Sign In", use_container_width=True, type="primary"):
            if not login_email or not login_password:
                st.error("Please fill in all fields")
            else:
                user = db.get_user_by_email(login_email)
                if user and user['is_active']:
                    try:
                        if bcrypt.checkpw(login_password.encode("utf-8"), user['password_hash'].encode("utf-8")):
                            # Email verification requirement removed; allow login if credentials match
                            config_admin_email, _ = _get_admin_config()
                            target_admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()

                            # Enforce admin role for configured admin email
                            is_admin_flag = user.get('is_admin')
                            if login_email.strip().lower() == target_admin_email:
                                is_admin_flag = 1
                                try:
                                    db.set_user_admin(login_email, True)
                                    db.update_user_status(user['user_id'], True)
                                    db.set_user_verified(login_email, True)
                                except Exception:
                                    pass

                            # Restrict to admin or approved lab users only
                            lab_mapping = _get_lab_email_mapping()
                            is_lab, lab_name = is_lab_user(login_email, lab_mapping)
                            if not is_admin_flag and not is_lab:
                                st.error("Access denied. This system is restricted to approved labs.")
                                st.session_state.authenticated = False
                                st.session_state.user_email = None
                                st.session_state.is_admin = False
                                st.session_state.lab_name = None
                                st.stop()

                            st.session_state.authenticated = True
                            st.session_state.user_email = login_email
                            st.session_state.last_activity_time = datetime.now()
                            st.session_state.is_admin = bool(is_admin_flag)
                            st.session_state.lab_name = lab_name if not is_admin_flag else None

                            db.update_last_login(login_email)
                            st.success("Login successful!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Invalid email or password")
                    except Exception as e:
                        st.error(f"Login error: {str(e)}")
                else:
                    st.error("Invalid email or password, or account is inactive")
    
    with tab2:
        st.subheader("Approved Laboratories")
        st.info("""
        Lab user accounts are pre-configured by the system administrator.
        
        Only authorized personnel from approved sentinel site laboratories have access.
        
        **Approved Laboratories:**
        • Eastern Regional Hospital
        • St. Martin De Porres Hospital Eikwe
        • Sekondi Public Health Reference Laboratory
        • Ho Teaching Hospital
        • Tamale Teaching Hospital
        • Komfo Anokye Teaching Hospital
        • Korle-Bu Teaching Hospital
        • Lekma Hospital
        • Sunyani Teaching Hospital
        • Cape Coast Teaching Hospital
        • National Food Safety Laboratory
        • CSIR Water Research Institute
        • Accra Veterinary Laboratory
        • Kumasi Veterinary Laboratory
        • Quadushah Medical Diagnostic Limited
        • Central Veterinary Laboratory
        • Pong Tamale School
        • Metropolis Health Care Limited
        • Alma Medical Laboratory Ltd
        
        Contact the AMR Surveillance Program administrator for access.
        """)
    
    st.markdown("""
        <div class="login-footer">
            <p>🇬🇭 ICBB-AMRSS</p>
            <p>ICBB AMR Surveillance System</p>
            <p style="margin-top: 0.5rem; opacity: 0.7;">Environment • Food • Human • Animal • Aquaculture</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.stop()

# ============================================================================
# MAIN APP STYLING (After Authentication)
# ============================================================================

# Professional styling for authenticated users
st.markdown("""
    <style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Main app background - subtle medical/lab pattern */
    .stApp {
        background: linear-gradient(135deg, rgba(248, 250, 252, 0.97) 0%, rgba(241, 245, 249, 0.97) 50%, rgba(226, 232, 240, 0.97) 100%),
                    url('https://images.unsplash.com/photo-1579154204601-01588f351e67?w=1920&q=80');
        background-size: cover;
        background-attachment: fixed;
        background-position: center;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Sidebar styling with laboratory/microscope background */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(7, 89, 133, 0.95) 0%, rgba(14, 116, 144, 0.92) 50%, rgba(6, 78, 59, 0.95) 100%),
                    url('https://images.unsplash.com/photo-1576086213369-97a306d36557?w=600&q=80');
        background-size: cover;
        background-position: center;
        background-blend-mode: overlay;
    }
    
    [data-testid="stSidebar"] > div:first-child {
        background: transparent;
    }
    
    /* Sidebar text styling */
    [data-testid="stSidebar"] .stMarkdown {
        color: #ecfdf5 !important;
    }
    
    [data-testid="stSidebar"] p, 
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label {
        color: #ecfdf5 !important;
    }
    
    /* Sidebar radio buttons */
    [data-testid="stSidebar"] .stRadio > label {
        color: #ecfdf5 !important;
        font-weight: 500;
    }
    
    [data-testid="stSidebar"] .stRadio > div {
        background: rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 0.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    [data-testid="stSidebar"] .stRadio > div > label {
        background: transparent;
        color: #d1fae5 !important;
        padding: 0.6rem 1rem;
        border-radius: 8px;
        transition: all 0.2s ease;
        margin: 2px 0;
    }
    
    [data-testid="stSidebar"] .stRadio > div > label:hover {
        background: rgba(20, 184, 166, 0.3);
        color: #ffffff !important;
    }
    
    [data-testid="stSidebar"] .stRadio > div > label[data-checked="true"] {
        background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
        color: white !important;
        box-shadow: 0 4px 15px rgba(20, 184, 166, 0.4);
    }
    
    /* Sidebar button styling */
    [data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    [data-testid="stSidebar"] .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(220, 38, 38, 0.5);
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important;
    }
    
    /* Sidebar expander styling */
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        color: #ecfdf5 !important;
    }
    
    [data-testid="stSidebar"] .streamlit-expanderContent {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 0 0 8px 8px;
    }
    
    /* Main content area */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Headers */
    h1 {
        background: linear-gradient(135deg, #0f766e 0%, #0891b2 50%, #0284c7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    
    h2, h3 {
        color: #0f766e;
        font-weight: 600;
    }
    
    /* Cards/Containers */
    .stMetric {
        background: rgba(255, 255, 255, 0.9);
        padding: 1.2rem;
        border-radius: 16px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
        border: 1px solid rgba(20, 184, 166, 0.2);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 12px;
        font-weight: 600;
        color: #0f766e;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #0d9488 0%, #0891b2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(13, 148, 136, 0.4);
    }
    
    .stButton > button[kind="secondary"] {
        background: white;
        color: #0d9488;
        border: 2px solid #0d9488;
    }
    
    /* Download button */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #059669 0%, #047857 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
    }
    
    .stDownloadButton > button:hover {
        box-shadow: 0 6px 20px rgba(5, 150, 105, 0.4);
    }
    
    /* Select boxes and inputs */
    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    .stTextInput > div > div > input {
        border-radius: 10px;
        border: 2px solid #e2e8f0;
        background: rgba(255, 255, 255, 0.9);
        transition: all 0.2s ease;
    }
    
    .stSelectbox > div > div:focus-within,
    .stMultiSelect > div > div:focus-within,
    .stTextInput > div > div > input:focus {
        border-color: #14b8a6;
        box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.15);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: rgba(241, 245, 249, 0.9);
        border-radius: 12px;
        padding: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-weight: 500;
        color: #64748b;
        padding: 0.5rem 1rem;
    }
    
    .stTabs [aria-selected="true"] {
        background: white;
        color: #0d9488;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }
    
    /* Success/Error/Info boxes */
    .stSuccess {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        border-left: 4px solid #059669;
        border-radius: 10px;
    }
    
    .stError {
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
        border-left: 4px solid #ef4444;
        border-radius: 10px;
    }
    
    .stInfo {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border-left: 4px solid #3b82f6;
        border-radius: 10px;
    }
    
    .stWarning {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border-left: 4px solid #f59e0b;
        border-radius: 10px;
    }
    
    /* User info card in sidebar */
    .user-info-card {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 1rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .user-info-card p {
        margin: 0.3rem 0;
        color: #ecfdf5;
    }
    
    /* Divider styling */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
        margin: 1.5rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# App title and description (only shown when authenticated)
st.markdown("# ICBB-AMRSS")
st.markdown("##### ICBB AMR Surveillance System — Multi-source Surveillance (Environment, Food, Human, Animal, Aquaculture) | Ghana")
st.markdown("---")

# Sidebar navigation with user info and admin panel
with st.sidebar:
    # Logo/Title
    st.markdown("""
        <div style="text-align: center; padding: 1rem 0 1.5rem 0;">
            <div style="font-size: 2.5em; margin-bottom: 0.5rem;">🔬</div>
            <div style="font-size: 1.2em; font-weight: 700; color: #e2e8f0;">ICBB-AMRSS</div>
            <div style="font-size: 0.85em; color: #94a3b8;">ICBB AMR Surveillance System</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # User info card
    st.markdown(f"""
        <div class="user-info-card">
            <p style="font-size: 0.8em; color: #a7f3d0; margin-bottom: 0.5rem;">Logged in as</p>
            <p style="font-weight: 600; color: #ecfdf5; font-size: 0.95em;">{st.session_state.user_email}</p>
            {"<p style='color: #fcd34d; font-size: 0.85em;'>Administrator</p>" if st.session_state.is_admin else ""}
            {f"<p style='color: #a7f3d0; font-size: 0.85em;'>{st.session_state.lab_name}</p>" if st.session_state.lab_name else ""}
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.is_admin = False
        st.session_state.last_activity_time = None
        st.session_state.lab_name = None
        st.success("Logged out successfully")
        st.rerun()
    
    st.markdown("---")
    st.markdown("<p style='color: #a7f3d0; font-size: 0.9em; font-weight: 600;'>Navigation</p>", unsafe_allow_html=True)

admin_pages = ["Admin - Users", "Admin - Datasets"] if st.session_state.is_admin else []
page = st.sidebar.radio(
    "",
    ["Upload & Data Quality", "Data Management", "Resistance Overview", "Resistance Heat Map", "Pathogen Profile", "HAI Profile", "Trends", "Map Hotspots", "Advanced Analytics", "Risk Assessment", "Comparative Analysis", "PPS Dashboard", "AMU Dashboard", "AMC Dashboard", "Alerts Dashboard", "Antibiogram", "WHONET Export", "Report Export"] + admin_pages,
    label_visibility="collapsed"
)

# ── Priority Pathogen Quick Filter (sidebar) ──────────────────────────
_pp_filter_path = os.path.join("data", "lookups", "priority_pathogens.json")
if os.path.exists(_pp_filter_path):
    with open(_pp_filter_path, "r") as _pf:
        _pp_lookup = json.load(_pf)
    _who_pp = _pp_lookup.get("WHO_2024_PRIORITY_PATHOGENS", {})
    _ghana_pp = _pp_lookup.get("GHANA_PRIORITY_PATHOGENS", {})
    _all_pp_names = sorted(set(
        p for pp_dict in [_who_pp, _ghana_pp]
        for tier_list in pp_dict.values()
        for p in tier_list
    ))
    if _all_pp_names:
        with st.sidebar.expander("Priority Pathogen Filter", expanded=False):
            pp_source = st.selectbox("List", ["WHO 2024", "Ghana"], key="pp_source")
            pp_dict = _who_pp if pp_source == "WHO 2024" else _ghana_pp
            pp_tier = st.selectbox("Tier", ["All"] + list(pp_dict.keys()), key="pp_tier")
            if pp_tier == "All":
                pp_names = sorted(set(p for lst in pp_dict.values() for p in lst))
            else:
                pp_names = pp_dict.get(pp_tier, [])
            st.session_state['priority_pathogen_filter'] = pp_names
            st.caption(f"{len(pp_names)} pathogens selected")

# ============================================================================
# PAGE 1: UPLOAD & DATA QUALITY
# ============================================================================
if page == "Upload & Data Quality":
    st.header("Upload & Data Quality")
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        st.subheader("📋 Template Download")
        os.makedirs("templates", exist_ok=True)
        try:
            from src.validate_onehealth import create_unified_template
            unified_bytes = create_unified_template()
            st.download_button(
                label="⬇ Download Unified Template",
                data=unified_bytes,
                file_name="AMR_OneHealth_Unified_Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Single workbook with all sheets: samples, ast_results, pps_survey, prescriptions, amu_data, amc_data",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Error creating unified template: {e}")
        st.caption("One Excel file · 6 sheets · fill only what you need")
    
    with col1:
        st.subheader("Upload Data")
        uploaded_file = st.file_uploader(
            "Upload the unified Excel template (samples + AST + PPS + AMU + AMC sheets)",
            type=["xlsx", "xls"]
        )
        
        if uploaded_file:
            if st.button("Validate & Upload", type="primary"):
                with st.spinner("Validating all sheets..."):
                    # ── Core AMR (samples + ast_results) ────────────────
                    is_valid, errors, samples_df, ast_df = validate.validate_upload(uploaded_file)
                    
                    amr_saved = False
                    if is_valid:
                        if st.session_state.lab_name:
                            lab_values = samples_df['lab_name'].astype(str).str.strip().unique().tolist()
                            if len(lab_values) != 1 or lab_values[0].strip().lower() != st.session_state.lab_name.strip().lower():
                                st.error("Uploaded data must contain only your laboratory in the lab_name column.")
                                st.stop()

                        auto_interpreted_count = ast_df['auto_interpreted'].sum() if 'auto_interpreted' in ast_df.columns else 0
                        if auto_interpreted_count > 0:
                            st.info(f"🔬 Automated interpretation: {int(auto_interpreted_count)} AST results (CLSI/EUCAST)")

                        dataset_id = str(uuid.uuid4())[:8]
                        success, msg = db.save_dataset(
                            dataset_id,
                            uploaded_file.name.replace('.xlsx', ''),
                            samples_df,
                            ast_df,
                            uploaded_by=(st.session_state.user_email or "Anonymous")
                        )
                        if success:
                            st.success(f"✅ AMR data saved (ID: {dataset_id}) — {len(samples_df)} samples, {len(ast_df)} tests")
                            amr_saved = True
                        else:
                            st.error(f"Database error: {msg}")
                    elif errors:
                        # Only show AMR errors if sheets existed
                        uploaded_file.seek(0)
                        from openpyxl import load_workbook as _lwb
                        _wb = _lwb(uploaded_file, read_only=True)
                        _has_amr = 'samples' in _wb.sheetnames or 'ast_results' in _wb.sheetnames
                        _wb.close()
                        if _has_amr:
                            st.warning("⚠ AMR sheets (samples/ast_results) had errors:")
                            for i, error in enumerate(errors, 1):
                                st.markdown(f"  {i}. {error}")

                    # ── One Health sheets (PPS / AMU / AMC) ─────────────
                    uploaded_file.seek(0)
                    from src.validate_onehealth import validate_unified_upload
                    oh_ok, oh_errors, oh_result = validate_unified_upload(uploaded_file)

                    oh_any = bool(oh_result)
                    if oh_errors:
                        for e in oh_errors:
                            st.warning(f"⚠ {e}")

                    user_email = st.session_state.get('user_email', 'unknown')

                    # PPS
                    if 'pps_survey' in oh_result and 'pps_prescriptions' in oh_result:
                        import uuid as _uuid
                        survey_raw = oh_result['pps_survey']
                        # Handle both DataFrame and legacy dict
                        survey_df = survey_raw if isinstance(survey_raw, pd.DataFrame) else pd.DataFrame([survey_raw])
                        rx_df = oh_result['pps_prescriptions']
                        n_surveys = len(survey_df)
                        n_rx = len(rx_df)
                        rx_per = max(1, n_rx // n_surveys) if n_surveys else 0
                        rx_idx = 0
                        pps_ok_count = 0
                        for _, srow in survey_df.iterrows():
                            sid = f"PPS-{_uuid.uuid4().hex[:8]}"
                            end_idx = min(rx_idx + rx_per, n_rx)
                            chunk = rx_df.iloc[rx_idx:end_idx] if rx_idx < n_rx else pd.DataFrame()
                            rx_idx = end_idx
                            ok, msg = db.save_pps_survey(
                                sid,
                                str(srow['facility_name']),
                                str(srow['survey_date']),
                                str(srow.get('region', '')),
                                str(srow.get('district', '')),
                                int(srow.get('total_patients', 0)),
                                int(srow.get('patients_on_antibiotics', 0)),
                                chunk,
                                uploaded_by=user_email,
                            )
                            if ok:
                                pps_ok_count += 1
                        if pps_ok_count:
                            st.success(f"✅ PPS saved — {pps_ok_count} surveys, {n_rx} prescriptions")
                        else:
                            st.error("PPS save error: no surveys could be saved")

                    # AMU
                    if 'amu_data' in oh_result:
                        amu_df = oh_result['amu_data']
                        ok_a, msg_a = db.save_amu_records(amu_df, user_email)
                        if ok_a:
                            st.success(f"✅ AMU saved — {len(amu_df)} records")
                        else:
                            st.error(f"AMU save error: {msg_a}")

                    # AMC
                    if 'amc_data' in oh_result:
                        amc_df = oh_result['amc_data']
                        ok_c, msg_c = db.save_amc_records(amc_df, user_email)
                        if ok_c:
                            st.success(f"✅ AMC saved — {len(amc_df)} records")
                        else:
                            st.error(f"AMC save error: {msg_c}")

                    if amr_saved or oh_any:
                        st.balloons()
    
    st.markdown("---")
    
    # Show existing datasets
    st.subheader("Existing Datasets")
    datasets = db.get_all_datasets()
    # Hide admin-owned datasets from non-admin users
    config_admin_email, _ = _get_admin_config()
    admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()
    if not st.session_state.is_admin:
        datasets = [ds for ds in datasets if (ds.get('uploaded_by') or '').strip().lower() != admin_email]
    if st.session_state.lab_name:
        datasets = [
            ds for ds in datasets
            if (ds.get('uploaded_by') or '').strip().lower() == (st.session_state.user_email or '').strip().lower()
        ]
    
    if datasets:
        for ds in datasets:
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.write(f"**{ds['dataset_name']}**")
                st.caption(f"ID: {ds['dataset_id']} | Uploaded: {ds['uploaded_at'][:10]}")
            
            with col2:
                st.metric("Samples", ds['rows_samples'])
                st.metric("Tests", ds['rows_tests'])
            
            with col3:
                if st.button("Delete", key=f"del_{ds['dataset_id']}"):
                    success, msg = db.delete_dataset(ds['dataset_id'])
                    if success:
                        st.success("Deleted!")
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.info("No datasets uploaded yet. Upload one above.")

# ============================================================================
# PAGE 2: DATA MANAGEMENT
# ============================================================================
elif page == "Data Management":
    st.header("Data Management")
    st.markdown("Manage, review, and maintain your AMR surveillance datasets")

    # Get all datasets
    datasets = db.get_all_datasets()
    # Hide admin-owned datasets from non-admin users
    config_admin_email, _ = _get_admin_config()
    admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()
    if not st.session_state.is_admin:
        datasets = [ds for ds in datasets if (ds.get('uploaded_by') or '').strip().lower() != admin_email]
    if st.session_state.lab_name:
        datasets = [
            ds for ds in datasets
            if (ds.get('uploaded_by') or '').strip().lower() == (st.session_state.user_email or '').strip().lower()
        ]

    if not datasets:
        st.info("No datasets available. Please upload data first on the 'Upload & Data Quality' page.")
    else:
        # Dataset selection
        dataset_names = [f"{ds['dataset_name']} (ID: {ds['dataset_id']})" for ds in datasets]
        selected_dataset_display = st.selectbox(
            "Select Dataset to Manage",
            dataset_names,
            key="data_mgmt_dataset"
        )
        # Extract dataset ID and store in session
        try:
            selected_dataset_id = selected_dataset_display.split("(ID: ")[1].rstrip(")")
            st.session_state.active_dataset_id = selected_dataset_id
            st.success(f"Active dataset: {selected_dataset_id}")
        except:
            st.warning("Unable to parse dataset ID. Please reselect.")
elif page == "Admin - Datasets":
    st.header("Admin - Datasets")
    config_admin_email, _ = _get_admin_config()
    admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()

    all_datasets = db.get_all_datasets()

    main_datasets = db.get_main_datasets(country="Ghana")
    main_choices = [f"{d['dataset_name']} ({d['dataset_id']})" for d in main_datasets] or ["None"]
    selected_main_display = st.selectbox("National Main Dataset (Ghana)", main_choices, key="main_ds_select")

    st.markdown("---")
    st.subheader("Mark a dataset as National Main")
    ds_choices = [f"{d['dataset_name']} ({d['dataset_id']})" for d in all_datasets]
    target_display = st.selectbox("Select dataset", ds_choices, key="mark_main_select")
    if st.button("Set as National Main (Ghana)", type="primary"):
        try:
            target_id = target_display.split("(")[-1].rstrip(")")
            ok, msg = db.set_dataset_main(target_id, True, country="Ghana")
            if ok:
                st.success("Main dataset updated")
                st.rerun()
            else:
                st.error(msg)
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Merge User Dataset into National Main")
    user_datasets = [d for d in all_datasets if (d.get('uploaded_by') or '').strip().lower() != admin_email]
    user_choices = [f"{d['uploaded_by'] or 'Unknown'}: {d['dataset_name']} ({d['dataset_id']})" for d in user_datasets] or ["No user datasets"]

    src_display = st.selectbox("Select user dataset", user_choices, key="merge_src_select")
    # Refresh main choices
    main_datasets = db.get_main_datasets(country="Ghana")
    main_choices = [f"{d['dataset_name']} ({d['dataset_id']})" for d in main_datasets] or ["None"]
    merge_target_display = st.selectbox("Target main dataset", main_choices, key="merge_target_select")

    if st.button("Merge into National Main", type="primary"):
        try:
            if not main_datasets:
                st.error("Please mark a dataset as National Main first")
            else:
                src_id = src_display.split("(")[-1].rstrip(")")
                target_id = merge_target_display.split("(")[-1].rstrip(")")
                ok, msg = db.merge_dataset_into_main(src_id, target_id)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("KoboToolbox Sync")
    with st.expander("Import submissions from KoboToolbox", expanded=False):
        saved_form_id = load_kobo_form_id() or ""
        form_id = st.text_input("KoboToolbox Form ID", value=saved_form_id, key="kobo_form_id")

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Create KoboToolbox Form", key="kobo_create_form"):
                with st.spinner("Creating KoboToolbox form..."):
                    kobo = KoboToolboxManager()
                    ok, msg, form_data = kobo.create_amr_form()
                    if not ok:
                        st.error(msg)
                    else:
                        new_form_id = str(form_data.get("uid") or form_data.get("id") or "").strip()
                        if new_form_id:
                            save_ok, save_msg = save_kobo_form_id(new_form_id)
                            st.success(f"Form created. Form ID: {new_form_id}")
                            if not save_ok:
                                st.warning(save_msg)
                        else:
                            st.warning("Form created but Form ID was not returned. Please copy it manually from KoboToolbox.")
        with col_b:
            if st.button("Save Form ID", key="kobo_save_form_id"):
                if not form_id:
                    st.error("Please enter a Form ID to save.")
                else:
                    ok, msg = save_kobo_form_id(form_id)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        if st.button("Sync KoboToolbox Submissions", key="kobo_sync"):
            if not form_id:
                st.error("Please provide a KoboToolbox Form ID.")
            else:
                with st.spinner("Syncing data from KoboToolbox..."):
                    kobo = KoboToolboxManager()
                    ok, msg, submissions_df = kobo.fetch_submitted_data(form_id)
                    if not ok:
                        st.error(msg)
                    elif submissions_df is None or submissions_df.empty:
                        st.info("No submissions available for import.")
                    else:
                        samples_df, ast_df = kobo_submissions_to_frames(submissions_df)
                        sample_valid, sample_errors = validate.validate_samples(samples_df)
                        ast_valid, ast_errors = validate.validate_ast_results(ast_df, set(samples_df['sample_id'].dropna().astype(str)))
                        errors = sample_errors + ast_errors

                        if errors:
                            st.error("KoboToolbox data validation failed.")
                            for err in errors[:10]:
                                st.write(f"- {err}")
                        else:
                            # Deduplicate by existing sample_id and (isolate_id + antibiotic) combination
                            existing_samples_df = db.get_all_samples()
                            existing_ast_df = db.get_all_ast_results()

                            existing_sample_ids = set(existing_samples_df['sample_id'].dropna().astype(str)) if not existing_samples_df.empty else set()
                            
                            # Create set of (isolate_id + antibiotic) combinations to allow same isolate tested against different antibiotics
                            existing_ast_combos = set()
                            if not existing_ast_df.empty:
                                existing_ast_combos = set(
                                    (str(row['isolate_id']), str(row['antibiotic'])) 
                                    for idx, row in existing_ast_df.iterrows()
                                    if pd.notna(row['isolate_id']) and pd.notna(row['antibiotic'])
                                )

                            before_samples = len(samples_df)
                            before_tests = len(ast_df)

                            samples_df = samples_df[~samples_df['sample_id'].astype(str).isin(existing_sample_ids)]
                            
                            # Filter AST data by (isolate_id + antibiotic) combination
                            ast_df['_combo'] = list(zip(
                                ast_df['isolate_id'].astype(str),
                                ast_df['antibiotic'].astype(str)
                            ))
                            ast_df = ast_df[~ast_df['_combo'].isin(existing_ast_combos)]
                            ast_df = ast_df.drop(columns=['_combo'])

                            # Ensure AST rows correspond to remaining samples
                            ast_df = ast_df[ast_df['sample_id'].astype(str).isin(samples_df['sample_id'].astype(str))]

                            dropped_samples = before_samples - len(samples_df)
                            dropped_tests = before_tests - len(ast_df)

                            if samples_df.empty or ast_df.empty:
                                st.info("No new unique records found after deduplication.")
                                st.stop()

                            dataset_id = str(uuid.uuid4())[:8]
                            dataset_name = f"Kobo Sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                            success, save_msg = db.save_dataset(
                                dataset_id,
                                dataset_name,
                                samples_df,
                                ast_df,
                                uploaded_by=(st.session_state.user_email or "System")
                            )
                            if success:
                                st.success(f"KoboToolbox data imported as dataset {dataset_id}")
                                if dropped_samples or dropped_tests:
                                    st.info(f"Skipped duplicates: {dropped_samples} samples, {dropped_tests} tests")
                            else:
                                st.error(save_msg)

        # Admin page continues without dataset preview block to avoid undefined variables

# ============================================================================
# PAGE 3: RESISTANCE OVERVIEW
# ============================================================================
elif page == "Resistance Overview":
    st.header("Resistance Overview")
    
    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    # Get data for active dataset only
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # Filters
        st.sidebar.markdown("### Filters")
        
        # Sentinel Site / Lab filter
        labs = sorted(all_samples['lab_name'].dropna().astype(str).unique().tolist()) if 'lab_name' in all_samples.columns else []
        if labs:
            lab_options = ["All"] + labs
            selected_lab_options = st.sidebar.multiselect(
                "Sentinel Site / Lab",
                lab_options,
                default=["All"]
            )
            if "All" in selected_lab_options:
                selected_labs = labs
            else:
                selected_labs = [opt for opt in selected_lab_options if opt != "All"]
        else:
            selected_labs = []
        
        # Organism filter
        organisms = sorted(all_ast['organism'].dropna().astype(str).unique().tolist())
        if organisms:
            organism_options = ["All"] + organisms
            selected_organism_options = st.sidebar.multiselect(
                "Organism", 
                organism_options, 
                default=["All"]
            )
            # If "All" is selected, use all organisms; otherwise use selected ones
            if "All" in selected_organism_options:
                selected_organisms = organisms
            else:
                selected_organisms = [opt for opt in selected_organism_options if opt != "All"]
        else:
            selected_organisms = []
            st.sidebar.warning("No organisms found")
        
        # Antibiotic filter
        antibiotics = sorted(all_ast['antibiotic'].dropna().astype(str).unique().tolist())
        if antibiotics:
            antibiotic_options = ["All"] + antibiotics
            selected_antibiotic_options = st.sidebar.multiselect(
                "Antibiotic",
                antibiotic_options,
                default=["All"]
            )
            # If "All" is selected, use all antibiotics; otherwise use selected ones
            if "All" in selected_antibiotic_options:
                selected_antibiotics = antibiotics
            else:
                selected_antibiotics = [opt for opt in selected_antibiotic_options if opt != "All"]
        else:
            selected_antibiotics = []
        
        # Source category filter
        categories = sorted(all_samples['source_category'].dropna().astype(str).unique().tolist())
        if categories:
            category_options = ["All"] + categories
            selected_category_options = st.sidebar.multiselect(
                "Source Category",
                category_options,
                default=["All"]
            )
            # If "All" is selected, use all categories; otherwise use selected ones
            if "All" in selected_category_options:
                selected_categories = categories
            else:
                selected_categories = [opt for opt in selected_category_options if opt != "All"]
        else:
            selected_categories = []
        
        # Source type filter
        source_types = sorted(all_samples['source_type'].dropna().astype(str).unique().tolist())
        if source_types:
            source_type_options = ["All"] + source_types
            selected_source_type_options = st.sidebar.multiselect(
                "Source Type",
                source_type_options,
                default=["All"]
            )
            # If "All" is selected, use all source types; otherwise use selected ones
            if "All" in selected_source_type_options:
                selected_source_types = source_types
            else:
                selected_source_types = [opt for opt in selected_source_type_options if opt != "All"]
        else:
            selected_source_types = []
        
        # Site type filter
        site_types = sorted(all_samples['site_type'].dropna().astype(str).unique().tolist())
        if site_types:
            site_type_options = ["All"] + site_types
            selected_site_type_options = st.sidebar.multiselect(
                "Site Type",
                site_type_options,
                default=["All"]
            )
            # If "All" is selected, use all site types; otherwise use selected ones
            if "All" in selected_site_type_options:
                selected_site_types = site_types
            else:
                selected_site_types = [opt for opt in selected_site_type_options if opt != "All"]
        else:
            selected_site_types = []
        
        # Region filter
        regions = sorted(all_samples['region'].dropna().astype(str).unique().tolist())
        if regions:
            region_options = ["All"] + regions
            selected_region_options = st.sidebar.multiselect(
                "Region",
                region_options,
                default=["All"]
            )
            # If "All" is selected, use all regions; otherwise use selected ones
            if "All" in selected_region_options:
                selected_regions = regions
            else:
                selected_regions = [opt for opt in selected_region_options if opt != "All"]
        else:
            selected_regions = []
        
        # District filter
        districts = sorted(all_samples['district'].dropna().astype(str).unique().tolist())
        if districts:
            district_options = ["All"] + districts
            selected_district_options = st.sidebar.multiselect(
                "District",
                district_options,
                default=["All"]
            )
            # If "All" is selected, use all districts; otherwise use selected ones
            if "All" in selected_district_options:
                selected_districts = districts
            else:
                selected_districts = [opt for opt in selected_district_options if opt != "All"]
        else:
            selected_districts = []
        
        # Apply filters with validation
        if selected_categories and selected_regions and selected_districts:
            _mask = (
                (all_samples['source_category'].astype(str).isin(selected_categories)) &
                (all_samples['source_type'].astype(str).isin(selected_source_types)) &
                (all_samples['site_type'].astype(str).isin(selected_site_types)) &
                (all_samples['region'].astype(str).isin(selected_regions)) &
                (all_samples['district'].astype(str).isin(selected_districts))
            )
            if selected_labs and 'lab_name' in all_samples.columns:
                _mask = _mask & (all_samples['lab_name'].astype(str).isin(selected_labs))
            filtered_samples = all_samples[_mask]
        else:
            filtered_samples = all_samples
        
        if selected_organisms and selected_antibiotics:
            filtered_ast = all_ast[
                (all_ast['organism'].astype(str).isin(selected_organisms)) &
                (all_ast['antibiotic'].astype(str).isin(selected_antibiotics)) &
                (all_ast['sample_id'].astype(str).isin(filtered_samples['sample_id'].astype(str)))
            ]
        else:
            filtered_ast = all_ast[
                all_ast['sample_id'].astype(str).isin(filtered_samples['sample_id'].astype(str))
            ]
        
        if filtered_ast.empty:
            st.warning("No data matches the selected filters.")
        else:
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                resistant_count = (filtered_ast['result'] == 'R').sum()
                total_tests = len(filtered_ast)
                pct = resistant_count / total_tests * 100 if total_tests > 0 else 0
                st.metric("Resistance %", f"{pct:.1f}%", delta=f"{resistant_count}/{total_tests}")
            
            with col2:
                st.metric("Total Tests", total_tests)
            
            with col3:
                st.metric("Unique Samples", filtered_samples['sample_id'].nunique())
            
            with col4:
                st.metric("Unique Organisms", filtered_ast['organism'].nunique())
            
            # ── Sentinel Phenotype & MDRO KPI Row ──────────────────────
            from src.analytics import detect_sentinel_phenotypes, calculate_mdro_incidence
            _sentinel = detect_sentinel_phenotypes(filtered_ast)
            _mdro = calculate_mdro_incidence(filtered_ast)

            if _sentinel or _mdro.get("mdr_isolates", 0) > 0:
                st.markdown("""
                <style>
                .sentinel-row { display:flex; gap:0.6rem; flex-wrap:wrap; margin-bottom:1rem; }
                .sentinel-card {
                    flex:1; min-width:110px; padding:0.7rem 0.6rem; border-radius:10px;
                    text-align:center; border:1px solid rgba(0,0,0,0.08);
                }
                .sentinel-card.crit { background:linear-gradient(135deg,#5c1e1e,#3d1010); }
                .sentinel-card.high { background:linear-gradient(135deg,#5c4a1e,#3d3010); }
                .sentinel-card.info { background:linear-gradient(135deg,#1e3a5f,#0d253f); }
                .sentinel-card .sv { font-size:1.5rem; font-weight:700; color:#fff; }
                .sentinel-card .sl { font-size:0.72rem; color:rgba(255,255,255,0.65); margin-top:0.15rem; }
                </style>
                """, unsafe_allow_html=True)

                cards_html = '<div class="sentinel-row">'
                # MDRO card
                _mdr_n = _mdro.get("mdr_isolates", 0)
                _mdr_pct = _mdro.get("mdr_rate_pct", 0)
                cards_html += (
                    f'<div class="sentinel-card {"crit" if _mdr_pct >= 30 else "info"}">'
                    f'<div class="sv">{_mdr_n}</div>'
                    f'<div class="sl">MDR Isolates ({_mdr_pct:.0f}%)</div></div>'
                )
                # Sentinel phenotype cards (top 5)
                for sp in _sentinel[:5]:
                    tier_class = "crit" if sp["who_tier"] == "Critical" else "high"
                    cards_html += (
                        f'<div class="sentinel-card {tier_class}">'
                        f'<div class="sv">{sp["isolate_count"]}</div>'
                        f'<div class="sl">{sp["code"]} ({sp["resistance_rate"]:.0f}%)</div></div>'
                    )
                cards_html += '</div>'
                st.markdown(cards_html, unsafe_allow_html=True)

                with st.expander("Sentinel Phenotype Details", expanded=False):
                    if _sentinel:
                        _sp_df = pd.DataFrame([{
                            "Phenotype": s["code"],
                            "Description": s["label"],
                            "WHO Tier": s["who_tier"],
                            "Positive Isolates": s["isolate_count"],
                            "Tested": s["total_tested"],
                            "Rate %": s["resistance_rate"],
                        } for s in _sentinel])
                        st.dataframe(_sp_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No WHO sentinel phenotypes detected in the current data.")

            st.markdown("---")
            
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                st.plotly_chart(
                    plots.plot_top_antibiotics(filtered_ast),
                    use_container_width=True
                )
            
            with col2:
                st.plotly_chart(
                    plots.plot_resistance_distribution(filtered_ast),
                    use_container_width=True
                )
            
            st.plotly_chart(
                plots.plot_resistance_by_category(filtered_ast, filtered_samples),
                use_container_width=True
            )
            
            st.plotly_chart(
                plots.plot_resistance_by_source_type(filtered_ast, filtered_samples),
                use_container_width=True
            )
            
            st.info("📊 For a detailed organism × antibiotic resistance matrix, visit the **Resistance Heat Map** page.")
            
            st.markdown("---")
            
            # Co-resistance patterns
            st.subheader("🔗 Co-Resistance Patterns")
            
            co_resistance = plots.get_co_resistance_patterns(filtered_ast)
            if not co_resistance.empty:
                st.dataframe(co_resistance, use_container_width=True)
            else:
                st.info("No co-resistance patterns detected")
            
            st.markdown("---")
            
            # Resistance Mechanisms
            st.subheader("🧬 Resistance Mechanisms")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                mech_fig = plots.plot_resistance_mechanisms(filtered_ast)
                st.plotly_chart(mech_fig, use_container_width=True)
            
            with col2:
                from src.analytics import detect_resistance_mechanisms
                mechanisms_df = detect_resistance_mechanisms(filtered_ast)
                if not mechanisms_df.empty:
                    st.dataframe(mechanisms_df[['isolate_id', 'organism', 'resistance_mechanism', 'confidence']].head(50), use_container_width=True)
                else:
                    st.info("No resistance mechanisms detected")
            
            st.markdown("---")
            
            # Cross-resistance patterns
            st.subheader("🔄 Cross-Resistance Patterns")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                cross_fig = plots.plot_cross_resistance_patterns(filtered_ast)
                st.plotly_chart(cross_fig, use_container_width=True)
            
            with col2:
                from src.analytics import detect_cross_resistance
                cross_df = detect_cross_resistance(filtered_ast)
                if not cross_df.empty:
                    st.dataframe(cross_df[['isolate_id', 'organism', 'antibiotic_class', 'cross_resistance_level']].head(50), use_container_width=True)
                else:
                    st.info("No cross-resistance patterns detected")
            
            st.markdown("---")
            
            # Data preview
            st.subheader("Data Preview")
            display_df = filtered_ast[['sample_id', 'organism', 'antibiotic', 'result', 'method', 'test_date']].head(100)
            st.dataframe(display_df, use_container_width=True)

# ============================================================================
# PAGE: RESISTANCE HEAT MAP
# ============================================================================
elif page == "Resistance Heat Map":
    render_heatmap_page()

# ============================================================================
# PAGE: PATHOGEN PROFILE
# ============================================================================
elif page == "Pathogen Profile":
    render_pathogen_profile_page()

# ============================================================================
# PAGE: HAI PROFILE
# ============================================================================
elif page == "HAI Profile":
    render_hai_page()

# ============================================================================
# PAGE 4: TRENDS
# ============================================================================
elif page == "Trends":
    st.header("Resistance Trends")
    
    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # Filters
        st.sidebar.markdown("### Trend Filters")
        
        # Sentinel Site / Lab filter
        _labs_tr = sorted(all_samples['lab_name'].dropna().astype(str).unique().tolist()) if 'lab_name' in all_samples.columns else []
        if _labs_tr:
            _lab_opts_tr = ["All"] + _labs_tr
            _sel_lab_opts_tr = st.sidebar.multiselect("Sentinel Site / Lab (Trends)", _lab_opts_tr, default=["All"])
            if "All" not in _sel_lab_opts_tr and _sel_lab_opts_tr:
                all_samples = all_samples[all_samples['lab_name'].astype(str).isin(_sel_lab_opts_tr)]
                all_ast = all_ast[all_ast['sample_id'].astype(str).isin(all_samples['sample_id'].astype(str))]
        
        organisms = sorted(all_ast['organism'].dropna().astype(str).unique().tolist())
        if organisms:
            organism_options = ["All"] + organisms
            selected_organism_options = st.sidebar.multiselect(
                "Organism (Trends)",
                organism_options,
                default=["All"]
            )
            # If "All" is selected, use all organisms; otherwise use selected ones
            if "All" in selected_organism_options:
                selected_organisms = organisms
            else:
                selected_organisms = [opt for opt in selected_organism_options if opt != "All"]
        else:
            selected_organisms = []
        
        antibiotics = sorted(all_ast['antibiotic'].dropna().astype(str).unique().tolist())
        if antibiotics:
            antibiotic_options = ["All"] + antibiotics
            selected_antibiotic_options = st.sidebar.multiselect(
                "Antibiotic (Trends)",
                antibiotic_options,
                default=["All"]
            )
            # If "All" is selected, use all antibiotics; otherwise use selected ones
            if "All" in selected_antibiotic_options:
                selected_antibiotics = antibiotics
            else:
                selected_antibiotics = [opt for opt in selected_antibiotic_options if opt != "All"]
        else:
            selected_antibiotics = []
        
        # Time aggregation
        time_agg = st.sidebar.selectbox("Time Aggregation", ["Monthly", "Quarterly", "Yearly"])
        
        # Apply filters
        if selected_organisms and selected_antibiotics:
            filtered_ast = all_ast[
                (all_ast['organism'].astype(str).isin(selected_organisms)) &
                (all_ast['antibiotic'].astype(str).isin(selected_antibiotics))
            ]
        else:
            filtered_ast = all_ast
        
        if filtered_ast.empty:
            st.warning("No data matches the selected filters. Try selecting different filters.")
        else:
            # Overall trend
            st.plotly_chart(
                plots.plot_resistance_trends(filtered_ast, time_agg),
                use_container_width=True
            )
            
            st.markdown("---")
            
            # Show summary statistics
            st.subheader("Trend Summary")
            
            col1, col2, col3 = st.columns(3)
            
            # Calculate oldest and newest dates
            filtered_ast['test_date_parsed'] = pd.to_datetime(filtered_ast['test_date'], errors='coerce')
            valid_dates = filtered_ast[filtered_ast['test_date_parsed'].notna()]['test_date_parsed']
            
            if not valid_dates.empty:
                earliest = valid_dates.min().strftime('%Y-%m-%d')
                latest = valid_dates.max().strftime('%Y-%m-%d')
                
                with col1:
                    st.metric("Earliest Test", earliest)
                with col2:
                    st.metric("Latest Test", latest)
                with col3:
                    st.metric("Date Range", f"{len(valid_dates)} tests")
            
            st.markdown("---")
            
            # Data preview
            st.subheader("Recent Test Data")
            display_df = filtered_ast[['test_date', 'organism', 'antibiotic', 'result', 'sample_id']].sort_values('test_date', ascending=False).head(100)
            st.dataframe(display_df, use_container_width=True)

# ============================================================================
# PAGE 5: MAP HOTSPOTS
# ============================================================================
elif page == "Map Hotspots":
    st.header("Geographic Hotspots & Regional Analysis")
    
    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")

    # Sentinel Site / Lab sidebar filter
    _labs_map = sorted(all_samples['lab_name'].dropna().astype(str).unique().tolist()) if 'lab_name' in all_samples.columns else []
    if _labs_map:
        st.sidebar.markdown("### Map Filters")
        _lab_opts_map = ["All"] + _labs_map
        _sel_lab_opts_map = st.sidebar.multiselect("Sentinel Site / Lab (Map)", _lab_opts_map, default=["All"])
        if "All" not in _sel_lab_opts_map and _sel_lab_opts_map:
            all_samples = all_samples[all_samples['lab_name'].astype(str).isin(_sel_lab_opts_map)]
            all_ast = all_ast[all_ast['sample_id'].astype(str).isin(all_samples['sample_id'].astype(str))]

    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # Check if geographic data exists
        samples_with_coords = all_samples[
            all_samples['latitude'].notna() & 
            all_samples['longitude'].notna()
        ]
        has_coords = len(samples_with_coords) > 0
        
        if has_coords:
            # Enhanced Interactive Folium Map
            st.subheader("📍 Interactive Ghana Map - Resistance Hotspots")
            st.markdown(f"**{len(samples_with_coords)}** samples with geographic coordinates | Interactive map below")
            
            try:
                # Import the enhanced mapping module
                from src import ghana_map
                from streamlit_folium import folium_static
                
                # Create and display interactive Folium map
                m = ghana_map.create_interactive_ghana_map(samples_with_coords, all_ast)
                
                # Display using folium_static with full width
                folium_static(m, width=1200, height=600)
                
                # Map instructions
                with st.expander("📚 How to Use the Interactive Map", expanded=False):
                    st.markdown("""
                    **Data Point Display:**
                    - Each colored circle represents a sample location
                    - Circle size = number of tests from that location
                    - Circle color = resistance rate:
                      - **Red**: High resistance (>50%)
                      - **Orange**: Medium resistance (30-50%)
                      - **Green**: Low resistance (<30%)
                    
                    **How to Interact:**
                    - **Hover** over circles to see detailed information
                    - **Click** on circles for popup with detailed data
                    - **Drag** to pan around the map
                    - **Scroll** to zoom in/out
                    - **Double-click** to zoom to location
                    """)
                
            except Exception as e:
                st.warning(f"Map rendering issue: {str(e)}")
                st.info("Displaying data in tabular format...")
                
                # Fallback display: Show data as table
                display_cols = ['sample_id', 'district', 'region', 'latitude', 'longitude']
                available_cols = [col for col in display_cols if col in samples_with_coords.columns]
                
                if available_cols:
                    st.dataframe(
                        samples_with_coords[available_cols].head(50),
                        use_container_width=True
                    )
                    st.caption(f"Showing first 50 of {len(samples_with_coords)} samples")
            
            st.markdown("---")
        else:
            st.info("📍 No geographic coordinates in uploaded data. Add latitude/longitude to samples sheet to enable location mapping.")
        
        # Regional Analysis
        st.subheader("Resistance by Region")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.plotly_chart(
                plots.plot_resistance_by_region(all_ast, all_samples),
                use_container_width=True
            )
        
        with col2:
            st.plotly_chart(
                plots.plot_resistance_percentage_by_region(all_ast, all_samples),
                use_container_width=True
            )
        
        st.markdown("---")
        
        # District-level Analysis
        st.subheader("District-Level Resistance Hotspots")
        
        # Detailed district analysis
        st.plotly_chart(
            plots.plot_resistance_by_district_detailed(all_ast, all_samples, top_n=15),
            use_container_width=True
        )
        
        st.markdown("---")
        
        # Top districts table
        st.subheader("Top Districts Summary Table")
        
        top_districts = plots.get_resistance_by_district_detailed(all_ast, all_samples)
        
        if not top_districts.empty:
            st.dataframe(
                top_districts[['district', 'region', 'total_tests', 'susceptible', 'intermediate', 'resistant', 'percent_resistant']],
                use_container_width=True,
                height=500
            )
        else:
            st.info("No district data available.")
        
        st.markdown("---")
        
        # Surveillance alerts
        st.subheader("Surveillance Alerts & Warnings")
        
        alerts = plots.get_surveillance_alerts(all_ast, all_samples)
        
        if alerts:
            for alert in alerts:
                if alert['severity'] == 'HIGH':
                    st.error(f"**{alert['severity']}**: {alert['message']}")
                elif alert['severity'] == 'MEDIUM':
                    st.warning(f"**{alert['severity']}**: {alert['message']}")
                else:
                    st.info(f"**{alert['severity']}**: {alert['message']}")
        else:
            st.success("No critical alerts detected")



# ============================================================================
# PAGE 6: ADVANCED ANALYTICS
# ============================================================================
elif page == "Advanced Analytics":
    st.header("Advanced Analytics & Insights")
    
    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")

    # Sentinel Site / Lab sidebar filter
    _labs_aa = sorted(all_samples['lab_name'].dropna().astype(str).unique().tolist()) if 'lab_name' in all_samples.columns else []
    if _labs_aa:
        st.sidebar.markdown("### Analytics Filters")
        _lab_opts_aa = ["All"] + _labs_aa
        _sel_lab_opts_aa = st.sidebar.multiselect("Sentinel Site / Lab (Analytics)", _lab_opts_aa, default=["All"])
        if "All" not in _sel_lab_opts_aa and _sel_lab_opts_aa:
            all_samples = all_samples[all_samples['lab_name'].astype(str).isin(_sel_lab_opts_aa)]
            all_ast = all_ast[all_ast['sample_id'].astype(str).isin(all_samples['sample_id'].astype(str))]

    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # Tab selection
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Statistics", 
            "Trends & Forecasts", 
            "Emerging Patterns",
            "Antibiotic Insights",
            "Data Quality"
        ])
        
        # TAB 1: STATISTICS
        with tab1:
            st.subheader("Comprehensive Resistance Statistics")
            
            col1, col2, col3 = st.columns(3)
            
            # Overall stats
            stats = analytics.calculate_resistance_statistics(all_ast)
            
            with col1:
                st.metric("Resistance Rate", f"{stats.get('resistance_rate', 0):.1f}%")
            with col2:
                st.metric("Tests Analyzed", stats.get('total_tests', 0))
            with col3:
                st.metric("Organisms", all_ast['organism'].nunique())
            
            # Detailed breakdown
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.info(f"**Susceptible**: {stats.get('susceptible_count', 0)} ({stats.get('susceptible_rate', 0):.1f}%)")
            with col2:
                st.warning(f"**Intermediate**: {stats.get('intermediate_count', 0)} ({stats.get('intermediate_rate', 0):.1f}%)")
            with col3:
                st.error(f"**Resistant**: {stats.get('resistant_count', 0)} ({stats.get('resistance_rate', 0):.1f}%)")
            
            st.markdown("---")
            
            # Trend direction
            st.subheader("Trend Analysis")
            trend_info = analytics.calculate_trend_direction(all_ast)
            
            if trend_info:
                col1, col2 = st.columns(2)
                
                with col1:
                    trend = trend_info.get('trend', 'stable').upper()
                    risk = trend_info.get('risk_level', 'LOW')
                    
                    if trend == 'INCREASING':
                        st.error(f"**{trend}** - Risk: {risk}")
                    elif trend == 'DECREASING':
                        st.success(f"**{trend}** - Risk: {risk}")
                    else:
                        st.info(f"**{trend}** - Risk: {risk}")
                
                with col2:
                    st.metric(
                        "Change in Resistance",
                        f"{trend_info.get('change_percentage', 0):.2f}%",
                        delta=f"{trend_info.get('change_percentage', 0):.2f}%"
                    )
            
            st.markdown("---")
            
            # Organism comparison
            st.subheader("Organism Resistance Comparison")
            org_comparison = analytics.compare_organisms(all_ast)
            if not org_comparison.empty:
                st.dataframe(org_comparison, use_container_width=True)
            
            st.markdown("---")
            
            # Antibiotic comparison
            st.subheader("Antibiotic Efficacy Comparison")
            abx_comparison = analytics.compare_antibiotics(all_ast)
            if not abx_comparison.empty:
                st.dataframe(abx_comparison, use_container_width=True)
        
        # TAB 2: TRENDS & FORECASTS
        with tab2:
            st.subheader("Resistance Trends & Forecasting")
            
            col1, col2 = st.columns(2)
            
            with col1:
                forecast_periods = st.slider("Forecast Periods (months)", 1, 12, 3)
            
            with col2:
                st.empty()
            
            # Forecast
            forecast = analytics.forecast_resistance_trend(all_ast, forecast_periods)
            
            if 'forecasts' in forecast:
                st.info(f"Trend: {forecast['forecasts'][0]['trend'].upper()}")
                
                forecast_df = pd.DataFrame(forecast['forecasts'])
                st.dataframe(forecast_df, use_container_width=True)
                
                # Visualization
                fig = px.line(
                    forecast_df,
                    x='months_ahead',
                    y='predicted_resistance_rate',
                    markers=True,
                    title='Forecasted Resistance Rate',
                    labels={'months_ahead': 'Months Ahead', 'predicted_resistance_rate': 'Predicted Resistance %'}
                )
                st.plotly_chart(fig, use_container_width=True)
            elif 'error' in forecast:
                st.warning(f"{forecast['error']}")
        
        # TAB 3: EMERGING PATTERNS
        with tab3:
            st.subheader("Emerging Resistance Patterns")
            
            emerging = analytics.identify_emerging_resistance(all_ast, all_samples)
            
            if emerging:
                emerging_df = pd.DataFrame(emerging)
                st.dataframe(emerging_df, use_container_width=True)
                
                st.warning(f"🚨 {len(emerging)} emerging resistance patterns detected in the last 3 months")
            else:
                st.success("No concerning emerging patterns detected")
        
        # TAB 4: ANTIBIOTIC INSIGHTS
        with tab4:
            st.subheader("Antibiotic Recommendations")
            
            recommendations = analytics.generate_antibiotic_recommendations(all_ast)
            
            if recommendations:
                # Priority breakdown
                col1, col2, col3, col4 = st.columns(4)
                
                preferred = len([r for r in recommendations if r['priority'] == 1])
                good = len([r for r in recommendations if r['priority'] == 2])
                caution = len([r for r in recommendations if r['priority'] == 3])
                avoid = len([r for r in recommendations if r['priority'] == 4])
                
                with col1:
                    st.success(f"**Preferred**: {preferred}")
                with col2:
                    st.info(f"**Good**: {good}")
                with col3:
                    st.warning(f"**Caution**: {caution}")
                with col4:
                    st.error(f"**Avoid**: {avoid}")
                
                st.markdown("---")
                
                # Detailed recommendations
                rec_df = pd.DataFrame(recommendations).sort_values('priority')
                st.dataframe(rec_df, use_container_width=True)
        
        # TAB 5: DATA QUALITY
        with tab5:
            st.subheader("Surveillance System Quality Metrics")
            
            quality = analytics.assess_data_quality(all_samples, all_ast)
            kpis = analytics.calculate_kpis(all_samples, all_ast)
            
            if quality:
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Samples", quality.get('total_samples', 0))
                with col2:
                    st.metric("Total Tests", quality.get('total_tests', 0))
                with col3:
                    st.metric("Completeness", f"{quality.get('completeness_score', 0):.1f}%")
                with col4:
                    st.metric("Geographic Coverage", f"{quality.get('samples_with_coordinates', 0)} samples")
                
                st.markdown("---")
                
                if quality.get('data_quality_issues'):
                    st.warning("**Data Quality Issues Detected:**")
                    for issue in quality['data_quality_issues']:
                        st.warning(f"• {issue}")
                else:
                    st.success("No data quality issues detected")
                
                st.markdown("---")
                
                # KPIs
                st.subheader("Key Performance Indicators")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Tests/Sample", kpis.get('tests_per_sample', 0))
                with col2:
                    st.metric("Organisms ID'd", kpis.get('organisms_identified', 0))
                with col3:
                    st.metric("Antibiotics Tested", kpis.get('antibiotics_tested', 0))


# ============================================================================
# PAGE 7: RISK ASSESSMENT
# ============================================================================
elif page == "Risk Assessment":
    st.header("Risk Assessment & Alerts")
    
    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")

    # Sentinel Site / Lab sidebar filter
    _labs_risk = sorted(all_samples['lab_name'].dropna().astype(str).unique().tolist()) if 'lab_name' in all_samples.columns else []
    if _labs_risk:
        st.sidebar.markdown("### Risk Filters")
        _lab_opts_risk = ["All"] + _labs_risk
        _sel_lab_opts_risk = st.sidebar.multiselect("Sentinel Site / Lab (Risk)", _lab_opts_risk, default=["All"])
        if "All" not in _sel_lab_opts_risk and _sel_lab_opts_risk:
            all_samples = all_samples[all_samples['lab_name'].astype(str).isin(_sel_lab_opts_risk)]
            all_ast = all_ast[all_ast['sample_id'].astype(str).isin(all_samples['sample_id'].astype(str))]

    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # Tabs
        tab1, tab2 = st.tabs(["Risk Scores", "Resistance Burden"])
        
        # TAB 1: ORGANISM RISK SCORES
        with tab1:
            st.subheader("Organism Risk Scores")
            
            # Risk threshold slider
            risk_threshold = st.slider("Show organisms with resistance rate ≥", 0, 100, 50, step=1)
            
            high_risk = analytics.get_high_risk_organisms(all_ast, risk_threshold)
            
            if high_risk:
                for risk_item in high_risk:
                    with st.expander(f"{risk_item['organism']} - Risk: {risk_item['risk_level']} ({risk_item['risk_score']}/100)"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Risk Score", risk_item['risk_score'])
                        with col2:
                            st.metric("Resistance Rate", f"{risk_item['resistance_rate']:.1f}%")
                        with col3:
                            st.metric("Tests", risk_item['test_count'])
                        
                        st.markdown("**Risk Factors:**")
                        for factor in risk_item['risk_factors']:
                            st.write(f"• {factor}")
                        
                        # Recommendation
                        if risk_item['risk_level'] == 'CRITICAL':
                            st.error("**Urgent intervention required** - Consider alternative treatment options")
                        elif risk_item['risk_level'] == 'HIGH':
                            st.warning("**Enhanced surveillance** - Monitor trends closely")
                        else:
                            st.info("**Monitor** - Continue standard surveillance")
            else:
                st.success(f"No organisms above risk threshold ({risk_threshold})")

            # Detailed single-organism assessment
            st.markdown("---")
            st.subheader("Detailed Organism Assessment")
            organisms = sorted(all_ast['organism'].dropna().astype(str).unique().tolist())
            if organisms:
                selected_org = st.selectbox("Select Organism for Detail", organisms, key="risk_org_detail")
                if selected_org:
                    org_risk = analytics.calculate_organism_risk_score(all_ast, selected_org)
                    if org_risk:
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Risk Score", org_risk['risk_score'])
                        with col2:
                            st.metric("Risk Level", org_risk['risk_level'])
                        with col3:
                            st.metric("Resistance Rate", f"{org_risk['resistance_rate']:.1f}%")
                        with col4:
                            st.metric("Tests", org_risk['test_count'])
                        st.markdown("**Risk Factors:**")
                        for factor in org_risk['risk_factors']:
                            st.write(f"• {factor}")
                        if org_risk['risk_level'] == 'CRITICAL':
                            st.error("**CRITICAL** — Implement enhanced infection control, review treatment guidelines, consider alternative antimicrobials, report to national health authorities.")
                        elif org_risk['risk_level'] == 'HIGH':
                            st.warning("**HIGH** — Increase surveillance frequency, review empiric treatment protocols, consider antimicrobial stewardship interventions.")
                        else:
                            st.info("**MODERATE/LOW** — Continue routine surveillance, monitor for changes in resistance patterns.")
        
        # TAB 2: RESISTANCE BURDEN
        with tab2:
            st.subheader("Overall Resistance Burden")
            
            burden = analytics.calculate_resistance_burden(all_samples, all_ast)
            
            if burden:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total Resistant Tests", burden.get('total_resistant_tests', 0))
                with col2:
                    st.metric("Overall Resistance Rate", f"{burden.get('overall_resistance_rate', 0):.1f}%")
                with col3:
                    st.metric("Total Tests", burden.get('total_tests', 0))
                
                st.markdown("---")
                
                # Public health impact
                impact = burden.get('public_health_impact', '')
                if 'CRITICAL' in impact:
                    st.error(f"{impact}")
                elif 'HIGH' in impact:
                    st.warning(f"{impact}")
                else:
                    st.info(f"{impact}")
                
                st.markdown("---")
                
                # By category
                if burden.get('resistance_by_category'):
                    st.subheader("Resistance by Source Category")
                    
                    category_data = pd.DataFrame(
                        list(burden['resistance_by_category'].items()),
                        columns=['Category', 'Resistance Rate (%)']
                    )
                    
                    fig = px.bar(
                        category_data,
                        x='Category',
                        y='Resistance Rate (%)',
                        color='Resistance Rate (%)',
                        color_continuous_scale='RdYlGn_r',
                        title='Resistance Burden by Source Category'
                    )
                    st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# PAGE 8: COMPARATIVE ANALYSIS
# ============================================================================
elif page == "Comparative Analysis":
    st.header("Comparative Analysis")
    st.markdown("Compare resistance patterns across different categories, time periods, and sources")

    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")

    # Sentinel Site / Lab sidebar filter
    _labs_comp = sorted(all_samples['lab_name'].dropna().astype(str).unique().tolist()) if 'lab_name' in all_samples.columns else []
    if _labs_comp:
        st.sidebar.markdown("### Comparison Filters")
        _lab_opts_comp = ["All"] + _labs_comp
        _sel_lab_opts_comp = st.sidebar.multiselect("Sentinel Site / Lab (Comparison)", _lab_opts_comp, default=["All"])
        if "All" not in _sel_lab_opts_comp and _sel_lab_opts_comp:
            all_samples = all_samples[all_samples['lab_name'].astype(str).isin(_sel_lab_opts_comp)]
            all_ast = all_ast[all_ast['sample_id'].astype(str).isin(all_samples['sample_id'].astype(str))]

    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # Analysis type selection
        analysis_type = st.selectbox(
            "Select Comparison Type",
            ["Category Comparison", "Time Period Comparison", "Source Type Comparison", "Multi-Parameter Comparison", "Cross-Variable Comparison", "Custom Comparison"],
            key="comparison_type"
        )

        st.markdown("---")

        if analysis_type == "Category Comparison":
            st.subheader("Category Comparison")

            # Get available categories
            available_categories = sorted(all_samples['source_category'].dropna().unique())

            if len(available_categories) >= 2:
                col1, col2 = st.columns(2)

                with col1:
                    category_a = st.selectbox(
                        "Select First Category",
                        available_categories,
                        index=0 if len(available_categories) > 0 else None,
                        key="category_a"
                    )

                with col2:
                    # Filter out the selected category A from options for category B
                    remaining_categories = [cat for cat in available_categories if cat != category_a]
                    category_b = st.selectbox(
                        "Select Second Category",
                        remaining_categories,
                        index=0 if len(remaining_categories) > 0 else None,
                        key="category_b"
                    )

                if st.button("Compare Categories", key="compare_categories"):
                    # Get data for each selected category
                    cat_a_samples = all_samples[all_samples['source_category'] == category_a]
                    cat_b_samples = all_samples[all_samples['source_category'] == category_b]

                    cat_a_ast = all_ast[all_ast['sample_id'].isin(cat_a_samples['sample_id'])]
                    cat_b_ast = all_ast[all_ast['sample_id'].isin(cat_b_samples['sample_id'])]

                    if not cat_a_ast.empty and not cat_b_ast.empty:
                        # Create comparison metrics
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            cat_a_resistance = (cat_a_ast['result'] == 'R').sum() / len(cat_a_ast) * 100
                            st.metric(f"{category_a} Resistance Rate", f"{cat_a_resistance:.1f}%", delta=f"{(cat_a_ast['result'] == 'R').sum()}/{len(cat_a_ast)}")

                        with col2:
                            cat_b_resistance = (cat_b_ast['result'] == 'R').sum() / len(cat_b_ast) * 100
                            st.metric(f"{category_b} Resistance Rate", f"{cat_b_resistance:.1f}%", delta=f"{(cat_b_ast['result'] == 'R').sum()}/{len(cat_b_ast)}")

                        with col3:
                            diff = cat_a_resistance - cat_b_resistance
                            st.metric(f"Difference ({category_a} - {category_b})", f"{diff:+.1f}%")

                        # Side-by-side charts
                        st.markdown("### Resistance Distribution Comparison")

                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown(f"**{category_a} Sources**")
                            try:
                                cat_a_fig = plots.plot_resistance_distribution(cat_a_ast)
                                st.plotly_chart(cat_a_fig, use_container_width=True)
                            except Exception as e:
                                st.warning(f"Unable to generate {category_a} sources chart: {str(e)}")

                        with col2:
                            st.markdown(f"**{category_b} Sources**")
                            try:
                                cat_b_fig = plots.plot_resistance_distribution(cat_b_ast)
                                st.plotly_chart(cat_b_fig, use_container_width=True)
                            except Exception as e:
                                st.warning(f"Unable to generate {category_b} sources chart: {str(e)}")

                        # Top antibiotics comparison
                        st.markdown("### Top Antibiotics Comparison")

                        try:
                            cat_a_top = plots.get_antibiotic_resistance_rates(cat_a_ast)
                            cat_b_top = plots.get_antibiotic_resistance_rates(cat_b_ast)

                            if not cat_a_top.empty and not cat_b_top.empty:
                                # Create comparison chart
                                comparison_data = []

                                # Get top 10 antibiotics from both
                                all_antibiotics = set(cat_a_top.head(10)['antibiotic']) | set(cat_b_top.head(10)['antibiotic'])

                                for antibiotic in all_antibiotics:
                                    cat_a_rate = cat_a_top.loc[cat_a_top['antibiotic'] == antibiotic, 'resistance_rate'].iloc[0] if antibiotic in cat_a_top['antibiotic'].values else 0
                                    cat_b_rate = cat_b_top.loc[cat_b_top['antibiotic'] == antibiotic, 'resistance_rate'].iloc[0] if antibiotic in cat_b_top['antibiotic'].values else 0

                                    comparison_data.append({
                                        'Antibiotic': antibiotic,
                                        category_a: cat_a_rate,
                                        category_b: cat_b_rate
                                    })

                                comparison_df = pd.DataFrame(comparison_data)

                                fig = px.bar(comparison_df, x='Antibiotic', y=[category_a, category_b],
                                           title=f'Antibiotic Resistance: {category_a} vs {category_b}',
                                           barmode='group', color_discrete_sequence=['#FF6B6B', '#4ECDC4'])
                                fig.update_layout(xaxis_tickangle=-45)
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("No antibiotic resistance data available for comparison.")
                        except Exception as e:
                            st.warning(f"Unable to generate antibiotic comparison: {str(e)}")

                    else:
                        st.warning(f"Insufficient data for {category_a} vs {category_b} comparison. Need both categories to have AST results.")
            else:
                st.warning("Need data from at least 2 categories for comparison.")

        elif analysis_type == "Time Period Comparison":
            st.subheader("📅 Time Period Comparison")

            if 'test_date' in all_ast.columns:
                # Get date range
                dates = pd.to_datetime(all_ast['test_date'].dropna())
                min_date = dates.min()
                max_date = dates.max()

                col1, col2 = st.columns(2)

                with col1:
                    period1 = st.date_input("First Period Start-End", value=(min_date, min_date + (max_date - min_date)/2), key="period1")
                    if len(period1) == 2:
                        period1_start, period1_end = period1

                with col2:
                    period2 = st.date_input("Second Period Start-End", value=(min_date + (max_date - min_date)/2, max_date), key="period2")
                    if len(period2) == 2:
                        period2_start, period2_end = period2

                if st.button("Compare Periods", key="compare_periods"):
                    # Filter data for each period
                    period1_data = all_ast[
                        (pd.to_datetime(all_ast['test_date']) >= pd.Timestamp(period1_start)) &
                        (pd.to_datetime(all_ast['test_date']) <= pd.Timestamp(period1_end))
                    ]

                    period2_data = all_ast[
                        (pd.to_datetime(all_ast['test_date']) >= pd.Timestamp(period2_start)) &
                        (pd.to_datetime(all_ast['test_date']) <= pd.Timestamp(period2_end))
                    ]

                    if not period1_data.empty and not period2_data.empty:
                        # Comparison metrics
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            p1_resistance = (period1_data['result'] == 'R').sum() / len(period1_data) * 100
                            st.metric(f"Period 1 Resistance ({period1_start.strftime('%Y-%m')})", f"{p1_resistance:.1f}%")

                        with col2:
                            p2_resistance = (period2_data['result'] == 'R').sum() / len(period2_data) * 100
                            st.metric(f"Period 2 Resistance ({period2_start.strftime('%Y-%m')})", f"{p2_resistance:.1f}%")

                        with col3:
                            diff = p2_resistance - p1_resistance
                            trend = "Increasing" if diff > 0 else "Decreasing" if diff < 0 else "Stable"
                            st.metric("Trend", f"{diff:+.1f}%", trend)

                        # Trend visualization
                        trend_data = pd.DataFrame({
                            'Period': [f"{period1_start.strftime('%Y-%m')}", f"{period2_start.strftime('%Y-%m')}"],
                            'Resistance_Rate': [p1_resistance, p2_resistance]
                        })

                        fig = px.line(trend_data, x='Period', y='Resistance_Rate',
                                    title='Resistance Trend Over Time',
                                    markers=True, color_discrete_sequence=['#FF6B6B'])
                        fig.update_layout(yaxis_title='Resistance Rate (%)')
                        st.plotly_chart(fig, use_container_width=True)

                        # Organism comparison
                        st.markdown("### Organism Resistance Changes")

                        p1_org = period1_data.groupby('organism').agg({
                            'result': lambda x: (x == 'R').sum() / len(x) * 100
                        }).round(1)

                        p2_org = period2_data.groupby('organism').agg({
                            'result': lambda x: (x == 'R').sum() / len(x) * 100
                        }).round(1)

                        # Find organisms present in both periods
                        common_orgs = set(p1_org.index) & set(p2_org.index)

                        if common_orgs:
                            comparison_org = []
                            for org in common_orgs:
                                comparison_org.append({
                                    'Organism': org,
                                    'Period_1': p1_org.loc[org, 'result'],
                                    'Period_2': p2_org.loc[org, 'result'],
                                    'Change': p2_org.loc[org, 'result'] - p1_org.loc[org, 'result']
                                })

                            org_comparison = pd.DataFrame(comparison_org).sort_values('Change', key=abs, ascending=False)

                            fig = px.bar(org_comparison.head(10), x='Organism', y='Change',
                                       title='Organism Resistance Changes (Period 2 - Period 1)',
                                       color='Change',
                                       color_continuous_scale=['green', 'red'])
                            fig.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("One or both periods have no data. Please adjust the date ranges.")
            else:
                st.warning("Date information not available for time period comparison.")

        elif analysis_type == "Source Type Comparison":
            st.subheader("🏭 Source Type Comparison")

            source_types = sorted(all_samples['source_type'].dropna().unique())
            if len(source_types) > 1:
                selected_sources = st.multiselect(
                    "Select Source Types to Compare",
                    source_types,
                    default=source_types[:3] if len(source_types) >= 3 else source_types,
                    key="source_comparison"
                )

                if len(selected_sources) >= 2 and st.button("Compare Sources", key="compare_sources"):
                    # Similar logic to regional comparison but for source types
                    source_data = {}

                    for source in selected_sources:
                        source_samples = all_samples[all_samples['source_type'] == source]
                        source_ast = all_ast[all_ast['sample_id'].isin(source_samples['sample_id'])]

                        if not source_ast.empty:
                            resistance_rate = (source_ast['result'] == 'R').sum() / len(source_ast) * 100
                            source_data[source] = {
                                'resistance_rate': resistance_rate,
                                'total_tests': len(source_ast),
                                'resistant_count': (source_ast['result'] == 'R').sum(),
                                'data': source_ast
                            }

                    if len(source_data) >= 2:
                        # Create comparison table
                        comparison_table = []
                        for source, data in source_data.items():
                            comparison_table.append({
                                'Source Type': source,
                                'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                'Total Tests': data['total_tests'],
                                'Resistant Isolates': data['resistant_count']
                            })

                        st.dataframe(pd.DataFrame(comparison_table))

                        # Resistance rate comparison chart
                        fig = px.bar(
                            pd.DataFrame(comparison_table),
                            x='Source Type',
                            y='Resistance Rate (%)',
                            title='Source Type Resistance Comparison',
                            color='Resistance Rate (%)',
                            color_continuous_scale='Blues'
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Need data from at least 2 source types for comparison.")
                else:
                    st.info("Select at least 2 source types to compare.")
            else:
                st.warning("Need data from multiple source types for comparison.")

        elif analysis_type == "Multi-Parameter Comparison":
            st.subheader("Multi-Parameter Comparison")
            st.markdown("Compare resistance patterns across multiple values of a single parameter (e.g., multiple regions, organisms, or antibiotics)")

            # Parameter selection
            parameter_type = st.selectbox(
                "Select Parameter to Compare",
                ["Regions", "Organisms", "Antibiotics", "Categories", "Source Types"],
                key="multi_param_type"
            )

            st.markdown("---")

            if parameter_type == "Regions":
                regions = sorted(all_samples['region'].dropna().unique())
                if len(regions) >= 2:
                    selected_items = st.multiselect(
                        "Select Regions to Compare",
                        regions,
                        default=regions[:min(5, len(regions))],
                        key="multi_regions"
                    )

                    if len(selected_items) >= 2 and st.button("Compare Multiple Regions", key="multi_region_compare"):
                        comparison_data = {}
                        
                        for region in selected_items:
                            region_samples = all_samples[all_samples['region'] == region]
                            region_ast = all_ast[all_ast['sample_id'].isin(region_samples['sample_id'])]
                            
                            if not region_ast.empty:
                                resistance_rate = (region_ast['result'] == 'R').sum() / len(region_ast) * 100
                                comparison_data[region] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(region_ast),
                                    'resistant_count': (region_ast['result'] == 'R').sum(),
                                    'susceptible_count': (region_ast['result'] == 'S').sum(),
                                    'intermediate_count': (region_ast['result'] == 'I').sum(),
                                    'data': region_ast
                                }
                        
                        if comparison_data:
                            # Create comparison table
                            comp_table = pd.DataFrame([
                                {
                                    'Parameter': param,
                                    'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                    'Total Tests': data['total_tests'],
                                    'Resistant': data['resistant_count'],
                                    'Susceptible': data['susceptible_count'],
                                    'Intermediate': data['intermediate_count']
                                }
                                for param, data in comparison_data.items()
                            ]).sort_values('Resistance Rate (%)', ascending=False)
                            
                            st.dataframe(comp_table, use_container_width=True)
                            
                            # Bar chart comparison
                            fig = px.bar(
                                comp_table,
                                x='Parameter',
                                y='Resistance Rate (%)',
                                title='Resistance Rate Comparison Across Regions',
                                color='Resistance Rate (%)',
                                color_continuous_scale='Reds',
                                text='Resistance Rate (%)'
                            )
                            fig.update_traces(textposition='outside')
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Result distribution
                            st.markdown("### Result Distribution by Region")
                            
                            result_data = []
                            for region, data in comparison_data.items():
                                total = data['total_tests']
                                result_data.append({
                                    'Region': region,
                                    'Resistant': (data['resistant_count'] / total * 100) if total > 0 else 0,
                                    'Susceptible': (data['susceptible_count'] / total * 100) if total > 0 else 0,
                                    'Intermediate': (data['intermediate_count'] / total * 100) if total > 0 else 0
                                })
                            
                            result_df = pd.DataFrame(result_data)
                            fig = px.bar(result_df, x='Region', y=['Resistant', 'Susceptible', 'Intermediate'],
                                       title='Result Distribution (%)',
                                       barmode='stack',
                                       color_discrete_map={'Resistant': '#FF6B6B', 'Susceptible': '#51CF66', 'Intermediate': '#FFD93D'})
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Top organisms comparison
                            st.markdown("### Top Organisms by Region")
                            
                            org_cols = st.columns(min(3, len(comparison_data)))
                            for idx, (region, data) in enumerate(list(comparison_data.items())[:3]):
                                with org_cols[idx]:
                                    st.markdown(f"**{region}**")
                                    org_data = data['data'].groupby('organism').agg({
                                        'result': lambda x: (x == 'R').sum() / len(x) * 100
                                    }).round(1).sort_values(by='result', ascending=False).head(5)
                                    org_data.columns = ['Resistance %']
                                    st.dataframe(org_data, use_container_width=True)
                else:
                    st.warning("Need data from at least 2 regions for comparison.")

            elif parameter_type == "Organisms":
                organisms = sorted(all_ast['organism'].dropna().unique())
                if len(organisms) >= 2:
                    selected_items = st.multiselect(
                        "Select Organisms to Compare",
                        organisms,
                        default=organisms[:min(5, len(organisms))],
                        key="multi_organisms"
                    )

                    if len(selected_items) >= 2 and st.button("Compare Multiple Organisms", key="multi_org_compare"):
                        comparison_data = {}
                        
                        for organism in selected_items:
                            org_ast = all_ast[all_ast['organism'] == organism]
                            
                            if not org_ast.empty:
                                resistance_rate = (org_ast['result'] == 'R').sum() / len(org_ast) * 100
                                comparison_data[organism] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(org_ast),
                                    'resistant_count': (org_ast['result'] == 'R').sum(),
                                    'susceptible_count': (org_ast['result'] == 'S').sum(),
                                    'intermediate_count': (org_ast['result'] == 'I').sum(),
                                    'data': org_ast
                                }
                        
                        if comparison_data:
                            # Create comparison table
                            comp_table = pd.DataFrame([
                                {
                                    'Organism': param,
                                    'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                    'Total Tests': data['total_tests'],
                                    'Resistant': data['resistant_count'],
                                    'Susceptible': data['susceptible_count'],
                                    'Intermediate': data['intermediate_count']
                                }
                                for param, data in comparison_data.items()
                            ]).sort_values('Resistance Rate (%)', ascending=False)
                            
                            st.dataframe(comp_table, use_container_width=True)
                            
                            # Bar chart comparison
                            fig = px.bar(
                                comp_table,
                                x='Organism',
                                y='Resistance Rate (%)',
                                title='Resistance Rate Comparison Across Organisms',
                                color='Resistance Rate (%)',
                                color_continuous_scale='Purples',
                                text='Resistance Rate (%)'
                            )
                            fig.update_traces(textposition='outside')
                            fig.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Top antibiotics comparison
                            st.markdown("### Top Antibiotics by Organism")
                            
                            org_cols = st.columns(min(3, len(comparison_data)))
                            for idx, (organism, data) in enumerate(list(comparison_data.items())[:3]):
                                with org_cols[idx]:
                                    st.markdown(f"**{organism}**")
                                    try:
                                        antibiotic_data = data['data'].groupby('antibiotic').agg({
                                            'result': lambda x: (x == 'R').sum() / len(x) * 100
                                        }).round(1).sort_values(by='result', ascending=False).head(5)
                                        antibiotic_data.columns = ['Resistance %']
                                        st.dataframe(antibiotic_data, use_container_width=True)
                                    except Exception as e:
                                        st.warning(f"Error processing {organism}: {str(e)}")
                else:
                    st.warning("Need data from at least 2 organisms for comparison.")

            elif parameter_type == "Antibiotics":
                antibiotics = sorted(all_ast['antibiotic'].dropna().unique())
                if len(antibiotics) >= 2:
                    selected_items = st.multiselect(
                        "Select Antibiotics to Compare",
                        antibiotics,
                        default=antibiotics[:min(8, len(antibiotics))],
                        key="multi_antibiotics"
                    )

                    if len(selected_items) >= 2 and st.button("Compare Multiple Antibiotics", key="multi_antibiotic_compare"):
                        comparison_data = {}
                        
                        for antibiotic in selected_items:
                            antibiotic_ast = all_ast[all_ast['antibiotic'] == antibiotic]
                            
                            if not antibiotic_ast.empty:
                                resistance_rate = (antibiotic_ast['result'] == 'R').sum() / len(antibiotic_ast) * 100
                                comparison_data[antibiotic] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(antibiotic_ast),
                                    'resistant_count': (antibiotic_ast['result'] == 'R').sum(),
                                    'susceptible_count': (antibiotic_ast['result'] == 'S').sum(),
                                    'intermediate_count': (antibiotic_ast['result'] == 'I').sum(),
                                    'data': antibiotic_ast
                                }
                        
                        if comparison_data:
                            # Create comparison table
                            comp_table = pd.DataFrame([
                                {
                                    'Antibiotic': param,
                                    'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                    'Total Tests': data['total_tests'],
                                    'Resistant': data['resistant_count'],
                                    'Susceptible': data['susceptible_count'],
                                    'Intermediate': data['intermediate_count']
                                }
                                for param, data in comparison_data.items()
                            ]).sort_values('Resistance Rate (%)', ascending=False)
                            
                            st.dataframe(comp_table, use_container_width=True)
                            
                            # Bar chart comparison
                            fig = px.bar(
                                comp_table,
                                x='Antibiotic',
                                y='Resistance Rate (%)',
                                title='Resistance Rate Comparison Across Antibiotics',
                                color='Resistance Rate (%)',
                                color_continuous_scale='Oranges',
                                text='Resistance Rate (%)'
                            )
                            fig.update_traces(textposition='outside')
                            fig.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Top organisms by antibiotic
                            st.markdown("### Top Organisms by Antibiotic")
                            
                            org_cols = st.columns(min(4, len(comparison_data)))
                            for idx, (antibiotic, data) in enumerate(list(comparison_data.items())[:4]):
                                with org_cols[idx]:
                                    st.markdown(f"**{antibiotic}**")
                                    try:
                                        org_data = data['data'].groupby('organism').agg({
                                            'result': lambda x: (x == 'R').sum() / len(x) * 100
                                        }).round(1).sort_values(by='result', ascending=False).head(5)
                                        org_data.columns = ['Resistance %']
                                        st.dataframe(org_data, use_container_width=True)
                                    except Exception as e:
                                        st.warning(f"Error processing {antibiotic}: {str(e)}")
                else:
                    st.warning("Need data from at least 2 antibiotics for comparison.")

            elif parameter_type == "Categories":
                categories = sorted(all_samples['source_category'].dropna().unique())
                if len(categories) >= 2:
                    selected_items = st.multiselect(
                        "Select Categories to Compare",
                        categories,
                        default=categories[:min(5, len(categories))],
                        key="multi_categories"
                    )

                    if len(selected_items) >= 2 and st.button("Compare Multiple Categories", key="multi_cat_compare"):
                        comparison_data = {}
                        
                        for category in selected_items:
                            cat_samples = all_samples[all_samples['source_category'] == category]
                            cat_ast = all_ast[all_ast['sample_id'].isin(cat_samples['sample_id'])]
                            
                            if not cat_ast.empty:
                                resistance_rate = (cat_ast['result'] == 'R').sum() / len(cat_ast) * 100
                                comparison_data[category] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(cat_ast),
                                    'resistant_count': (cat_ast['result'] == 'R').sum(),
                                    'susceptible_count': (cat_ast['result'] == 'S').sum(),
                                    'intermediate_count': (cat_ast['result'] == 'I').sum(),
                                    'data': cat_ast
                                }
                        
                        if comparison_data:
                            # Create comparison table
                            comp_table = pd.DataFrame([
                                {
                                    'Category': param,
                                    'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                    'Total Tests': data['total_tests'],
                                    'Resistant': data['resistant_count'],
                                    'Susceptible': data['susceptible_count'],
                                    'Intermediate': data['intermediate_count']
                                }
                                for param, data in comparison_data.items()
                            ]).sort_values('Resistance Rate (%)', ascending=False)
                            
                            st.dataframe(comp_table, use_container_width=True)
                            
                            # Bar chart comparison
                            fig = px.bar(
                                comp_table,
                                x='Category',
                                y='Resistance Rate (%)',
                                title='Resistance Rate Comparison Across Categories',
                                color='Resistance Rate (%)',
                                color_continuous_scale='Greens',
                                text='Resistance Rate (%)'
                            )
                            fig.update_traces(textposition='outside')
                            st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Need data from at least 2 categories for comparison.")

            elif parameter_type == "Source Types":
                source_types = sorted(all_samples['source_type'].dropna().unique())
                if len(source_types) >= 2:
                    selected_items = st.multiselect(
                        "Select Source Types to Compare",
                        source_types,
                        default=source_types[:min(5, len(source_types))],
                        key="multi_sources"
                    )

                    if len(selected_items) >= 2 and st.button("Compare Multiple Source Types", key="multi_source_compare"):
                        comparison_data = {}
                        
                        for source_type in selected_items:
                            source_samples = all_samples[all_samples['source_type'] == source_type]
                            source_ast = all_ast[all_ast['sample_id'].isin(source_samples['sample_id'])]
                            
                            if not source_ast.empty:
                                resistance_rate = (source_ast['result'] == 'R').sum() / len(source_ast) * 100
                                comparison_data[source_type] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(source_ast),
                                    'resistant_count': (source_ast['result'] == 'R').sum(),
                                    'susceptible_count': (source_ast['result'] == 'S').sum(),
                                    'intermediate_count': (source_ast['result'] == 'I').sum(),
                                    'data': source_ast
                                }
                        
                        if comparison_data:
                            # Create comparison table
                            comp_table = pd.DataFrame([
                                {
                                    'Source Type': param,
                                    'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                    'Total Tests': data['total_tests'],
                                    'Resistant': data['resistant_count'],
                                    'Susceptible': data['susceptible_count'],
                                    'Intermediate': data['intermediate_count']
                                }
                                for param, data in comparison_data.items()
                            ]).sort_values('Resistance Rate (%)', ascending=False)
                            
                            st.dataframe(comp_table, use_container_width=True)
                            
                            # Bar chart comparison
                            fig = px.bar(
                                comp_table,
                                x='Source Type',
                                y='Resistance Rate (%)',
                                title='Resistance Rate Comparison Across Source Types',
                                color='Resistance Rate (%)',
                                color_continuous_scale='Blues',
                                text='Resistance Rate (%)'
                            )
                            fig.update_traces(textposition='outside')
                            fig.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Need data from at least 2 source types for comparison.")

        elif analysis_type == "Cross-Variable Comparison":
            st.subheader("Cross-Variable Comparison")
            st.markdown("Compare a specific organism-antibiotic combination across different variables (regions, source types, categories, etc.)")

            st.markdown("---")

            # Step 1: Select organism and antibiotic
            col1, col2 = st.columns(2)

            organisms = sorted(all_ast['organism'].dropna().unique())
            antibiotics = sorted(all_ast['antibiotic'].dropna().unique())

            with col1:
                selected_organism = st.selectbox(
                    "Select Organism",
                    organisms,
                    key="cross_organism"
                )

            with col2:
                selected_antibiotic = st.selectbox(
                    "Select Antibiotic",
                    antibiotics,
                    key="cross_antibiotic"
                )

            st.markdown("---")

            # Step 2: Select variable to compare across
            comparison_variable = st.selectbox(
                "Compare This Combination Across:",
                ["Regions", "Districts", "Source Types", "Categories", "Sources", "Time Periods"],
                key="cross_variable"
            )

            st.markdown("---")

            if st.button("Compare Across Variable", key="cross_compare"):
                # Filter for the selected organism and antibiotic
                filtered_ast = all_ast[
                    (all_ast['organism'] == selected_organism) & 
                    (all_ast['antibiotic'] == selected_antibiotic)
                ]

                if filtered_ast.empty:
                    st.warning(f"No data found for {selected_organism} tested against {selected_antibiotic}")
                else:
                    # Merge with samples data to get location/source information
                    filtered_with_samples = filtered_ast.merge(
                        all_samples[['sample_id', 'region', 'district', 'source_type', 'source_category', 'collection_date']],
                        on='sample_id',
                        how='left'
                    )

                    comparison_data = {}

                    if comparison_variable == "Regions":
                        regions = sorted(filtered_with_samples['region'].dropna().unique())
                        
                        for region in regions:
                            region_data = filtered_with_samples[filtered_with_samples['region'] == region]
                            if not region_data.empty:
                                resistance_rate = (region_data['result'] == 'R').sum() / len(region_data) * 100
                                comparison_data[region] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(region_data),
                                    'resistant_count': (region_data['result'] == 'R').sum(),
                                    'susceptible_count': (region_data['result'] == 'S').sum(),
                                    'intermediate_count': (region_data['result'] == 'I').sum()
                                }

                    elif comparison_variable == "Districts":
                        districts = sorted(filtered_with_samples['district'].dropna().unique())
                        
                        for district in districts:
                            district_data = filtered_with_samples[filtered_with_samples['district'] == district]
                            if not district_data.empty:
                                resistance_rate = (district_data['result'] == 'R').sum() / len(district_data) * 100
                                comparison_data[district] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(district_data),
                                    'resistant_count': (district_data['result'] == 'R').sum(),
                                    'susceptible_count': (district_data['result'] == 'S').sum(),
                                    'intermediate_count': (district_data['result'] == 'I').sum()
                                }

                    elif comparison_variable == "Source Types":
                        source_types = sorted(filtered_with_samples['source_type'].dropna().unique())
                        
                        for source_type in source_types:
                            source_data = filtered_with_samples[filtered_with_samples['source_type'] == source_type]
                            if not source_data.empty:
                                resistance_rate = (source_data['result'] == 'R').sum() / len(source_data) * 100
                                comparison_data[source_type] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(source_data),
                                    'resistant_count': (source_data['result'] == 'R').sum(),
                                    'susceptible_count': (source_data['result'] == 'S').sum(),
                                    'intermediate_count': (source_data['result'] == 'I').sum()
                                }

                    elif comparison_variable == "Categories":
                        categories = sorted(filtered_with_samples['source_category'].dropna().unique())
                        
                        for category in categories:
                            cat_data = filtered_with_samples[filtered_with_samples['source_category'] == category]
                            if not cat_data.empty:
                                resistance_rate = (cat_data['result'] == 'R').sum() / len(cat_data) * 100
                                comparison_data[category] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(cat_data),
                                    'resistant_count': (cat_data['result'] == 'R').sum(),
                                    'susceptible_count': (cat_data['result'] == 'S').sum(),
                                    'intermediate_count': (cat_data['result'] == 'I').sum()
                                }

                    elif comparison_variable == "Sources":
                        sources = sorted(filtered_with_samples.get('source', filtered_with_samples.get('source_type', pd.Series(dtype='object'))).dropna().unique())
                        
                        for source in sources:
                            source_data = filtered_with_samples[filtered_with_samples.get('source', filtered_with_samples['source_type']) == source]
                            if not source_data.empty:
                                resistance_rate = (source_data['result'] == 'R').sum() / len(source_data) * 100
                                comparison_data[source] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(source_data),
                                    'resistant_count': (source_data['result'] == 'R').sum(),
                                    'susceptible_count': (source_data['result'] == 'S').sum(),
                                    'intermediate_count': (source_data['result'] == 'I').sum()
                                }

                    elif comparison_variable == "Time Periods":
                        filtered_with_samples['test_month'] = pd.to_datetime(filtered_with_samples.get('collection_date', filtered_with_samples.get('test_date', pd.Series(dtype='object')))).dt.to_period('M')
                        time_periods = sorted(filtered_with_samples['test_month'].dropna().unique())
                        
                        for period in time_periods:
                            period_data = filtered_with_samples[filtered_with_samples['test_month'] == period]
                            if not period_data.empty:
                                resistance_rate = (period_data['result'] == 'R').sum() / len(period_data) * 100
                                comparison_data[str(period)] = {
                                    'resistance_rate': resistance_rate,
                                    'total_tests': len(period_data),
                                    'resistant_count': (period_data['result'] == 'R').sum(),
                                    'susceptible_count': (period_data['result'] == 'S').sum(),
                                    'intermediate_count': (period_data['result'] == 'I').sum()
                                }

                    if comparison_data:
                        # Create summary header
                        st.markdown(f"### {selected_organism} vs {selected_antibiotic} - Across {comparison_variable}")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Tests (All)", len(filtered_ast))
                        with col2:
                            overall_resistance = (filtered_ast['result'] == 'R').sum() / len(filtered_ast) * 100
                            st.metric("Overall Resistance Rate", f"{overall_resistance:.1f}%")
                        with col3:
                            st.metric("Locations/Variables", len(comparison_data))

                        st.markdown("---")

                        # Create comparison table
                        comp_table = pd.DataFrame([
                            {
                                comparison_variable.rstrip('s'): param,
                                'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                'Total Tests': data['total_tests'],
                                'Resistant': data['resistant_count'],
                                'Susceptible': data['susceptible_count'],
                                'Intermediate': data['intermediate_count']
                            }
                            for param, data in comparison_data.items()
                        ]).sort_values('Resistance Rate (%)', ascending=False)

                        st.dataframe(comp_table, use_container_width=True)

                        st.markdown("---")

                        # Bar chart comparison
                        fig = px.bar(
                            comp_table,
                            x=comparison_variable.rstrip('s'),
                            y='Resistance Rate (%)',
                            title=f'{selected_organism} + {selected_antibiotic} Resistance Rate Across {comparison_variable}',
                            color='Resistance Rate (%)',
                            color_continuous_scale='RdYlGn_r',
                            text='Resistance Rate (%)',
                            height=500
                        )
                        fig.update_traces(textposition='outside')
                        fig.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig, use_container_width=True)

                        # Result distribution across variable
                        st.markdown(f"### Result Distribution by {comparison_variable}")

                        result_dist = []
                        for var, data in comparison_data.items():
                            total = data['total_tests']
                            result_dist.append({
                                comparison_variable.rstrip('s'): var,
                                'Resistant (%)': (data['resistant_count'] / total * 100) if total > 0 else 0,
                                'Susceptible (%)': (data['susceptible_count'] / total * 100) if total > 0 else 0,
                                'Intermediate (%)': (data['intermediate_count'] / total * 100) if total > 0 else 0
                            })

                        result_dist_df = pd.DataFrame(result_dist)
                        fig = px.bar(
                            result_dist_df,
                            x=comparison_variable.rstrip('s'),
                            y=['Resistant (%)', 'Susceptible (%)', 'Intermediate (%)'],
                            title=f'Result Distribution Across {comparison_variable}',
                            barmode='stack',
                            color_discrete_map={'Resistant (%)': '#FF6B6B', 'Susceptible (%)': '#51CF66', 'Intermediate (%)': '#FFD93D'},
                            height=500
                        )
                        fig.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig, use_container_width=True)

                        # Heatmap style visualization
                        st.markdown(f"### Heatmap: {selected_organism} + {selected_antibiotic} Resistance")
                        
                        heatmap_data = comp_table.set_index(comparison_variable.rstrip('s'))
                        heatmap_vals = heatmap_data[['Resistant', 'Susceptible', 'Intermediate']]
                        
                        fig = px.imshow(
                            heatmap_vals.T,
                            labels=dict(x=comparison_variable.rstrip('s'), y='Result', color='Count'),
                            title=f'Test Result Distribution Heatmap',
                            color_continuous_scale='Blues',
                            height=300
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    else:
                        st.warning(f"No data available for {selected_organism} vs {selected_antibiotic} across {comparison_variable}")

        elif analysis_type == "Custom Comparison":
            st.subheader("🎯 Custom Comparison")

            st.markdown("Create custom comparisons by selecting specific filter combinations:")

            # Custom filter setup
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Group A Filters:**")
                group_a_categories = st.multiselect(
                    "Categories (Group A)",
                    sorted(all_samples['source_category'].dropna().unique()),
                    key="group_a_cat"
                )
                group_a_regions = st.multiselect(
                    "Regions (Group A)",
                    sorted(all_samples['region'].dropna().unique()),
                    key="group_a_reg"
                )

            with col2:
                st.markdown("**Group B Filters:**")
                group_b_categories = st.multiselect(
                    "Categories (Group B)",
                    sorted(all_samples['source_category'].dropna().unique()),
                    key="group_b_cat"
                )
                group_b_regions = st.multiselect(
                    "Regions (Group B)",
                    sorted(all_samples['region'].dropna().unique()),
                    key="group_b_reg"
                )

            group_a_name = st.text_input("Group A Name", value="Group A", key="group_a_name")
            group_b_name = st.text_input("Group B Name", value="Group B", key="group_b_name")

            if st.button("Run Custom Comparison", key="custom_comparison"):
                # Apply filters for Group A
                group_a_samples = all_samples
                if group_a_categories:
                    group_a_samples = group_a_samples[group_a_samples['source_category'].isin(group_a_categories)]
                if group_a_regions:
                    group_a_samples = group_a_samples[group_a_samples['region'].isin(group_a_regions)]

                # Apply filters for Group B
                group_b_samples = all_samples
                if group_b_categories:
                    group_b_samples = group_b_samples[group_b_samples['source_category'].isin(group_b_categories)]
                if group_b_regions:
                    group_b_samples = group_b_samples[group_b_samples['region'].isin(group_b_regions)]

                # Get AST data
                group_a_ast = all_ast[all_ast['sample_id'].isin(group_a_samples['sample_id'])]
                group_b_ast = all_ast[all_ast['sample_id'].isin(group_b_samples['sample_id'])]

                if not group_a_ast.empty and not group_b_ast.empty:
                    # Comparison metrics
                    a_resistance = (group_a_ast['result'] == 'R').sum() / len(group_a_ast) * 100
                    b_resistance = (group_b_ast['result'] == 'R').sum() / len(group_b_ast) * 100

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric(f"{group_a_name} Resistance", f"{a_resistance:.1f}%")
                    with col2:
                        st.metric(f"{group_b_name} Resistance", f"{b_resistance:.1f}%")
                    with col3:
                        diff = b_resistance - a_resistance
                        st.metric("Difference", f"{diff:+.1f}%")

                    # Side-by-side charts
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**{group_a_name}**")
                        try:
                            a_fig = plots.plot_resistance_distribution(group_a_ast)
                            st.plotly_chart(a_fig, use_container_width=True)
                        except Exception as e:
                            st.warning(f"Unable to generate chart for {group_a_name}: {str(e)}")

                    with col2:
                        st.markdown(f"**{group_b_name}**")
                        try:
                            b_fig = plots.plot_resistance_distribution(group_b_ast)
                            st.plotly_chart(b_fig, use_container_width=True)
                        except Exception as e:
                            st.warning(f"Unable to generate chart for {group_b_name}: {str(e)}")

                else:
                    st.warning("One or both groups have no data. Please adjust your filters.")

# ============================================================================
# PAGE 9: ALERTS DASHBOARD
# ============================================================================
elif page == "Alerts Dashboard":
    st.header("Alerts Dashboard")
    
    # Require dataset selection
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    # Import alerts module
    from src.alerts import (
        generate_all_alerts, alerts_to_dataframe, get_alert_summary,
        AlertSeverity, AlertType
    )
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)
    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")
    
    if all_ast.empty:
        st.warning("No AST data available for alert generation.")
    else:
        # Alert Configuration
        with st.expander("Alert Configuration", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                critical_threshold = st.slider("Critical Threshold (%)", 50, 95, 80, 5)
            with col2:
                high_threshold = st.slider("High Threshold (%)", 30, 80, 60, 5)
            with col3:
                medium_threshold = st.slider("Medium Threshold (%)", 20, 60, 40, 5)
        
        # Build thresholds dict
        custom_thresholds = {
            'critical': critical_threshold,
            'high': high_threshold,
            'medium': medium_threshold
        }
        
        # Generate alerts
        with st.spinner("Analyzing data for alerts..."):
            alerts = generate_all_alerts(
                all_ast, 
                all_samples,
                thresholds=custom_thresholds
            )
        
        # Alert Summary Cards
        summary = get_alert_summary(alerts)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #ef4444, #dc2626); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 32px; font-weight: bold;">{summary['critical']}</div>
                <div>Critical Alerts</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #f97316, #ea580c); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 32px; font-weight: bold;">{summary['high']}</div>
                <div>High Priority</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #eab308, #ca8a04); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 32px; font-weight: bold;">{summary['medium']}</div>
                <div>Medium Priority</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #22c55e, #16a34a); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 32px; font-weight: bold;">{summary['low']}</div>
                <div>Low Priority</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        if alerts:
            # Filter alerts by type
            st.subheader("Alert Details")
            
            alert_type_filter = st.multiselect(
                "Filter by Alert Type",
                options=[t.value.replace('_', ' ').title() for t in AlertType],
                default=[t.value.replace('_', ' ').title() for t in AlertType]
            )
            
            severity_filter = st.multiselect(
                "Filter by Severity",
                options=[s.value.upper() for s in AlertSeverity],
                default=[s.value.upper() for s in AlertSeverity]
            )
            
            # Convert to dataframe for display
            alerts_df = alerts_to_dataframe(alerts)
            
            # Apply filters using correct column names
            filtered_alerts = alerts_df[
                (alerts_df['Type'].isin(alert_type_filter)) &
                (alerts_df['Severity'].isin(severity_filter))
            ]
            
            if not filtered_alerts.empty:
                # Display alerts
                for _, alert in filtered_alerts.iterrows():
                    severity_color = {
                        'CRITICAL': '#ef4444',
                        'HIGH': '#f97316',
                        'MEDIUM': '#eab308',
                        'LOW': '#22c55e'
                    }.get(alert['Severity'], '#64748b')
                    
                    with st.expander(f"{alert['Title']}", expanded=alert['Severity'] == 'CRITICAL'):
                        st.markdown(f"""
                        <div style="border-left: 4px solid {severity_color}; padding-left: 15px;">
                            <p><strong>Severity:</strong> <span style="color: {severity_color}; font-weight: bold;">{alert['Severity']}</span></p>
                            <p><strong>Type:</strong> {alert['Type']}</p>
                            <p><strong>Description:</strong> {alert['Description']}</p>
                            <p><strong>Detected:</strong> {alert['Created']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if alert['Organism'] != '-':
                            st.write(f"**Organism:** {alert['Organism']}")
                        if alert['Antibiotic'] != '-':
                            st.write(f"**Antibiotic:** {alert['Antibiotic']}")
                        if alert['Current Value'] != '-':
                            st.write(f"**Current Value:** {alert['Current Value']}")
            else:
                st.info("No alerts match the selected filters.")
        else:
            st.success("No alerts detected based on current thresholds. Your data looks good!")

# ============================================================================
# PAGE 10: ANTIBIOGRAM
# ============================================================================
elif page == "Antibiogram":
    st.header("Cumulative Antibiogram")
    
    # Require dataset selection
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    # Import antibiogram module
    from src.antibiogram import (
        generate_antibiogram, antibiogram_to_html, antibiogram_to_excel,
        generate_quarterly_antibiograms, compare_antibiograms,
        CLSI_MIN_ISOLATES
    )
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)
    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")
    
    if all_ast.empty:
        st.warning("No AST data available for antibiogram generation.")
    else:
        # Configuration
        st.subheader("Antibiogram Configuration")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            min_isolates = st.slider(
                "Minimum Isolates for Reporting",
                min_value=5, max_value=50, value=30, step=5,
                help=f"CLSI recommends minimum {CLSI_MIN_ISOLATES} isolates for cumulative antibiograms"
            )
        with col2:
            include_all = st.checkbox(
                "Include combinations below threshold",
                value=False,
                help="Show all combinations (marked with *) even if below minimum isolates"
            )
        with col3:
            lab_filter = st.selectbox(
                "Filter by Laboratory",
                options=["All Laboratories"] + sorted(all_samples['lab_name'].dropna().unique().tolist())
            )
        
        # Apply lab filter
        if lab_filter != "All Laboratories":
            filtered_samples = all_samples[all_samples['lab_name'] == lab_filter]
            filtered_ast = all_ast[all_ast['sample_id'].isin(filtered_samples['sample_id'])]
            lab_name = lab_filter
        else:
            filtered_ast = all_ast
            lab_name = "All Laboratories"
        
        # Generate antibiogram
        with st.spinner("Generating antibiogram..."):
            antibiogram = generate_antibiogram(
                filtered_ast,
                lab_name=lab_name,
                min_isolates=min_isolates,
                include_all=include_all
            )
        
        if 'error' in antibiogram and antibiogram.get('matrix') is None:
            st.error(antibiogram['error'])
        else:
            # Summary statistics
            st.subheader("Summary")
            summary = antibiogram.get('summary', {})
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Isolates", summary.get('total_isolates', 0))
            with col2:
                st.metric("Organisms", summary.get('total_organisms', 0))
            with col3:
                st.metric("Antibiotics", summary.get('total_antibiotics', 0))
            with col4:
                avg_susc = summary.get('overall_susceptibility', 0)
                st.metric("Avg Susceptibility", f"{avg_susc:.1f}%" if avg_susc else "N/A")
            
            st.markdown("---")
            
            # Display antibiogram
            st.subheader("Antibiogram Matrix")
            st.markdown("*Values show % Susceptible (number tested)*")
            
            # Display as interactive DataFrame with color styling
            matrix = antibiogram.get('matrix', pd.DataFrame())
            numeric_matrix = antibiogram.get('numeric_matrix', pd.DataFrame())
            
            if not matrix.empty:
                # Create styled dataframe
                def color_cells(val):
                    try:
                        # Extract numeric value from string like "85 (20)"
                        if pd.isna(val) or val == '-':
                            return 'background-color: #f0f0f0'
                        num_str = str(val).split('(')[0].strip().replace('*', '')
                        num = float(num_str) if num_str else 0
                        if num >= 90:
                            return 'background-color: #10b981; color: white'
                        elif num >= 70:
                            return 'background-color: #84cc16; color: white'
                        elif num >= 50:
                            return 'background-color: #fbbf24; color: #1f2937'
                        elif num >= 30:
                            return 'background-color: #f97316; color: white'
                        else:
                            return 'background-color: #ef4444; color: white'
                    except:
                        return 'background-color: #f0f0f0'
                
                styled_df = matrix.style.applymap(color_cells)
                st.dataframe(styled_df, use_container_width=True, height=400)
                
                # Legend
                st.markdown("""
                <div style="margin-top: 15px; padding: 10px; background: #f8fafc; border-radius: 8px;">
                    <p style="font-weight: 600; margin-bottom: 5px;">Legend:</p>
                    <div style="display: flex; gap: 15px; flex-wrap: wrap; font-size: 12px;">
                        <span><span style="display: inline-block; width: 15px; height: 15px; background: #10b981; margin-right: 5px; vertical-align: middle;"></span>≥90% Susceptible</span>
                        <span><span style="display: inline-block; width: 15px; height: 15px; background: #84cc16; margin-right: 5px; vertical-align: middle;"></span>70-89%</span>
                        <span><span style="display: inline-block; width: 15px; height: 15px; background: #fbbf24; margin-right: 5px; vertical-align: middle;"></span>50-69%</span>
                        <span><span style="display: inline-block; width: 15px; height: 15px; background: #f97316; margin-right: 5px; vertical-align: middle;"></span>30-49%</span>
                        <span><span style="display: inline-block; width: 15px; height: 15px; background: #ef4444; margin-right: 5px; vertical-align: middle;"></span>&lt;30%</span>
                    </div>
                    <p style="margin-top: 10px; font-size: 11px; color: #64748b;">* indicates fewer than minimum isolates (interpret with caution)</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("No antibiogram matrix data available.")
            
            # High resistance alerts
            if summary.get('lowest_susceptibility_combinations'):
                st.markdown("---")
                st.subheader("High Resistance Alerts")
                st.markdown("*Organism-antibiotic combinations with lowest susceptibility:*")
                
                for combo in summary['lowest_susceptibility_combinations']:
                    resistance = 100 - combo['pct_susceptible']
                    color = '#ef4444' if resistance >= 70 else '#f97316' if resistance >= 50 else '#eab308'
                    st.markdown(f"""
                    <div style="background: #f8fafc; padding: 10px; margin: 5px 0; border-radius: 5px; border-left: 4px solid {color};">
                        <strong>{combo['organism']}</strong> vs <strong>{combo['antibiotic']}</strong>: 
                        <span style="color: {color}; font-weight: bold;">{resistance:.0f}% resistant</span>
                        ({combo['total']} tested)
                    </div>
                    """, unsafe_allow_html=True)
            
            # Export options
            st.markdown("---")
            st.subheader("Export Antibiogram")
            
            col1, col2 = st.columns(2)
            with col1:
                # HTML export
                html_data = antibiogram_to_html(antibiogram)
                st.download_button(
                    label="Download as HTML",
                    data=html_data,
                    file_name=f"antibiogram_{lab_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.html",
                    mime="text/html"
                )
            with col2:
                # Excel export
                try:
                    excel_data = antibiogram_to_excel(antibiogram)
                    st.download_button(
                        label="Download as Excel",
                        data=excel_data,
                        file_name=f"antibiogram_{lab_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Excel export requires openpyxl: {e}")

# ============================================================================
# PAGE 11: WHONET EXPORT
# ============================================================================
elif page == "WHONET Export":
    st.header("WHONET Data Export")
    st.markdown("*Export data in WHONET format for integration with WHO GLASS and global surveillance networks.*")
    
    # Require dataset selection
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    # Import WHONET module
    from src.whonet import (
        convert_to_whonet_format, export_to_whonet_txt, export_to_whonet_excel,
        generate_glass_report, validate_whonet_data, generate_glass_html_report
    )
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)
    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available for WHONET export.")
    else:
        # Lab configuration
        st.subheader("Laboratory Information")
        
        col1, col2 = st.columns(2)
        with col1:
            lab_code = st.text_input("Laboratory Code", value="GH001", help="WHONET laboratory identifier")
        with col2:
            lab_name = st.text_input("Laboratory Name", value="AMR Surveillance Lab Ghana")
        
        lab_info = {'code': lab_code, 'name': lab_name}
        
        # Convert to WHONET format
        with st.spinner("Converting data to WHONET format..."):
            whonet_df = convert_to_whonet_format(all_samples, all_ast, lab_info)
        
        if whonet_df.empty:
            st.error("Unable to convert data to WHONET format.")
        else:
            # Validate data
            validation = validate_whonet_data(whonet_df)
            
            # Summary
            st.subheader("Export Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Records", len(whonet_df))
            with col2:
                st.metric("Unique Organisms", validation['statistics'].get('unique_organisms', 0))
            with col3:
                st.metric("Antibiotics", len(validation['statistics'].get('antibiotics', [])))
            with col4:
                status_icon = "Valid" if validation['is_valid'] else "Issues"
                st.metric("Status", status_icon)
            
            # Validation results
            if not validation['is_valid'] or validation['warnings']:
                with st.expander("Validation Details", expanded=not validation['is_valid']):
                    if validation['errors']:
                        for error in validation['errors']:
                            st.error(error)
                    if validation['warnings']:
                        for warning in validation['warnings']:
                            st.warning(warning)
            
            # Preview
            st.subheader("Data Preview")
            st.dataframe(whonet_df.head(20), use_container_width=True)
            
            st.markdown("---")
            
            # GLASS Report
            st.subheader("WHO GLASS Summary")
            
            glass_report = generate_glass_report(whonet_df)
            
            if 'error' not in glass_report:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Organism Distribution:**")
                    for org, count in list(glass_report.get('organisms', {}).items())[:10]:
                        st.write(f"- {org}: {count}")
                
                with col2:
                    st.markdown("**Specimen Types:**")
                    for spec, count in glass_report.get('specimen_distribution', {}).items():
                        st.write(f"- {spec}: {count}")
                
                # Priority pathogen resistance rates
                if glass_report.get('resistance_rates'):
                    st.markdown("---")
                    st.markdown("**Priority Pathogen Resistance Rates:**")
                    
                    for org, data in glass_report['resistance_rates'].items():
                        with st.expander(f"{org} (n={data['isolate_count']})"):
                            for ab, ab_data in data.get('antibiotics', {}).items():
                                rate = ab_data.get('resistance_rate', 0)
                                color = 'red' if rate >= 50 else 'orange' if rate >= 30 else 'green'
                                st.markdown(f"- **{ab}**: {rate:.1f}% resistant ({ab_data['tested']} tested)")
            
            st.markdown("---")
            
            # Export options
            st.subheader("Export Options")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Tab-delimited text (standard WHONET format)
                txt_data = export_to_whonet_txt(whonet_df)
                st.download_button(
                    label="Download WHONET Text",
                    data=txt_data,
                    file_name=f"WHONET_export_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    help="Standard WHONET tab-delimited format"
                )
            
            with col2:
                # Excel format
                try:
                    excel_data = export_to_whonet_excel(whonet_df)
                    st.download_button(
                        label="Download WHONET Excel",
                        data=excel_data,
                        file_name=f"WHONET_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Excel export requires openpyxl: {e}")
            
            with col3:
                # GLASS summary HTML report
                glass_html = generate_glass_html_report(glass_report)
                st.download_button(
                    label="Download GLASS Report",
                    data=glass_html,
                    file_name=f"GLASS_Report_{datetime.now().strftime('%Y%m%d')}.html",
                    mime="text/html",
                    help="WHO GLASS formatted HTML report"
                )

# ============================================================================
# PAGE 12: REPORT EXPORT
# ============================================================================
elif page == "Report Export":
    st.header("Report Export")

    # Require dataset selection before showing dashboard
    if not st.session_state.active_dataset_id:
        st.warning("Please select a dataset in the 'Data Management' page first.")
        st.stop()
    
    all_ast = db.get_dataset_ast(st.session_state.active_dataset_id)
    all_samples = db.get_dataset_samples(st.session_state.active_dataset_id)

    all_samples, all_ast = _apply_lab_filter(all_samples, all_ast)
    
    st.info(f"Viewing dataset: {st.session_state.active_dataset_id}")

    if all_ast.empty or all_samples.empty:
        st.warning("No data available in the selected dataset.")
    else:
        # ============================================================================
        # FILTERING CONTROLS (Same as Resistance Overview)
        # ============================================================================
        st.subheader("Report Filters")
        st.markdown("Configure filters to generate reports based on specific data subsets:")

        col1, col2, col3 = st.columns(3)

        with col1:
            # Category filter
            categories = sorted(all_samples['source_category'].dropna().astype(str).unique().tolist())
            if categories:
                category_options = ["All"] + categories
                selected_category_options = st.multiselect(
                    "Source Category",
                    category_options,
                    default=["All"],
                    key="report_categories"
                )
                # If "All" is selected, use all categories; otherwise use selected ones
                if "All" in selected_category_options:
                    selected_categories = categories
                else:
                    selected_categories = [opt for opt in selected_category_options if opt != "All"]
            else:
                selected_categories = []

        with col2:
            # Source type filter
            source_types = sorted(all_samples['source_type'].dropna().astype(str).unique().tolist())
            if source_types:
                source_type_options = ["All"] + source_types
                selected_source_type_options = st.multiselect(
                    "Source Type",
                    source_type_options,
                    default=["All"],
                    key="report_source_types"
                )
                # If "All" is selected, use all source types; otherwise use selected ones
                if "All" in selected_source_type_options:
                    selected_source_types = source_types
                else:
                    selected_source_types = [opt for opt in selected_source_type_options if opt != "All"]
            else:
                selected_source_types = []

        with col3:
            # Site type filter
            site_types = sorted(all_samples['site_type'].dropna().astype(str).unique().tolist())
            if site_types:
                site_type_options = ["All"] + site_types
                selected_site_type_options = st.multiselect(
                    "Site Type",
                    site_type_options,
                    default=["All"],
                    key="report_site_types"
                )
                # If "All" is selected, use all site types; otherwise use selected ones
                if "All" in selected_site_type_options:
                    selected_site_types = site_types
                else:
                    selected_site_types = [opt for opt in selected_site_type_options if opt != "All"]
            else:
                selected_site_types = []

        col4, col5, col6 = st.columns(3)

        with col4:
            # Region filter
            regions = sorted(all_samples['region'].dropna().astype(str).unique().tolist())
            if regions:
                region_options = ["All"] + regions
                selected_region_options = st.multiselect(
                    "Region",
                    region_options,
                    default=["All"],
                    key="report_regions"
                )
                # If "All" is selected, use all regions; otherwise use selected ones
                if "All" in selected_region_options:
                    selected_regions = regions
                else:
                    selected_regions = [opt for opt in selected_region_options if opt != "All"]
            else:
                selected_regions = []

        with col5:
            # District filter
            districts = sorted(all_samples['district'].dropna().astype(str).unique().tolist())
            if districts:
                district_options = ["All"] + districts
                selected_district_options = st.multiselect(
                    "District",
                    district_options,
                    default=["All"],
                    key="report_districts"
                )
                # If "All" is selected, use all districts; otherwise use selected ones
                if "All" in selected_district_options:
                    selected_districts = districts
                else:
                    selected_districts = [opt for opt in selected_district_options if opt != "All"]
            else:
                selected_districts = []

        with col6:
            # Date range filter
            if 'test_date' in all_ast.columns:
                min_date = pd.to_datetime(all_ast['test_date'].dropna()).min()
                max_date = pd.to_datetime(all_ast['test_date'].dropna()).max()

                if pd.notna(min_date) and pd.notna(max_date):
                    date_range = st.date_input(
                        "Date Range",
                        value=(min_date.date(), max_date.date()),
                        key="report_date_range"
                    )
                    if len(date_range) == 2:
                        start_date, end_date = date_range
                    else:
                        start_date, end_date = min_date.date(), max_date.date()
                else:
                    start_date, end_date = None, None
            else:
                start_date, end_date = None, None

        col7, col8 = st.columns(2)

        with col7:
            # Organism filter
            organisms = sorted(all_ast['organism'].dropna().astype(str).unique().tolist())
            if organisms:
                organism_options = ["All"] + organisms
                selected_organism_options = st.multiselect(
                    "Organisms",
                    organism_options,
                    default=["All"],
                    key="report_organisms"
                )
                # If "All" is selected, use all organisms; otherwise use selected ones
                if "All" in selected_organism_options:
                    selected_organisms = organisms
                else:
                    selected_organisms = [opt for opt in selected_organism_options if opt != "All"]
            else:
                selected_organisms = []

        with col8:
            # Antibiotic filter
            antibiotics = sorted(all_ast['antibiotic'].dropna().astype(str).unique().tolist())
            if antibiotics:
                antibiotic_options = ["All"] + antibiotics
                selected_antibiotic_options = st.multiselect(
                    "Antibiotics",
                    antibiotic_options,
                    default=["All"],
                    key="report_antibiotics"
                )
                # If "All" is selected, use all antibiotics; otherwise use selected ones
                if "All" in selected_antibiotic_options:
                    selected_antibiotics = antibiotics
                else:
                    selected_antibiotics = [opt for opt in selected_antibiotic_options if opt != "All"]
            else:
                selected_antibiotics = []

        # Apply filters to get filtered data
        st.markdown("---")

        # Apply sample filters
        if selected_categories and selected_regions and selected_districts:
            filtered_samples = all_samples[
                (all_samples['source_category'].astype(str).isin(selected_categories)) &
                (all_samples['source_type'].astype(str).isin(selected_source_types)) &
                (all_samples['site_type'].astype(str).isin(selected_site_types)) &
                (all_samples['region'].astype(str).isin(selected_regions)) &
                (all_samples['district'].astype(str).isin(selected_districts))
            ]
        else:
            filtered_samples = all_samples

        # Apply AST filters
        base_ast_filter = all_ast['sample_id'].astype(str).isin(filtered_samples['sample_id'].astype(str))

        if selected_organisms:
            base_ast_filter &= all_ast['organism'].astype(str).isin(selected_organisms)

        if selected_antibiotics:
            base_ast_filter &= all_ast['antibiotic'].astype(str).isin(selected_antibiotics)

        # Apply date filter if available
        if start_date and end_date and 'test_date' in all_ast.columns:
            date_filter = pd.to_datetime(all_ast['test_date']).dt.date.between(start_date, end_date)
            base_ast_filter &= date_filter

        filtered_ast = all_ast[base_ast_filter]

        # Display filter summary
        st.subheader("Filtered Data Summary")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Filtered Samples", filtered_samples['sample_id'].nunique())
        with col2:
            st.metric("Filtered Tests", len(filtered_ast))
        with col3:
            resistant_count = (filtered_ast['result'] == 'R').sum()
            resistance_rate = resistant_count / len(filtered_ast) * 100 if len(filtered_ast) > 0 else 0
            st.metric("Resistance Rate", f"{resistance_rate:.1f}%")
        with col4:
            st.metric("Organisms", filtered_ast['organism'].nunique())

        st.markdown("---")

        # ============================================================================
        # REPORT GENERATION
        # ============================================================================
        st.subheader("Generate Technical Report")

        if filtered_ast.empty:
            st.warning("No data matches the selected filters. Please adjust your filters.")
        else:
            # Report configuration
            report_title = st.text_input(
                "Report Title",
                value=f"AMR Technical Surveillance Report - {datetime.now().strftime('%B %Y')}",
                key="report_title"
            )

            # Dataset selection (optional - for metadata)
            datasets = db.get_all_datasets()
            # Hide admin-owned datasets from non-admin users
            config_admin_email, _ = _get_admin_config()
            admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()
            if not st.session_state.is_admin:
                datasets = [d for d in datasets if (d.get('uploaded_by') or '').strip().lower() != admin_email]
            dataset_names = [f"{d['dataset_name']} ({d['dataset_id']})" for d in datasets]

            selected_dataset_name = "Filtered Dataset"
            if dataset_names:
                selected_dataset_display = st.selectbox(
                    "Reference Dataset (optional)",
                    ["None"] + dataset_names,
                    key="reference_dataset"
                )
                if selected_dataset_display != "None":
                    selected_dataset_name = selected_dataset_display.split('(')[0].strip()

            if st.button("Generate Technical Report", type="primary", use_container_width=True):
                with st.spinner("Generating comprehensive technical report with filtered data..."):
                    try:
                        # Generate HTML report with filtered data
                        html_content = report.generate_filtered_html_report(
                            report_title,
                            filtered_samples,
                            filtered_ast,
                            selected_categories,
                            selected_regions,
                            selected_organisms,
                            selected_antibiotics,
                            pps_df=db.get_pps_surveys(),
                            pps_rx_df=db.get_pps_prescriptions(),
                            amu_df=db.get_amu_records(),
                            amc_df=db.get_amc_records(),
                        )

                        # Success message
                        st.success("Professional HTML report generated successfully!")
                        st.info("Report includes embedded interactive visualizations and comprehensive filtered data analysis")

                        # Preview section
                        with st.expander("Report Preview", expanded=False):
                            st.markdown("**Report will include:**")
                            st.markdown("- Executive summary with key metrics")
                            st.markdown("- Interactive resistance distribution charts")
                            st.markdown("- Geographic and temporal analysis")
                            st.markdown("- Advanced analytics and risk assessment")
                            st.markdown("- Professional formatting with no text overlap")

                        # Download button
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"AMR_Report_Filtered_{timestamp}.html"
                        st.download_button(
                            label="Download HTML Report",
                            data=html_content,
                            file_name=filename,
                            mime="text/html",
                            use_container_width=True
                        )

                    except Exception as e:
                        st.error(f"Error generating report: {str(e)}")
                        st.info("Please check your data and try again. If the error persists, contact support.")

# ============================================================================
# PAGE 14: PPS DASHBOARD
# ============================================================================
elif page == "PPS Dashboard":
    render_pps_page()

# ============================================================================
# PAGE 16: AMU DASHBOARD
# ============================================================================
elif page == "AMU Dashboard":
    render_amu_page()

# ============================================================================
# PAGE 17: AMC DASHBOARD
# ============================================================================
elif page == "AMC Dashboard":
    render_amc_page()

# ============================================================================
# PAGE 10: ADMIN - USER MANAGEMENT
# ============================================================================
elif page == "Admin - Users":
    if not st.session_state.is_admin:
        st.error("🚫 Access denied. Admin privileges required.")
        st.stop()
    
    st.header("👥 User Management")
    st.markdown("Manage user accounts and permissions")
    st.markdown("---")
    
    # Get all users
    all_users = db.get_all_users()
    
    if not all_users:
        st.info("📭 No users registered yet.")
    else:
        # Display users in a table
        st.subheader("Registered Users")
        
        # Create columns for display
        users_df = pd.DataFrame(all_users)
        users_df['created_at'] = pd.to_datetime(users_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        users_df['last_login'] = users_df['last_login'].apply(
            lambda x: pd.to_datetime(x).strftime('%Y-%m-%d %H:%M') if x else "Never"
        )
        users_df['Status'] = users_df['is_active'].apply(lambda x: "Active" if x else "Inactive")
        users_df['Role'] = users_df['is_admin'].apply(lambda x: "Admin" if x else "User")
        
        # Display table
        display_df = users_df[['email', 'created_at', 'last_login', 'Status', 'Role']].copy()
        display_df.columns = ['Email', 'Created', 'Last Login', 'Status', 'Role']
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # User management actions
        st.subheader("User Actions")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Deactivate User")
            selected_user = st.selectbox(
                "Select user to deactivate",
                [u for u in all_users if u['is_active']],
                format_func=lambda x: x['email'],
                key="deactivate_user"
            )
            if st.button("Deactivate", use_container_width=True, key="btn_deactivate"):
                success, msg = db.update_user_status(selected_user['user_id'], False)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        with col2:
            st.subheader("Reactivate User")
            selected_inactive = st.selectbox(
                "Select user to reactivate",
                [u for u in all_users if not u['is_active']],
                format_func=lambda x: x['email'],
                key="reactivate_user"
            )
            if st.button("Reactivate", use_container_width=True, key="btn_reactivate"):
                success, msg = db.update_user_status(selected_inactive['user_id'], True)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        st.markdown("---")
        
        # Reset password section
        st.subheader("Reset Password")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            user_for_reset = st.selectbox(
                "Select user to reset password",
                all_users,
                format_func=lambda x: x['email'],
                key="reset_user"
            )
        
        with col2:
            st.write("")  # Spacing
            if st.button("Generate Temporary Password", use_container_width=True):
                # Generate a temporary password
                temp_password = f"Temp@{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
                password_hash = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                success, msg = db.update_user_password(user_for_reset['email'], password_hash)
                
                if success:
                    st.success(msg)
                    st.info(f"Temporary Password: `{temp_password}`")
                    st.warning("Please share this password securely with the user. They should change it on first login.")
                else:
                    st.error(msg)
        
        st.markdown("---")
        
        # User statistics
        st.subheader("User Statistics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_users = len(all_users)
        active_users = len([u for u in all_users if u['is_active']])
        inactive_users = len([u for u in all_users if not u['is_active']])
        admin_users = len([u for u in all_users if u['is_admin']])
        
        with col1:
            st.metric("Total Users", total_users)
        with col2:
            st.metric("Active Users", active_users)
        with col3:
            st.metric("Inactive Users", inactive_users)
        with col4:
            st.metric("Admins", admin_users)

# ============================================================================
# Footer
# ============================================================================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #7f8c8d; font-size: 12px; margin-top: 30px;">
    <p>ICBB-AMRSS | ICBB AMR Surveillance System | Ghana</p>
    <p>Data stored locally in SQLite. No internet required.</p>
    <p><em>For academic and policy use. Always consult AMR experts for decision-making.</em></p>
</div>
""", unsafe_allow_html=True)
