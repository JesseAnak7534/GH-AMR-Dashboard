"""
Lab Management Module for KoboToolbox Integration
Handles lab user authentication, access control, and data syncing with KoboToolbox.
"""

import requests
import json
import pandas as pd
from typing import Tuple, List, Dict, Optional, Any
from datetime import datetime
import os
from dotenv import load_dotenv

# KoboToolbox API Configuration
KOBO_API_BASE = "https://kf.kobotoolbox.org/api/v2"
# Short, easy-to-type domain used for sentinel-lab logins.  Each lab has a
# fixed email of the form  <code>@icbb-amr.gh  (see LAB_LOGIN_CODES below).
LAB_EMAIL_DOMAIN = "icbb-amr.gh"
KOBO_CONFIG_PATH = os.path.join("db", "kobo_config.json")

# Short login codes for each approved lab.  These map directly to the
# usernames that per-laboratory login accounts used to carry, and are the
# values the dashboard checks at sign-in time, so changing a code here
# without re-running the provisioner will lock that lab out.
LAB_LOGIN_CODES: dict = {
    "Eastern Regional Hospital": "erh",
    "St. Martin De Porres Hospital Eikwe": "smpe",
    "Sekondi Public Health Reference Laboratory": "sphrl",
    "Ho Teaching Hospital": "hth",
    "Tamale Teaching Hospital": "tth",
    "Komfo Anokye Teaching Hospital": "kath",
    "Korle-Bu Teaching Hospital": "kbth",
    "Lekma Hospital": "lekma",
    "Sunyani Teaching Hospital": "snth",
    "Cape Coast Teaching Hospital": "ccth",
    "National Food Safety Laboratory": "nfsl",
    "CSIR – Water Research Institute (Microbiology Laboratory)": "csir",
    "Accra Veterinary Laboratory": "avl",
    "Kumasi Veterinary Laboratory": "kvl",
    "Quadushah Medical Diagnostic Limited": "qmd",
    "Central Veterinary Laboratory": "cvl",
    "Pong Tamale School": "pts",
    "Metropolis Health Care Limited": "mhc",
    "Alma Medical Laboratory Ltd": "alma",
}

# Importing src.settings loads .env from the project root. A bare
# load_dotenv() searches upward from the working directory instead, so
# launching from anywhere else left every value in .env invisible.
from src import settings as _settings  # noqa: F401
def _kobo_token() -> Optional[str]:
    """The KoboToolbox API token, read when it is needed.

    This was a module constant assigned from os.getenv at import time, which
    meant the token was found only if something else had already loaded .env --
    in practice src.db, by import order -- and was never found on Streamlit
    Cloud, where secrets are not environment variables. That produced the
    "KoboToolbox API token is not configured" error against a .env that
    contained it.
    """
    from src.settings import get_setting
    return get_setting("KOBO_API_TOKEN")

# List of approved sentinel site laboratories
APPROVED_LABS = {
    "Eastern Regional Hospital": "eastern_regional_hospital",
    "St. Martin De Porres Hospital Eikwe": "st_martin_de_porres_hospital_eikwe",
    "Sekondi Public Health Reference Laboratory": "sekondi_public_health_reference_lab",
    "Ho Teaching Hospital": "ho_teaching_hospital",
    "Tamale Teaching Hospital": "tamale_teaching_hospital",
    "Komfo Anokye Teaching Hospital": "komfo_anokye_teaching_hospital",
    "Korle-Bu Teaching Hospital": "korle_bu_teaching_hospital",
    "Lekma Hospital": "lekma_hospital",
    "Sunyani Teaching Hospital": "sunyani_teaching_hospital",
    "Cape Coast Teaching Hospital": "cape_coast_teaching_hospital",
    "National Food Safety Laboratory": "national_food_safety_laboratory",
    "CSIR – Water Research Institute (Microbiology Laboratory)": "csir_water_research_institute",
    "Accra Veterinary Laboratory": "accra_veterinary_laboratory",
    "Kumasi Veterinary Laboratory": "kumasi_veterinary_laboratory",
    "Quadushah Medical Diagnostic Limited": "quadushah_medical_diagnostic",
    "Central Veterinary Laboratory": "central_veterinary_laboratory",
    "Pong Tamale School": "pong_tamale_school",
    "Metropolis Health Care Limited": "metropolis_health_care",
    "Alma Medical Laboratory Ltd": "alma_medical_laboratory"
}

