import os
import smtplib
import ssl
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
    host = (secrets_cfg.get("SMTP_HOST") or os.getenv("SMTP_HOST") or "").lower()
    username = secrets_cfg.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME")
    from_secret = secrets_cfg.get("SMTP_FROM") or os.getenv("SMTP_FROM") or os.getenv("ADMIN_EMAIL")

    # Default from to username for better deliverability, especially on Gmail
    effective_from = from_secret or username or "no-reply@example.com"

    config = {
        "host": secrets_cfg.get("SMTP_HOST") or os.getenv("SMTP_HOST"),
        "port": int(secrets_cfg.get("SMTP_PORT") or os.getenv("SMTP_PORT", "587")),
        "username": username,
        "password": secrets_cfg.get("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD"),
        "from_email": effective_from,
        "use_tls": str(secrets_cfg.get("SMTP_USE_TLS") or os.getenv("SMTP_USE_TLS", "true")).lower() in ("1", "true", "yes"),
        "use_ssl": str(secrets_cfg.get("SMTP_USE_SSL") or os.getenv("SMTP_USE_SSL", "false")).lower() in ("1", "true", "yes"),
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
        # Optional: set Reply-To to admin
        if os.getenv("ADMIN_EMAIL"):
            msg["Reply-To"] = os.getenv("ADMIN_EMAIL")
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

        host = (cfg.get("host") or "").lower()
        use_ssl = cfg.get("use_ssl")
        use_tls = cfg.get("use_tls")
        port = cfg.get("port") or 587

        # Prefer SSL on port 465 if explicitly requested or for Gmail with port 465
        if use_ssl or ("gmail.com" in host and int(port) == 465):
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], port, context=context) as server:
                server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], port) as server:
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        return True, "Verification email sent"
    except Exception as e:
        err = str(e)
        # Provide actionable guidance for Gmail's 5.7.8 bad credentials
        if "gmail" in (cfg.get("host") or "").lower() and ("5.7.8" in err or "BadCredentials" in err or "Username and Password not accepted" in err):
            return False, (
                "Gmail SMTP rejected the credentials. Use a Gmail App Password "
                "(requires 2‑Step Verification) and set it as SMTP_PASSWORD. "
                "See https://support.google.com/mail/?p=BadCredentials"
            )
        return False, f"Error sending email: {err}"
