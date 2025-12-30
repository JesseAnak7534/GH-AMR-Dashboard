import os
import smtplib
from email.message import EmailMessage
from typing import Optional, Tuple
import requests
import urllib.parse


def _get_secrets() -> dict:
    try:
        import streamlit as st  # type: ignore
        if hasattr(st, "secrets"):
            return dict(st.secrets)
    except Exception:
        pass
    return {}


def get_smtp_config() -> dict:
    """Retrieve SMTP configuration from env variables or Streamlit secrets if available."""
    secrets_cfg = _get_secrets()
    config = {
        "host": secrets_cfg.get("SMTP_HOST") or os.getenv("SMTP_HOST"),
        "port": int(secrets_cfg.get("SMTP_PORT") or os.getenv("SMTP_PORT", "587")),
        "username": secrets_cfg.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
        "password": secrets_cfg.get("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD"),
        "from_email": secrets_cfg.get("SMTP_FROM") or os.getenv("SMTP_FROM") or os.getenv("ADMIN_EMAIL") or "no-reply@example.com",
        "use_tls": str(secrets_cfg.get("SMTP_USE_TLS") or os.getenv("SMTP_USE_TLS", "true")).lower() in ("1", "true", "yes"),
    }
    return config


def get_app_base_url() -> Optional[str]:
    secrets_cfg = _get_secrets()
    return secrets_cfg.get("APP_BASE_URL") or os.getenv("APP_BASE_URL")


def build_verification_link(base_url: Optional[str], email: str, code: str) -> Optional[str]:
    if not base_url:
        return None
    params = {
        "verify_email": email,
        "verify_code": code,
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def send_verification_email(to_email: str, code: str, country: str = "Ghana") -> Tuple[bool, str]:
    """Send a verification email containing both code and a magic link.
    Prefers SendGrid API if configured, otherwise SMTP; returns (ok, message).
    """
    base_url = get_app_base_url()
    link = build_verification_link(base_url, to_email, code) if base_url else None

    # Try SendGrid first if available
    secrets_cfg = _get_secrets()
    sg_key = secrets_cfg.get("SENDGRID_API_KEY") or os.getenv("SENDGRID_API_KEY")
    sg_from = secrets_cfg.get("SENDGRID_FROM") or os.getenv("SENDGRID_FROM")
    if sg_key and sg_from:
        try:
            body_text = (
                "Hello,\n\n"
                "Use the code below to verify your email for the AMR Dashboard, or click the link provided.\n\n"
                f"Verification Code: {code}\n"
                + (f"Verification Link: {link}\n\n" if link else "") +
                "This code expires in 30 minutes.\n\n"
                "Regards,\nAMR Dashboard Team"
            )
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": sg_from},
                "subject": f"AMR Dashboard Email Verification ({country})",
                "content": [{"type": "text/plain", "value": body_text}],
            }
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {sg_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
            if 200 <= resp.status_code < 300:
                return True, "Verification email sent"
            else:
                # Fall through to SMTP
                pass
        except Exception as e:
            # Fall through to SMTP
            pass

    # SMTP fallback
    cfg = get_smtp_config()
    if not cfg.get("host") or not cfg.get("username") or not cfg.get("password"):
        # Fallback: no SMTP configured; return dev message including code and link
        dev_msg = f"SMTP not configured. Dev mode: code={code}" + (f", link={link}" if link else "")
        return False, dev_msg

    try:
        msg = EmailMessage()
        msg["Subject"] = f"AMR Dashboard Email Verification ({country})"
        msg["From"] = cfg["from_email"]
        msg["To"] = to_email
        body_text = (
            "Hello,\n\n"
            "Use the code below to verify your email for the AMR Dashboard, or click the link provided.\n\n"
            f"Verification Code: {code}\n"
            + (f"Verification Link: {link}\n\n" if link else "") +
            "This code expires in 30 minutes.\n\n"
            "Regards,\nAMR Dashboard Team"
        )
        msg.set_content(body_text)

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            if cfg["use_tls"]:
                server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.send_message(msg)
        return True, "Verification email sent"
    except Exception as e:
        return False, f"Error sending email: {str(e)}"