class KoboToolboxManager:
    """Manager for KoboToolbox form creation and data syncing."""
    
    def __init__(self, api_token: Optional[str] = None):
        """Initialize KoboToolbox manager with API token."""
        self.api_token = api_token or _kobo_token()
        self.session = None
        
    def authenticate(self) -> Tuple[bool, str]:
        """Authenticate with KoboToolbox API using Token Auth."""
        try:
            if not self.api_token:
                return False, (
                    "KoboToolbox API token is not configured. Add KOBO_API_TOKEN "
                    "to .env for local use, or to Settings > Secrets on "
                    "Streamlit Cloud. The token is on your KoboToolbox account "
                    "page under Account Settings > Security.")
            
            # Test authentication using Token auth on the assets endpoint
            test_url = f"{KOBO_API_BASE}/assets/"
            response = requests.get(
                test_url,
                headers={"Authorization": f"Token {self.api_token}"},
                timeout=10
            )
            
            if response.status_code == 200:
                # Authentication successful - create session with Token auth
                self.session = requests.Session()
                self.session.headers.update({
                    "Authorization": f"Token {self.api_token}",
                    "Content-Type": "application/json"
                })
                return True, "Authentication successful"
            else:
                return False, f"Authentication failed: {response.status_code} - {response.text[:200]}"
        except Exception as e:
            return False, f"Authentication error: {str(e)}"
    
    def create_amr_form(self, form_name: str = "AMR One Health Surveillance") -> Tuple[bool, str, Optional[Dict]]:
        """Create comprehensive KoboToolbox form – one form for AST, PPS, AMU, AMC data."""
        try:
            if not self.session:
                success, msg = self.authenticate()
                if not success:
                    return False, msg, None
            
            # The survey is defined in src/kobo_form.py, built from the same
            # vocabularies the validator enforces. It used to be a literal
            # here, which let the form offer values the validator rejected,
            # and asked for one antibiotic per submission with a hand-typed
            # isolate id -- so one culture tested against six drugs arrived as
            # six isolates. The new survey nests susceptibility results inside
            # isolates, which makes that impossible to record.
            from src.kobo_form import build_survey, FORM_VERSION
            survey_questions, all_choices = build_survey()
            form_name = f"{form_name} v{FORM_VERSION}"

            # Create form payload
            form_payload = {
                "name": form_name,
                "asset_type": "survey",
                "content": {
                    "survey": survey_questions,
                    "choices": all_choices
                }
            }
            
            # Create form via assets endpoint
            url = f"{KOBO_API_BASE}/assets/"
            response = self.session.post(url, json=form_payload, timeout=10)
            
            if response.status_code in [200, 201]:
                form_data = response.json()
                return True, "Form created successfully", form_data
            else:
                return False, f"Form creation failed: {response.status_code} - {response.text[:300]}", None
        
        except Exception as e:
            return False, f"Form creation error: {str(e)}", None
    
    def fetch_submitted_data(self, form_id: str) -> Tuple[bool, str, Optional[pd.DataFrame]]:
        """Fetch submitted AST data from KoboToolbox form.

        KoboToolbox paginates ``/data/`` (default 100 per page) and returns a
        ``next`` URL for each subsequent page.  Walk every page so the caller
        sees the complete submission set, not just the first 100 rows.
        """
        try:
            if not self.session:
                success, msg = self.authenticate()
                if not success:
                    return False, msg, None

            # The form_id is actually the asset UID from KoboToolbox
            # Use the correct endpoint: /api/v2/assets/{asset_uid}/data/
            url: Optional[str] = f"{KOBO_API_BASE}/assets/{form_id}/data/"
            params: Optional[Dict[str, Any]] = {"format": "json", "limit": 30000}

            all_results: list = []
            pages = 0
            while url:
                response = self.session.get(url, params=params, timeout=60)
                if response.status_code != 200:
                    return False, f"Failed to fetch data: {response.status_code} - {response.text[:200]}", None

                data = response.json()
                if isinstance(data, dict):
                    page_rows = data.get('results', [])
                    next_url = data.get('next')
                else:
                    page_rows = data or []
                    next_url = None

                all_results.extend(page_rows)
                pages += 1
                # ``next`` already carries the offset/limit query string
                url = next_url
                params = None

                # Hard ceiling so a runaway pagination loop can't hang the UI
                if pages >= 200:
                    break

            if all_results:
                df = pd.DataFrame(all_results)
                return True, f"Retrieved {len(df)} submissions", df
            return True, "No submissions found", pd.DataFrame()

        except Exception as e:
            return False, f"Data fetch error: {str(e)}", None

