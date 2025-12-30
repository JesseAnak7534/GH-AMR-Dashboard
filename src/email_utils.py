import os
import smtplib
from email.message import EmailMessage
from typing import Optional, Tuple


def get_smtp_config() -> dict:
    """Retrieve SMTP configuration from env variables or Streamlit secrets if available."""
    config = {
        "host": os.getenv("SMTP_HOST"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME"),
        "password": os.getenv("SMTP_PASSWORD"),
        "from_email": os.getenv("SMTP_FROM", os.getenv("ADMIN_EMAIL", "no-reply@example.com")),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"),
    }
    try:
        import streamlit as st  # type: ignore
        if hasattr(st, "secrets"):
            secrets = st.secrets
            config.update({
                "host": secrets.get("SMTP_HOST", config["host"]),
                "port": int(secrets.get("SMTP_PORT", config["port"])),
                "username": secrets.get("SMTP_USERNAME", config["username"]),
                "password": secrets.get("SMTP_PASSWORD", config["password"]),
                "from_email": secrets.get("SMTP_FROM", config["from_email"]),
                "use_tls": secrets.get("SMTP_USE_TLS", str(config["use_tls"]).lower()) in ("1", "true", "yes"),
            })
    except Exception:
        pass
    return config


def send_verification_email(to_email: str, code: str, country: str = "Ghana") -> Tuple[bool, str]:
    """Send a verification code to the user's email via SMTP.
    Returns (ok, message).
    """
    cfg = get_smtp_config()
    if not cfg.get("host") or not cfg.get("username") or not cfg.get("password"):
        # Fallback: no SMTP configured; return code to caller for dev display
        return False, f"SMTP not configured. Dev mode: your verification code is {code}"

    try:
        msg = EmailMessage()
        msg["Subject"] = f"AMR Dashboard Email Verification ({country})"
        msg["From"] = cfg["from_email"]
        msg["To"] = to_email
        msg.set_content(
            (
                "Hello,\n\n"
                "Use the code below to verify your email for the AMR Dashboard.\n\n"
                f"Verification Code: {code}\n\n"
                "This code expires in 30 minutes.\n\n"
                "If you did not request this, you can ignore this email.\n\n"
                "Regards,\nAMR Dashboard Team"
            )
        )

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            if cfg["use_tls"]:
                server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.send_message(msg)
        return True, "Verification email sent"
    except Exception as e:
        return False, f"Error sending email: {str(e)}"
