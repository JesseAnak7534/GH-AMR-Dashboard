"""
Login page for AMR Surveillance Dashboard.
Handles user authentication with email and password.
"""
import streamlit as st
import bcrypt
from datetime import datetime
from src import db

# Configure page
st.set_page_config(
    page_title="AMR Dashboard - Login",
    page_icon="🔐",
    layout="centered"
)

# Add custom CSS with background styling
st.markdown("""
    <style>
    * {
        margin: 0;
        padding: 0;
    }
    
    body {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        background-attachment: fixed;
        min-height: 100vh;
    }
    
    .main {
        background-color: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
    }
    
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .login-header {
        text-align: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5em;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    
    .login-subheader {
        text-align: center;
        color: #555;
        font-size: 1.1em;
        margin-bottom: 2rem;
    }
    
    .form-container {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    }
    
    .login-divider {
        text-align: center;
        color: #999;
        margin: 1.5rem 0;
        font-size: 0.9em;
    }
    
    .demo-box {
        background: #e8f4f8;
        border-left: 4px solid #667eea;
        padding: 1rem;
        border-radius: 5px;
        margin-top: 1rem;
    }
    
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.is_admin = False


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def login_user(email: str, password: str) -> bool:
    """Authenticate a user."""
    user = db.get_user_by_email(email)
    
    if user and user['is_active']:
        if verify_password(password, user['password_hash']):
            st.session_state.authenticated = True
            st.session_state.user_email = email
            st.session_state.is_admin = user['is_admin']
            db.update_last_login(email)
            return True
    return False


# Display login form
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    # Header with logo and title
    st.markdown('<div class="login-header">🦠 AMR Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subheader">Antimicrobial Resistance Surveillance System</div>', unsafe_allow_html=True)
    
    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)
    
    # Create tabs for login and signup
    tab1, tab2 = st.tabs(["🔐 Login", "📝 Sign Up"])
    
    with tab1:
        st.markdown('<h4 style="text-align: center; color: #333;">Welcome Back</h4>', unsafe_allow_html=True)
        
        with st.form("login_form"):
            email = st.text_input(
                "📧 Email Address",
                placeholder="your.email@example.com",
                key="login_email"
            )
            password = st.text_input(
                "🔐 Password",
                type="password",
                placeholder="Enter your password",
                key="login_password"
            )
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit_button = st.form_submit_button("Sign In", use_container_width=True)
            with col_btn2:
                st.form_submit_button("Forgot Password?", use_container_width=True, disabled=True)
            
            if submit_button:
                if not email or not password:
                    st.error("❌ Please fill in all fields")
                elif login_user(email, password):
                    st.success("✅ Login successful! Redirecting...")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Invalid email or password, or account is inactive")

    with tab2:
        st.markdown('<h4 style="text-align: center; color: #333;">Create Account</h4>', unsafe_allow_html=True)
        
        with st.form("signup_form"):
            new_email = st.text_input(
                "📧 Email Address",
                placeholder="your.email@example.com",
                key="signup_email"
            )
            new_password = st.text_input(
                "🔐 Password",
                type="password",
                placeholder="At least 6 characters",
                key="signup_pass"
            )
            confirm_password = st.text_input(
                "🔐 Confirm Password",
                type="password",
                placeholder="Confirm your password",
                key="confirm_pass"
            )
            
            submit_signup = st.form_submit_button("Create Account", use_container_width=True)
            
            if submit_signup:
                # Validation
                if not new_email or not new_password:
                    st.error("❌ Please fill in all fields")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters long")
                elif new_password != confirm_password:
                    st.error("❌ Passwords do not match")
                elif "@" not in new_email or "." not in new_email.split("@")[1]:
                    st.error("❌ Please enter a valid email address")
                else:
                    # Try to create user
                    password_hash = hash_password(new_password)
                    success, message = db.create_user(new_email, password_hash, is_admin=False)
                    
                    if success:
                        st.success("✅ Account created successfully!")
                        st.info("📝 You can now log in with your credentials in the Login tab.")
                    else:
                        st.error(f"❌ {message}")
    
    st.markdown("---")
    
    # Demo account info
    with st.expander("ℹ️ Demo Account (For Testing)", expanded=False):
        st.markdown("""
        <div class="demo-box">
        <strong>Email:</strong> admin@amr.gh<br>
        <strong>Password:</strong> Admin@123<br>
        <br>
        <em>Auto-created on first login. Admin account with full access.</em>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("")
    
    # Footer
    st.markdown("""
    <div style="text-align: center; color: #999; font-size: 0.85em; margin-top: 2rem;">
        <p>🦠 AMR Surveillance Dashboard</p>
        <p style="font-size: 0.8em; margin-top: 0.5rem;">Multi-source Surveillance System | Ghana</p>
        <p style="font-size: 0.75em; color: #ccc; margin-top: 1rem;">Secure • Private • Local</p>
    </div>
    """, unsafe_allow_html=True)

