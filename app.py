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
from dotenv import load_dotenv
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict
import plotly.express as px
import urllib.parse

# Import modules
from src import db, validate, plots, report, analytics
from src import email_utils

# Page configuration
st.set_page_config(
    page_title="AMR Surveillance Dashboard",
    page_icon="🦠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
db.init_database()

# Handle email verification via magic link query params
try:
    # Prefer stable API; fallback to experimental
    params = None
    if hasattr(st, "query_params"):
        params = st.query_params
    else:
        try:
            params = st.experimental_get_query_params()
        except Exception:
            params = {}

    email_q = None
    code_q = None
    if params:
        email_q = params.get("verify_email")
        code_q = params.get("verify_code")
        if isinstance(email_q, list):
            email_q = email_q[0] if email_q else None
        if isinstance(code_q, list):
            code_q = code_q[0] if code_q else None
    if email_q and code_q:
        ok, msg = db.verify_user_email(str(email_q), str(code_q))
        if ok:
            st.success("✅ Email verified via link! You can now log in.")
        else:
            st.error(f"❌ Verification failed: {msg}")
except Exception:
    pass

# Authentication check
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.is_admin = False

def _get_admin_config():
    """Retrieve admin bootstrap credentials from Streamlit secrets or environment variables."""
    admin_email = None
    admin_password = None
    # Prefer Streamlit secrets on cloud
    try:
        if hasattr(st, "secrets"):
            if "ADMIN_EMAIL" in st.secrets and "ADMIN_PASSWORD" in st.secrets:
                admin_email = st.secrets["ADMIN_EMAIL"]
                admin_password = st.secrets["ADMIN_PASSWORD"]
    except Exception:
        pass

    # Fallback to local .env / environment
    load_dotenv()
    admin_email = admin_email or os.getenv("ADMIN_EMAIL")
    admin_password = admin_password or os.getenv("ADMIN_PASSWORD")
    return admin_email, admin_password

# Create or promote main admin account if configured via secrets/env
ADMIN_EMAIL, ADMIN_PASSWORD = _get_admin_config()
if ADMIN_EMAIL and ADMIN_PASSWORD:
    try:
        admin_user = db.get_user_by_email(ADMIN_EMAIL)
        password_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        if not admin_user:
            db.create_user(ADMIN_EMAIL, password_hash, is_admin=True)
        else:
            # Ensure admin privileges and active status
            if not admin_user.get("is_admin"):
                db.set_user_admin(ADMIN_EMAIL, True)
            if not admin_user.get("is_active"):
                db.update_user_status(admin_user["user_id"], True)
            # Keep password in sync with configured admin password
            db.update_user_password(ADMIN_EMAIL, password_hash)
        # Auto-verify admin email
        try:
            db.set_user_verified(ADMIN_EMAIL, True)
        except Exception:
            pass
    except Exception:
        pass

# Optional one-time purge of non-admin users controlled by secret/env flag
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
            # Create flag file to avoid repeated purge across restarts
            os.makedirs("db", exist_ok=True)
            with open(flag_path, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} - {msg}")
            st.info(f"Startup maintenance: {msg}")
except Exception:
    pass

# If not authenticated, show login page
if not st.session_state.authenticated:
    # Render login page (avoid calling set_page_config twice)
    
    st.markdown("""
        <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .main { background: white; border-radius: 10px; padding: 2rem; }
        .center-title { text-align: center; color: #667eea; font-size: 2.5em; font-weight: bold; margin-bottom: 0.5rem; }
        .center-subtitle { text-align: center; color: #666; font-size: 1.1em; margin-bottom: 2rem; }
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown('<div class="center-title">🦠 AMR Dashboard</div>', unsafe_allow_html=True)
        st.markdown('<div class="center-subtitle">Antimicrobial Resistance Surveillance System</div>', unsafe_allow_html=True)
        st.markdown("---")
        
        # Create two columns for better spacing
        tab1, tab2 = st.tabs(["🔐 Login", "📝 Sign Up"])
        
        with tab1:
            st.subheader("Welcome Back")
            
            login_email = st.text_input("📧 Email Address", placeholder="Enter your email", key="login_email")
            login_password = st.text_input("🔐 Password", type="password", placeholder="Enter your password", key="login_password")
            
            if st.button("🔓 Sign In", use_container_width=True, type="primary"):
                if not login_email or not login_password:
                    st.error("❌ Please fill in all fields")
                else:
                    user = db.get_user_by_email(login_email)
                    if user and user['is_active']:
                        try:
                            if bcrypt.checkpw(login_password.encode("utf-8"), user['password_hash'].encode("utf-8")):
                                # Require email verification
                                if not user.get('is_verified'):
                                    st.error("❌ Please verify your email before logging in.")
                                    st.info("Check your email for the verification link and open it.")
                                    st.stop()
                                st.session_state.authenticated = True
                                st.session_state.user_email = login_email

                                # Enforce admin for configured email (secrets/env) or fallback fixed admin
                                config_admin_email, _ = _get_admin_config()
                                is_admin_flag = user['is_admin']
                                target_admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()
                                if login_email.strip().lower() == target_admin_email:
                                    is_admin_flag = 1
                                    try:
                                        db.set_user_admin(login_email, True)
                                        db.update_user_status(user['user_id'], True)
                                    except Exception:
                                        pass

                                st.session_state.is_admin = bool(is_admin_flag)
                                db.update_last_login(login_email)
                                st.success("✅ Login successful!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("❌ Invalid email or password")
                        except Exception as e:
                            st.error(f"❌ Login error: {str(e)}")
                    else:
                        st.error("❌ Invalid email or password, or account is inactive")
        
        with tab2:
            st.subheader("Create New Account")
            
            signup_email = st.text_input("📧 Email Address", placeholder="your.email@example.com", key="signup_email")
            signup_password = st.text_input("🔐 Password", type="password", placeholder="At least 6 characters", key="signup_password")
            signup_confirm = st.text_input("🔐 Confirm Password", type="password", placeholder="Confirm your password", key="signup_confirm")
            
            if st.button("✅ Create Account", use_container_width=True, type="primary"):
                if not signup_email or not signup_password:
                    st.error("❌ Please fill in all fields")
                elif len(signup_password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                elif signup_password != signup_confirm:
                    st.error("❌ Passwords do not match")
                elif "@" not in signup_email or "." not in signup_email.split("@")[1]:
                    st.error("❌ Invalid email format")
                else:
                    try:
                        password_hash = bcrypt.hashpw(signup_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                        success, msg = db.create_user(signup_email, password_hash, is_admin=False)
                        if success:
                            # Generate and send verification code
                            code = f"{secrets.randbelow(1000000):06d}"
                            expires_at = (datetime.now() + timedelta(minutes=30)).isoformat()
                            db.set_verification_code(signup_email, code, expires_at)
                            # Attempt to send email, but always show link and code as fallback
                            ok, send_msg = email_utils.send_verification_email(signup_email, code, country="Ghana")
                            base_url = email_utils.get_app_base_url()
                            verify_link = email_utils.build_verification_link(base_url, signup_email, code) if base_url else None

                            if ok:
                                st.success("✅ Account created! We've sent a verification email with a link.")
                            else:
                                if verify_link:
                                    st.info("✅ Account created! Use the verification link below to activate your account.")
                                else:
                                    st.info("If the email doesn't arrive, use the code below to verify.")

                            # Always present the code and link (if configured) so users can proceed
                            st.markdown("### Email Verification Details")
                            st.write("Use the code or click the link to verify your account.")
                            st.code(code, language="text")
                            if verify_link:
                                st.markdown(f"[Open verification link]({verify_link})")
                            else:
                                st.warning("Verification link is unavailable. Set APP_BASE_URL in Streamlit secrets for link support.")
                        else:
                            st.error(f"❌ {msg}")
                            # Verify Email tab removed; verification is via email link only.
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")

            # Provide a resend option in the Sign Up tab
            st.markdown("---")
            st.caption("Didn't receive the email? Resend it below.")
            colr1, colr2 = st.columns([2, 1])
            with colr1:
                resend_email = st.text_input("Resend to Email", value=signup_email or "", key="resend_email")
            with colr2:
                if st.button("📨 Resend Verification", use_container_width=True):
                    if not resend_email:
                        st.error("Enter an email to resend.")
                    else:
                        try:
                            code = f"{secrets.randbelow(1000000):06d}"
                            expires_at = (datetime.now() + timedelta(minutes=30)).isoformat()
                            db.set_verification_code(resend_email, code, expires_at)
                            ok, send_msg = email_utils.send_verification_email(resend_email, code, country="Ghana")
                            base_url = email_utils.get_app_base_url()
                            verify_link = email_utils.build_verification_link(base_url, resend_email, code) if base_url else None
                            if ok:
                                st.success("Verification email resent.")
                            else:
                                if verify_link:
                                    st.info("Verification email couldn't be sent. Use the link below to verify.")
                                else:
                                    st.info("If the email doesn't arrive, use the code below to verify.")
                            st.code(code, language="text")
                            if verify_link:
                                st.markdown(f"[Open verification link]({verify_link})")
                            else:
                                st.warning("Verification link is unavailable. Set APP_BASE_URL in Streamlit secrets for link support.")
                        except Exception as e:
                            st.error(f"❌ Error resending email: {str(e)}")
        
        st.markdown("---")
        
        st.markdown("""
            <div style="text-align: center; color: #999; font-size: 0.85em; margin-top: 2rem;">
                <p>🦠 AMR Surveillance Dashboard</p>
                <p style="font-size: 0.8em;">Multi-source Surveillance System | Ghana</p>
                <p style="font-size: 0.75em; color: #ccc; margin-top: 1rem;">Please enter your credentials to continue</p>
            </div>
        """, unsafe_allow_html=True)
    
    st.stop()

# App title and description (only shown when authenticated)
st.title("🦠 AMR Surveillance Dashboard")
st.markdown("### Multi-source Surveillance (Environment, Food, Human, Animal, Aquaculture) | Ghana")
st.markdown("---")

# Sidebar navigation with user info and admin panel
with st.sidebar:
    st.markdown(f"👤 **Logged in as:** {st.session_state.user_email}")
    if st.session_state.is_admin:
        st.markdown("🛡️ **Admin Account**")
    
    st.markdown("---")
    
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_email = None
        st.session_state.is_admin = False
        st.success("✅ Logged out successfully")
        st.rerun()
    
    st.markdown("---")

admin_pages = ["Admin - Users", "Admin - Datasets"] if st.session_state.is_admin else []
page = st.sidebar.radio(
    "Navigation",
    ["Upload & Data Quality", "Data Management", "Resistance Overview", "Trends", "Map Hotspots", "Advanced Analytics", "Risk Assessment", "Comparative Analysis", "Report Export"] + admin_pages
)

# ============================================================================
# PAGE 1: UPLOAD & DATA QUALITY
# ============================================================================
if page == "Upload & Data Quality":
    st.header("📤 Upload & Data Quality")
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        st.subheader("Template Download")
        # Create template on demand
        os.makedirs("templates", exist_ok=True)
        template_path = "templates/AMR_ENV_FOOD_template_v1.xlsx"
        
        if not os.path.exists(template_path):
            try:
                validate.create_template_excel()
                st.success("Template created!")
            except Exception as e:
                st.error(f"Error creating template: {e}")
        
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                st.download_button(
                    label="📥 Download Template",
                    data=f.read(),
                    file_name="AMR_ENV_FOOD_template_v1.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    with col1:
        st.subheader("Upload Data")
        uploaded_file = st.file_uploader(
            "Upload Excel file with 'samples' and 'ast_results' sheets",
            type=["xlsx", "xls"]
        )
        
        if uploaded_file:
            if st.button("✓ Validate Upload"):
                with st.spinner("Validating..."):
                    is_valid, errors, samples_df, ast_df = validate.validate_upload(uploaded_file)
                    
                    if is_valid:
                        st.success("✓ Validation successful!")

                        # Check for automated interpretation
                        auto_interpreted_count = ast_df['auto_interpreted'].sum() if 'auto_interpreted' in ast_df.columns else 0
                        if auto_interpreted_count > 0:
                            st.info(f"🤖 Automated interpretation performed on {int(auto_interpreted_count)} AST results using CLSI/EUCAST breakpoints")

                        # Save to database
                        dataset_id = str(uuid.uuid4())[:8]
                        success, msg = db.save_dataset(
                            dataset_id,
                            uploaded_file.name.replace('.xlsx', ''),
                            samples_df,
                            ast_df,
                            uploaded_by=(st.session_state.user_email or "Anonymous")
                        )

                        if success:
                            st.success(f"✓ Data saved with ID: {dataset_id}")
                            st.balloons()
                        else:
                            st.error(f"Database error: {msg}")
                    else:
                        st.error("❌ Validation failed. Errors:")
                        for i, error in enumerate(errors, 1):
                            st.markdown(f"  {i}. {error}")
    
    st.markdown("---")
    
    # Show existing datasets
    st.subheader("📊 Existing Datasets")
    datasets = db.get_all_datasets()
    # Hide admin-owned datasets from non-admin users
    config_admin_email, _ = _get_admin_config()
    admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()
    if not st.session_state.is_admin:
        datasets = [ds for ds in datasets if (ds.get('uploaded_by') or '').strip().lower() != admin_email]
    
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
                if st.button("🗑️ Delete", key=f"del_{ds['dataset_id']}"):
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
    st.header("🗂️ Data Management")
    st.markdown("Manage, review, and maintain your AMR surveillance datasets")

    # Get all datasets
    datasets = db.get_all_datasets()
    # Hide admin-owned datasets from non-admin users
    config_admin_email, _ = _get_admin_config()
    admin_email = (config_admin_email or "jesseanak98@gmail.com").strip().lower()
    if not st.session_state.is_admin:
        datasets = [ds for ds in datasets if (ds.get('uploaded_by') or '').strip().lower() != admin_email]

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
elif page == "Admin - Datasets":
    st.header("🛡️ Admin - Datasets")
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

        if selected_dataset_display:
            # Extract dataset ID
            try:
                selected_dataset_id = selected_dataset_display.split("(ID: ")[1].rstrip(")")
            except (IndexError, ValueError):
                st.error("Error parsing dataset ID. Please refresh the page.")
                selected_dataset_id = None

            if selected_dataset_id:
                # Get dataset details
                dataset_details = next((ds for ds in datasets if ds['dataset_id'] == selected_dataset_id), None)

                if dataset_details:
                    st.markdown("---")

                # Dataset overview
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Dataset ID", dataset_details['dataset_id'])
                with col2:
                    st.metric("Samples", dataset_details['rows_samples'])
                with col3:
                    st.metric("Tests", dataset_details['rows_tests'])
                with col4:
                    st.metric("Uploaded", dataset_details['uploaded_at'][:10])

                st.markdown("---")

                # Load data for all tabs
                try:
                    samples_data = db.get_dataset_samples(selected_dataset_id)
                    ast_data = db.get_dataset_ast(selected_dataset_id)
                except Exception as e:
                    st.error(f"Error loading dataset data: {str(e)}")
                    samples_data = pd.DataFrame()
                    ast_data = pd.DataFrame()

                # Data preview tabs
                tab1, tab2, tab3 = st.tabs(["📊 Samples Data", "🧪 AST Results", "📈 Summary Statistics"])

                with tab1:
                    st.subheader("Sample Data Preview")
                    if not samples_data.empty:
                        st.dataframe(samples_data.head(100), use_container_width=True)
                        st.caption(f"Showing first 100 of {len(samples_data)} samples")

                        # Download samples
                        csv_samples = samples_data.to_csv(index=False)
                        st.download_button(
                            label="📥 Download Samples CSV",
                            data=csv_samples,
                            file_name=f"{dataset_details['dataset_name']}_samples.csv",
                            mime="text/csv",
                            key="download_samples"
                        )
                    else:
                        st.warning("No sample data found for this dataset")

                with tab2:
                    st.subheader("AST Results Preview")
                    if not ast_data.empty:
                        st.dataframe(ast_data.head(100), use_container_width=True)
                        st.caption(f"Showing first 100 of {len(ast_data)} test results")

                        # Download AST results
                        csv_ast = ast_data.to_csv(index=False)
                        st.download_button(
                            label="📥 Download AST Results CSV",
                            data=csv_ast,
                            file_name=f"{dataset_details['dataset_name']}_ast_results.csv",
                            mime="text/csv",
                            key="download_ast"
                        )
                    else:
                        st.warning("No AST data found for this dataset")

                with tab3:
                    st.subheader("Dataset Summary Statistics")

                    if not samples_data.empty and not ast_data.empty:
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.metric("Unique Organisms", ast_data['organism'].nunique())
                            st.metric("Unique Antibiotics", ast_data['antibiotic'].nunique())

                        with col2:
                            resistant_count = (ast_data['result'] == 'R').sum()
                            resistance_rate = resistant_count / len(ast_data) * 100 if len(ast_data) > 0 else 0
                            st.metric("Resistance Rate", f"{resistance_rate:.1f}%")
                            st.metric("Resistant Isolates", resistant_count)

                        with col3:
                            st.metric("Geographic Coverage", f"{samples_data['latitude'].notna().sum()} samples with coordinates")
                            st.metric("Source Categories", samples_data['source_category'].nunique())

                        # Data quality indicators
                        st.markdown("---")
                        st.subheader("Data Quality Indicators")

                        quality_col1, quality_col2, quality_col3 = st.columns(3)

                        with quality_col1:
                            missing_coords = samples_data['latitude'].isna().sum()
                            st.metric("Missing Coordinates", missing_coords)
                            if missing_coords > 0:
                                st.warning(f"{missing_coords} samples lack geographic coordinates")

                        with quality_col2:
                            missing_results = ast_data['result'].isna().sum()
                            st.metric("Missing Results", missing_results)
                            if missing_results > 0:
                                st.error(f"{missing_results} tests have missing S/I/R results")

                        with quality_col3:
                            auto_interp = ast_data['auto_interpreted'].sum() if 'auto_interpreted' in ast_data.columns else 0
                            st.metric("Auto-Interpreted", auto_interp)
                            if auto_interp > 0:
                                st.info(f"{auto_interp} results automatically interpreted using CLSI/EUCAST breakpoints")
                            else:
                                st.info("No automatic interpretation data available")
                    else:
                        st.warning("Unable to calculate statistics - missing data")

                # Dataset actions
                st.markdown("---")
                st.subheader("Dataset Actions")

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("🔄 Refresh Data", key="refresh_data"):
                        st.rerun()

                with col2:
                    # Export complete dataset
                    if st.button("📦 Export Complete Dataset", key="export_dataset"):
                        try:
                            # Create Excel file with both sheets
                            from io import BytesIO
                            import pandas as pd

                            output = BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                samples_data.to_excel(writer, sheet_name='samples', index=False)
                                ast_data.to_excel(writer, sheet_name='ast_results', index=False)

                            output.seek(0)
                            
                            # Store the Excel data in session state for download
                            st.session_state.excel_data = output.getvalue()
                            st.session_state.excel_filename = f"{dataset_details['dataset_name']}_complete.xlsx"
                            st.success("Excel file prepared! Click download button below.")
                            
                        except Exception as e:
                            st.error(f"Error creating Excel file: {str(e)}")
                    
                    # Show download button if Excel data is ready
                    if 'excel_data' in st.session_state and 'excel_filename' in st.session_state:
                        st.download_button(
                            label="📥 Download Excel File",
                            data=st.session_state.excel_data,
                            file_name=st.session_state.excel_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_excel"
                        )

                with col3:
                    # Delete dataset (with confirmation)
                    if "confirm_delete" not in st.session_state:
                        st.session_state.confirm_delete = False
                    
                    if st.button("🗑️ Delete Dataset", key="delete_dataset_confirm"):
                        st.session_state.confirm_delete = True
                    
                    if st.session_state.confirm_delete:
                        st.error("⚠️ Are you sure you want to delete this dataset? This action cannot be undone!")
                        
                        col_confirm1, col_confirm2 = st.columns(2)
                        with col_confirm1:
                            if st.button("✅ Yes, Delete", key="confirm_delete_yes"):
                                success, msg = db.delete_dataset(selected_dataset_id)
                                if success:
                                    st.success("Dataset deleted successfully!")
                                    st.session_state.confirm_delete = False
                                    st.rerun()
                                else:
                                    st.error(f"Error deleting dataset: {msg}")
                                    st.session_state.confirm_delete = False
                                    
                        with col_confirm2:
                            if st.button("❌ Cancel", key="confirm_delete_no"):
                                st.info("Delete cancelled")
                                st.session_state.confirm_delete = False

# ============================================================================
# PAGE 3: RESISTANCE OVERVIEW
# ============================================================================
elif page == "Resistance Overview":
    st.header("📈 Resistance Overview")
    
    # Get all data
    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # Filters
        st.sidebar.markdown("### Filters")
        
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
            filtered_samples = all_samples[
                (all_samples['source_category'].astype(str).isin(selected_categories)) &
                (all_samples['source_type'].astype(str).isin(selected_source_types)) &
                (all_samples['site_type'].astype(str).isin(selected_site_types)) &
                (all_samples['region'].astype(str).isin(selected_regions)) &
                (all_samples['district'].astype(str).isin(selected_districts))
            ]
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
            
            st.plotly_chart(
                plots.plot_organism_antibiotic_heatmap(filtered_ast),
                use_container_width=True
            )
            
            st.markdown("---")
            
            # Advanced AMR Features
            st.subheader("🔬 Multi-Drug Resistance Analysis")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                # MDR distribution graph
                mdr_data = plots.detect_mdr_isolates(filtered_ast)
                if not mdr_data.empty:
                    # Create MDR distribution chart
                    import plotly.graph_objects as go
                    
                    # Count MDR by drug class count
                    mdr_counts = mdr_data['resistant_drug_classes'].value_counts().sort_index()
                    
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=mdr_counts.index,
                        y=mdr_counts.values,
                        marker_color='#e74c3c',
                        name='MDR Isolates'
                    ))
                    
                    fig.update_layout(
                        title='Multi-Drug Resistant Isolates by Drug Class Count',
                        xaxis_title='Number of Resistant Drug Classes',
                        yaxis_title='Number of Isolates',
                        height=400
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No multi-drug resistant isolates detected")
            
            with col2:
                mdr_data = plots.detect_mdr_isolates(filtered_ast)
                if not mdr_data.empty:
                    st.warning(f"⚠️ {len(mdr_data)} multi-drug resistant isolates detected")
                    st.dataframe(mdr_data[['isolate_id', 'organism', 'resistant_drug_classes']], use_container_width=True)
                else:
                    st.info("No multi-drug resistant isolates detected (MDR threshold: 3+ drug classes)")
            
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
            st.subheader("📊 Data Preview")
            display_df = filtered_ast[['sample_id', 'organism', 'antibiotic', 'result', 'method', 'test_date']].head(100)
            st.dataframe(display_df, use_container_width=True)

# ============================================================================
# PAGE 4: TRENDS
# ============================================================================
elif page == "Trends":
    st.header("📊 Resistance Trends")
    
    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # Filters
        st.sidebar.markdown("### Trend Filters")
        
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
            st.subheader("📈 Trend Summary")
            
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
    st.header("🗺️ Geographic Hotspots & Regional Analysis")
    
    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # Check if geographic data exists
        samples_with_coords = all_samples[
            all_samples['latitude'].notna() & 
            all_samples['longitude'].notna()
        ]
        has_coords = len(samples_with_coords) > 0
        
        if has_coords:
            # Enhanced Interactive Folium Map
            st.subheader("📍 Interactive Ghana Map - Resistance Hotspots & Regional Analysis")
            
            try:
                # Import the enhanced mapping module
                from src import ghana_map
                
                # Create and display interactive pydeck map
                m = ghana_map.create_interactive_ghana_map(samples_with_coords, all_ast)
                
                # Display using pydeck
                st.pydeck_chart(m, use_container_width=True)
                
                st.markdown("---")
                
                # Map features explanation
                with st.expander("📚 How to Use the Interactive Map", expanded=False):
                    st.markdown("""
                    **Map Components:**
                    - **Colored Circles**: Sample locations colored by resistance level
                    - **Blue Markers 🔵**: Region centers (administrative boundaries)
                    - **Purple Markers 🟣**: District locations (municipality centers)
                    
                    **Interactions:**
                    - Click any marker to see detailed information
                    - Drag to pan around Ghana
                    - Scroll to zoom in/out
                    - Use the zoom controls in the top-left corner
                    - Toggle layers on/off using the layer control (top-right)
                    
                    **Color Legend:**
                    - 🔴 **Red**: High resistance (>50%) - Critical surveillance area
                    - 🟠 **Orange**: Medium resistance (30-50%) - Monitor closely
                    - 🟢 **Green**: Low resistance (<30%) - Lower risk
                    """)
                
            except Exception as e:
                st.warning(f"⚠️ Could not load enhanced map: {str(e)}")
                st.info("Displaying alternative map visualization below...")
                
                # Fallback to Plotly map
                st.plotly_chart(
                    plots.plot_point_map(samples_with_coords, all_ast),
                    use_container_width=True
                )
            
            st.markdown("---")
        else:
            st.info("📍 No geographic coordinates in uploaded data. Add latitude/longitude to samples sheet to enable location mapping.")
        
        # Regional Analysis
        st.subheader("🏘️ Resistance by Region")
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
        st.subheader("🔴 District-Level Resistance Hotspots")
        
        # Detailed district analysis
        st.plotly_chart(
            plots.plot_resistance_by_district_detailed(all_ast, all_samples, top_n=15),
            use_container_width=True
        )
        
        st.markdown("---")
        
        # Top districts table
        st.subheader("📊 Top Districts Summary Table")
        
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
        st.subheader("⚠️ Surveillance Alerts & Warnings")
        
        alerts = plots.get_surveillance_alerts(all_ast, all_samples)
        
        if alerts:
            for alert in alerts:
                if alert['severity'] == 'HIGH':
                    st.error(f"🔴 **{alert['severity']}**: {alert['message']}")
                elif alert['severity'] == 'MEDIUM':
                    st.warning(f"🟠 **{alert['severity']}**: {alert['message']}")
                else:
                    st.info(f"🔵 **{alert['severity']}**: {alert['message']}")
        else:
            st.success("✅ No critical alerts detected")



# ============================================================================
# PAGE 6: ADVANCED ANALYTICS
# ============================================================================
elif page == "Advanced Analytics":
    st.header("🔬 Advanced Analytics & Insights")
    
    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # Tab selection
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Statistics", 
            "📈 Trends & Forecasts", 
            "🔍 Emerging Patterns",
            "💊 Antibiotic Insights",
            "📋 Data Quality"
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
                st.info(f"🟢 **Susceptible**: {stats.get('susceptible_count', 0)} ({stats.get('susceptible_rate', 0):.1f}%)")
            with col2:
                st.warning(f"🟡 **Intermediate**: {stats.get('intermediate_count', 0)} ({stats.get('intermediate_rate', 0):.1f}%)")
            with col3:
                st.error(f"🔴 **Resistant**: {stats.get('resistant_count', 0)} ({stats.get('resistance_rate', 0):.1f}%)")
            
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
                        st.error(f"📈 **{trend}** - Risk: {risk}")
                    elif trend == 'DECREASING':
                        st.success(f"📉 **{trend}** - Risk: {risk}")
                    else:
                        st.info(f"➡️ **{trend}** - Risk: {risk}")
                
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
                st.info(f"📊 Trend: {forecast['forecasts'][0]['trend'].upper()}")
                
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
                st.warning(f"⚠️ {forecast['error']}")
        
        # TAB 3: EMERGING PATTERNS
        with tab3:
            st.subheader("Emerging Resistance Patterns")
            
            emerging = analytics.identify_emerging_resistance(all_ast, all_samples)
            
            if emerging:
                emerging_df = pd.DataFrame(emerging)
                st.dataframe(emerging_df, use_container_width=True)
                
                st.warning(f"🚨 {len(emerging)} emerging resistance patterns detected in the last 3 months")
            else:
                st.success("✅ No concerning emerging patterns detected")
        
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
                    st.success(f"✅ **Preferred**: {preferred}")
                with col2:
                    st.info(f"✓ **Good**: {good}")
                with col3:
                    st.warning(f"⚠️ **Caution**: {caution}")
                with col4:
                    st.error(f"❌ **Avoid**: {avoid}")
                
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
                    st.success("✅ No data quality issues detected")
                
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
    st.header("⚠️ Risk Assessment & Alerts")
    
    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()
    
    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # Tabs
        tab1, tab2, tab3 = st.tabs(["🔴 Risk Scores", "🏥 Resistance Burden", "📉 Organism Assessment"])
        
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
                            st.error("🔴 **Urgent intervention required** - Consider alternative treatment options")
                        elif risk_item['risk_level'] == 'HIGH':
                            st.warning("🟠 **Enhanced surveillance** - Monitor trends closely")
                        else:
                            st.info("🔵 **Monitor** - Continue standard surveillance")
            else:
                st.success(f"✅ No organisms above risk threshold ({risk_threshold})")
        
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
                    st.error(f"🔴 {impact}")
                elif 'HIGH' in impact:
                    st.warning(f"🟠 {impact}")
                else:
                    st.info(f"🔵 {impact}")
                
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
        
        # TAB 3: ORGANISM ASSESSMENT
        with tab3:
            st.subheader("Detailed Organism Risk Assessment")
            
            organisms = sorted(all_ast['organism'].dropna().astype(str).unique().tolist())
            
            if organisms:
                selected_org = st.selectbox("Select Organism", organisms)
                
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
                        
                        st.markdown("---")
                        
                        st.subheader("Risk Assessment Details")
                        
                        st.markdown("**Risk Factors:**")
                        for factor in org_risk['risk_factors']:
                            st.write(f"• {factor}")
                        
                        st.markdown("---")
                        
                        # Recommendations
                        st.subheader("Clinical Recommendations")
                        
                        if org_risk['risk_level'] == 'CRITICAL':
                            st.error("""
                            🔴 **CRITICAL RISK LEVEL**
                            
                            • Implement enhanced infection control measures
                            • Review treatment guidelines
                            • Consider alternative antimicrobials
                            • Increase surveillance frequency
                            • Report to national health authorities
                            """)
                        elif org_risk['risk_level'] == 'HIGH':
                            st.warning("""
                            🟠 **HIGH RISK LEVEL**
                            
                            • Increase surveillance frequency
                            • Monitor trends closely
                            • Review empiric treatment protocols
                            • Consider antimicrobial stewardship interventions
                            """)
                        else:
                            st.info("""
                            🔵 **MODERATE/LOW RISK LEVEL**
                            
                            • Continue routine surveillance
                            • Monitor for any changes in resistance patterns
                            • Maintain current treatment protocols
                            """)


# ============================================================================
# PAGE 8: COMPARATIVE ANALYSIS
# ============================================================================
elif page == "Comparative Analysis":
    st.header("🔍 Comparative Analysis")
    st.markdown("Compare resistance patterns across different categories, time periods, and sources")

    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()

    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # Analysis type selection
        analysis_type = st.selectbox(
            "Select Comparison Type",
            ["Category Comparison", "Time Period Comparison", "Regional Comparison", "Source Type Comparison", "Multi-Parameter Comparison", "Cross-Variable Comparison", "Custom Comparison"],
            key="comparison_type"
        )

        st.markdown("---")

        if analysis_type == "Category Comparison":
            st.subheader("📊 Category Comparison")

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

                if st.button("🔍 Compare Categories", key="compare_categories"):
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
                            trend = "↗️ Increasing" if diff > 0 else "↘️ Decreasing" if diff < 0 else "➡️ Stable"
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

        elif analysis_type == "Regional Comparison":
            st.subheader("🗺️ Regional Comparison")

            regions = sorted(all_samples['region'].dropna().unique())
            if len(regions) > 1:
                selected_regions_comp = st.multiselect(
                    "Select Regions to Compare",
                    regions,
                    default=regions[:3] if len(regions) >= 3 else regions,
                    key="regional_comparison"
                )

                if len(selected_regions_comp) >= 2 and st.button("Compare Regions", key="compare_regions"):
                    # Get data for each region
                    regional_data = {}

                    for region in selected_regions_comp:
                        region_samples = all_samples[all_samples['region'] == region]
                        region_ast = all_ast[all_ast['sample_id'].isin(region_samples['sample_id'])]

                        if not region_ast.empty:
                            resistance_rate = (region_ast['result'] == 'R').sum() / len(region_ast) * 100
                            regional_data[region] = {
                                'resistance_rate': resistance_rate,
                                'total_tests': len(region_ast),
                                'resistant_count': (region_ast['result'] == 'R').sum(),
                                'data': region_ast
                            }

                    if len(regional_data) >= 2:
                        # Create comparison table
                        comparison_table = []
                        for region, data in regional_data.items():
                            comparison_table.append({
                                'Region': region,
                                'Resistance Rate (%)': round(data['resistance_rate'], 1),
                                'Total Tests': data['total_tests'],
                                'Resistant Isolates': data['resistant_count']
                            })

                        st.dataframe(pd.DataFrame(comparison_table))

                        # Resistance rate comparison chart
                        fig = px.bar(
                            pd.DataFrame(comparison_table),
                            x='Region',
                            y='Resistance Rate (%)',
                            title='Regional Resistance Comparison',
                            color='Resistance Rate (%)',
                            color_continuous_scale='Reds'
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        # Top organisms by region
                        st.markdown("### Top Organisms by Region")

                        col1, col2 = st.columns(2)

                        region_list = list(regional_data.keys())
                        if len(region_list) >= 2:
                            with col1:
                                st.markdown(f"**{region_list[0]}**")
                                org_data = regional_data[region_list[0]]['data'].groupby('organism').agg({
                                    'result': lambda x: (x == 'R').sum() / len(x) * 100
                                }).round(1).sort_values(by='result', ascending=False).head(5)
                                st.dataframe(org_data)

                            with col2:
                                st.markdown(f"**{region_list[1]}**")
                                org_data = regional_data[region_list[1]]['data'].groupby('organism').agg({
                                    'result': lambda x: (x == 'R').sum() / len(x) * 100
                                }).round(1).sort_values(by='result', ascending=False).head(5)
                                st.dataframe(org_data)
                    else:
                        st.warning("Need data from at least 2 regions for comparison.")
                else:
                    st.info("Select at least 2 regions to compare.")
            else:
                st.warning("Need data from multiple regions for comparison.")

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
            st.subheader("🎲 Multi-Parameter Comparison")
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
            st.subheader("🔀 Cross-Variable Comparison")
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

            if st.button("🔍 Run Custom Comparison", key="custom_comparison"):
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
# PAGE 9: REPORT EXPORT
# ============================================================================
elif page == "Report Export":
    st.header("📄 Report Export")

    all_ast = db.get_all_ast_results()
    all_samples = db.get_all_samples()

    if all_ast.empty or all_samples.empty:
        st.warning("No data available. Please upload data first.")
    else:
        # ============================================================================
        # FILTERING CONTROLS (Same as Resistance Overview)
        # ============================================================================
        st.subheader("🔍 Report Filters")
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
        st.subheader("📊 Filtered Data Summary")
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
        st.subheader("📄 Generate Technical Report")

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

            if st.button("📊 Generate Technical Report", type="primary", use_container_width=True):
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
                            selected_antibiotics
                        )

                        # Success message
                        st.success("✅ Professional HTML report generated successfully!")
                        st.info("📊 Report includes embedded interactive visualizations and comprehensive filtered data analysis")

                        # Preview section
                        with st.expander("📋 Report Preview", expanded=False):
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
                            label="📥 Download Professional HTML Report",
                            data=html_content,
                            file_name=filename,
                            mime="text/html",
                            use_container_width=True
                        )

                    except Exception as e:
                        st.error(f"Error generating report: {str(e)}")
                        st.info("Please check your data and try again. If the error persists, contact support.")

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
        st.subheader("📋 Registered Users")
        
        # Create columns for display
        users_df = pd.DataFrame(all_users)
        users_df['created_at'] = pd.to_datetime(users_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        users_df['last_login'] = users_df['last_login'].apply(
            lambda x: pd.to_datetime(x).strftime('%Y-%m-%d %H:%M') if x else "Never"
        )
        users_df['Status'] = users_df['is_active'].apply(lambda x: "🟢 Active" if x else "🔴 Inactive")
        users_df['Role'] = users_df['is_admin'].apply(lambda x: "👨‍💼 Admin" if x else "👤 User")
        
        # Display table
        display_df = users_df[['email', 'created_at', 'last_login', 'Status', 'Role']].copy()
        display_df.columns = ['Email', 'Created', 'Last Login', 'Status', 'Role']
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # User management actions
        st.subheader("🛠️ User Actions")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Deactivate User")
            selected_user = st.selectbox(
                "Select user to deactivate",
                [u for u in all_users if u['is_active']],
                format_func=lambda x: x['email'],
                key="deactivate_user"
            )
            if st.button("🔴 Deactivate", use_container_width=True, key="btn_deactivate"):
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
            if st.button("🟢 Reactivate", use_container_width=True, key="btn_reactivate"):
                success, msg = db.update_user_status(selected_inactive['user_id'], True)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        st.markdown("---")
        
        # Reset password section
        st.subheader("🔐 Reset Password")
        
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
            if st.button("🔑 Generate Temporary Password", use_container_width=True):
                # Generate a temporary password
                temp_password = f"Temp@{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
                password_hash = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                success, msg = db.update_user_password(user_for_reset['email'], password_hash)
                
                if success:
                    st.success(msg)
                    st.info(f"🔐 Temporary Password: `{temp_password}`")
                    st.warning("⚠️ Please share this password securely with the user. They should change it on first login.")
                else:
                    st.error(msg)
        
        st.markdown("---")
        
        # User statistics
        st.subheader("📊 User Statistics")
        
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
    <p>🦠 AMR Surveillance Dashboard | Multi-source Surveillance | Ghana</p>
    <p>Data stored locally in SQLite. No internet required.</p>
    <p><em>For academic and policy use. Always consult AMR experts for decision-making.</em></p>
</div>
""", unsafe_allow_html=True)
