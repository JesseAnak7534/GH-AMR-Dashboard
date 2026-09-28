# Streamlit Cloud secrets

The deployed app reads configuration from Streamlit's secrets store. Local
development reads the same names from `.env`. Both go through
`src/settings.py`, which checks the environment first and secrets second.

Open the app on share.streamlit.io, then **Settings → Secrets**, and paste the
block below with your own values substituted. Streamlit restarts the app when
you save.

```toml
# ---- required: the app will not start without these -------------------------
DATABASE_URL       = "postgresql://postgres.<ref>:<password>@aws-1-eu-north-1.pooler.supabase.com:5432/postgres"
AMRSS_PATIENT_SALT = "<copy from .env exactly — see the warning below>"
ADMIN_EMAIL        = "<your admin email>"
ADMIN_PASSWORD     = "<your admin password>"

# ---- KoboToolbox sync -------------------------------------------------------
KOBO_API_TOKEN     = "<40-character token from KoboToolbox>"

# ---- email: verification, password reset, scheduled reports -----------------
SMTP_SERVER        = "smtp.gmail.com"
SMTP_PORT          = "587"
SMTP_USERNAME      = "<the sending account>"
SMTP_PASSWORD      = "<a Gmail App Password, 16 characters — not the account password>"
SMTP_FROM_NAME     = "AMR Surveillance Dashboard"

# ---- optional ---------------------------------------------------------------
SESSION_TIMEOUT_MINUTES = "30"
APP_BASE_URL            = "https://<your-app>.streamlit.app"
```

## Notes that matter

**`AMRSS_PATIENT_SALT` must match local exactly.** Patient pseudonyms are a
salted hash. A different salt produces different pseudonyms for the same
patient, which silently breaks the linkage between a patient's specimens and
makes first-isolate deduplication wrong. Copy it; never regenerate it.

**The database password must be percent-encoded.** A `@` in the password has to
appear as `%40`, or the URL parser reads it as the host separator.

**`sslmode` is added automatically** for any non-local host, and must not be
removed. If the app reports that the database refused an encrypted connection,
that is the platform protecting the data, not a configuration error — see the
message it prints.

**Gmail needs an App Password.** A normal account password will be rejected for
SMTP. Generate one at Google Account → Security → 2-Step Verification → App
passwords. It is 16 characters with no spaces.

## Getting the KoboToolbox API token

1. Sign in at <https://kf.kobotoolbox.org>.
2. Click your initials, top right, then **Account Settings**.
3. Open the **Security** tab.
4. Under **API Key**, reveal and copy the token. It is 40 hexadecimal
   characters.

Direct link once signed in: <https://kf.kobotoolbox.org/#/account/security>

The token is equivalent to your KoboToolbox password: it can read and delete
your forms and submissions. Keep it out of the repository — `.env` is
gitignored, and Streamlit secrets are not part of the repository. If it leaks,
regenerate it on the same page; the old one stops working immediately.

## Checking it worked

After saving secrets and letting the app restart, open **Data Management →
Admin - Datasets → KoboToolbox Sync**. A configured token shows the sync
controls rather than "KoboToolbox API token is not configured".