def is_lab_user(user_email: str, lab_mapping: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """
    Check if user email belongs to an approved lab.
    
    Args:
        user_email: User's email address
        lab_mapping: Mapping of lab names to email credentials
        
    Returns:
        Tuple of (is_lab, lab_name)
    """
    for lab_name, email in lab_mapping.items():
        if user_email.lower() == email.lower():
            return True, lab_name
    
    return False, None

def get_lab_credentials() -> Dict[str, str]:
    """Return ``{lab_name: short_username}`` for every approved lab.

    The short username is combined with :data:`LAB_EMAIL_DOMAIN` to form the
    login email (e.g. ``kbth@icbb-amr.gh``).

    Per-laboratory login accounts were retired: laboratory identity is a data
    attribute (``samples.lab_name``), not a credential. This mapping is kept
    because the login path still recognises a laboratory address if such an
    account is ever created deliberately, and because the codes are the same
    ones WHONET exports carry.
    """
    return dict(LAB_LOGIN_CODES)

def get_lab_names() -> List[str]:
    """Get list of all approved lab names for dropdown selection."""
    return sorted(APPROVED_LABS.keys())


def get_lab_email_map() -> Dict[str, str]:
    """Build mapping of lab name to lab email address."""
    credentials = get_lab_credentials()
    return {
        lab_name: f"{username}@{LAB_EMAIL_DOMAIN}"
        for lab_name, username in credentials.items()
    }


def get_lab_name_from_email(email: str) -> Optional[str]:
    """Return lab name for a given lab email, if matched."""
    email_map = get_lab_email_map()
    for lab_name, lab_email in email_map.items():
        if email.strip().lower() == lab_email.lower():
            return lab_name
    return None


def kobo_submissions_to_frames(submissions_df):
    """Convert KoboToolbox submissions into upload-contract frames.

    Returns ``(samples, isolates, ast_results)``. The previous version returned
    two frames and could not populate the isolate table at all, because the form
    it read had no concept of an isolate separate from a susceptibility test.

    The work is done by ``src.kobo_form.submissions_to_frames``, which sits
    beside the survey definition so the two cannot drift.
    """
    from src.kobo_form import submissions_to_frames
    return submissions_to_frames(submissions_df)



def save_kobo_form_id(form_id: str) -> Tuple[bool, str]:
    """Persist KoboToolbox form ID to local config file."""
    try:
        os.makedirs("db", exist_ok=True)
        payload = {
            "form_id": str(form_id).strip(),
            "updated_at": datetime.now().isoformat()
        }
        with open(KOBO_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True, "KoboToolbox form ID saved"
    except Exception as e:
        return False, f"Failed to save KoboToolbox form ID: {e}"


def load_kobo_form_id() -> Optional[str]:
    """Load KoboToolbox form ID from local config file if available."""
    try:
        if not os.path.exists(KOBO_CONFIG_PATH):
            return None
        with open(KOBO_CONFIG_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        form_id = payload.get("form_id")
        return str(form_id).strip() if form_id else None
    except Exception:
        return None
