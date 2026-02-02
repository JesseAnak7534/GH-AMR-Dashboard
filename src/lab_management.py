"""
Lab Management Module for KoboToolbox Integration
Handles lab user authentication, access control, and data syncing with KoboToolbox.
"""

import requests
import json
import pandas as pd
from typing import Tuple, List, Dict, Optional
from datetime import datetime
import os
from dotenv import load_dotenv

# KoboToolbox API Configuration
KOBO_API_BASE = "https://kf.kobotoolbox.org/api/v2"
LAB_EMAIL_DOMAIN = "sentinel-amr.lab"
KOBO_CONFIG_PATH = os.path.join("db", "kobo_config.json")

load_dotenv()
KOBO_API_TOKEN = os.getenv("KOBO_API_TOKEN")

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
        self.api_token = api_token or KOBO_API_TOKEN
        self.session = None
        
    def authenticate(self) -> Tuple[bool, str]:
        """Authenticate with KoboToolbox API using Token Auth."""
        try:
            if not self.api_token:
                return False, "KoboToolbox API token is not configured. Set KOBO_API_TOKEN."
            
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
    
    def create_amr_form(self, form_name: str = "AMR Surveillance Data Entry") -> Tuple[bool, str, Optional[Dict]]:
        """Create KoboToolbox form for AMR data entry with all required fields."""
        try:
            if not self.session:
                success, msg = self.authenticate()
                if not success:
                    return False, msg, None
            
            # Build all lab choices
            lab_choices = [
                {"list_name": "approved_labs", "name": lab_code, "label": lab_name}
                for lab_name, lab_code in APPROVED_LABS.items()
            ]
            
            # Build survey questions for samples data
            survey_questions = [
                # Laboratory Information
                {
                    "type": "select_one approved_labs",
                    "name": "lab_name",
                    "label": "Select Your Laboratory",
                    "required": "true"
                },
                {
                    "type": "date",
                    "name": "collection_date",
                    "label": "Sample Collection Date",
                    "required": "true"
                },
                # Sample Information
                {
                    "type": "text",
                    "name": "sample_id",
                    "label": "Sample ID",
                    "required": "true"
                },
                {
                    "type": "select_one source_categories",
                    "name": "source_category",
                    "label": "Source Category (ENVIRONMENT, FOOD, HUMAN, ANIMAL, AQUACULTURE)",
                    "required": "true"
                },
                {
                    "type": "text",
                    "name": "source_type",
                    "label": "Source Type",
                    "required": "true"
                },
                {
                    "type": "text",
                    "name": "region",
                    "label": "Region",
                    "required": "true"
                },
                {
                    "type": "text",
                    "name": "district",
                    "label": "District",
                    "required": "true"
                },
                {
                    "type": "text",
                    "name": "site_type",
                    "label": "Site Type",
                    "required": "false"
                },
                {
                    "type": "text",
                    "name": "food_matrix",
                    "label": "Food Matrix (if applicable)",
                    "required": "false"
                },
                {
                    "type": "text",
                    "name": "environment_matrix",
                    "label": "Environment Matrix (if applicable)",
                    "required": "false"
                },
                {
                    "type": "geopoint",
                    "name": "geolocation",
                    "label": "Sample Collection Location (automatically captures GPS coordinates)",
                    "required": "false"
                },
                # AST Results Information
                {
                    "type": "text",
                    "name": "isolate_id",
                    "label": "Isolate ID",
                    "required": "true"
                },
                {
                    "type": "text",
                    "name": "organism",
                    "label": "Organism",
                    "required": "true"
                },
                {
                    "type": "text",
                    "name": "antibiotic",
                    "label": "Antibiotic Tested",
                    "required": "true"
                },
                {
                    "type": "select_one ast_results",
                    "name": "result",
                    "label": "AST Result (S/I/R)",
                    "required": "true"
                },
                {
                    "type": "select_one testing_methods",
                    "name": "method",
                    "label": "Testing Method (DD/MIC)",
                    "required": "true"
                },
                {
                    "type": "select_one guidelines",
                    "name": "guideline",
                    "label": "Breakpoint Guideline (CLSI/EUCAST)",
                    "required": "true"
                },
                {
                    "type": "date",
                    "name": "test_date",
                    "label": "Test Date",
                    "required": "true"
                },
                {
                    "type": "decimal",
                    "name": "mic_value",
                    "label": "MIC Value (if applicable)",
                    "required": "false"
                },
                {
                    "type": "decimal",
                    "name": "zone_diameter",
                    "label": "Zone Diameter in mm (if applicable)",
                    "required": "false"
                }
            ]
            
            # Build all choice options
            all_choices = lab_choices + [
                {"list_name": "source_categories", "name": "env", "label": "ENVIRONMENT"},
                {"list_name": "source_categories", "name": "food", "label": "FOOD"},
                {"list_name": "source_categories", "name": "human", "label": "HUMAN"},
                {"list_name": "source_categories", "name": "animal", "label": "ANIMAL"},
                {"list_name": "source_categories", "name": "aqua", "label": "AQUACULTURE"},
                {"list_name": "ast_results", "name": "s", "label": "S"},
                {"list_name": "ast_results", "name": "i", "label": "I"},
                {"list_name": "ast_results", "name": "r", "label": "R"},
                {"list_name": "testing_methods", "name": "dd", "label": "DD"},
                {"list_name": "testing_methods", "name": "mic", "label": "MIC"},
                {"list_name": "guidelines", "name": "clsi", "label": "CLSI"},
                {"list_name": "guidelines", "name": "eucast", "label": "EUCAST"},
            ]
            
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
        """Fetch submitted AST data from KoboToolbox form."""
        try:
            if not self.session:
                success, msg = self.authenticate()
                if not success:
                    return False, msg, None
            
            # The form_id is actually the asset UID from KoboToolbox
            # Use the correct endpoint: /api/v2/assets/{asset_uid}/data/
            url = f"{KOBO_API_BASE}/assets/{form_id}/data/"
            response = self.session.get(url, params={"format": "json"}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract results from paginated response
                results = data.get('results', []) if isinstance(data, dict) else data
                
                # Convert to DataFrame
                if results:
                    df = pd.DataFrame(results)
                    return True, f"Retrieved {len(df)} submissions", df
                else:
                    return True, "No submissions found", pd.DataFrame()
            else:
                return False, f"Failed to fetch data: {response.status_code} - {response.text[:200]}", None
        
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
    """
    Get lab credentials from configuration.
    Format: {lab_name: username}
    
    These are pre-configured lab usernames. Passwords are managed separately.
    """
    return {
        "Eastern Regional Hospital": "eastern_regional_hospital",
        "St. Martin De Porres Hospital Eikwe": "st_martin_de_porres_hospital",
        "Sekondi Public Health Reference Laboratory": "sekondi_public_health_lab",
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


def kobo_submissions_to_frames(submissions_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Convert KoboToolbox submissions to samples and AST dataframes."""
    if submissions_df is None or (isinstance(submissions_df, pd.DataFrame) and submissions_df.empty):
        return pd.DataFrame(), pd.DataFrame()

    # Define mappings from choice codes to proper labels
    choice_mappings = {
        'source_category': {'env': 'ENVIRONMENT', 'food': 'FOOD', 'human': 'HUMAN', 'animal': 'ANIMAL', 'aqua': 'AQUACULTURE'},
        'result': {'s': 'S', 'i': 'I', 'r': 'R'},
        'method': {'dd': 'DD', 'mic': 'MIC'},
        'guideline': {'clsi': 'CLSI', 'eucast': 'EUCAST'},
        'lab_name': {v: k for k, v in APPROVED_LABS.items()}  # Map code back to full lab name
    }
    
    # Handle both raw API dict responses and pre-converted DataFrames
    if isinstance(submissions_df, dict):
        # If it's a paginated response from the API
        if 'results' in submissions_df:
            if not submissions_df['results']:
                return pd.DataFrame(), pd.DataFrame()
            df = pd.DataFrame(submissions_df['results'])
        else:
            # Single row dict
            df = pd.DataFrame([submissions_df])
    else:
        df = submissions_df.copy() if isinstance(submissions_df, pd.DataFrame) else pd.DataFrame(submissions_df)
    
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]
    
    # Apply choice mappings to convert codes to labels
    for col, mapping in choice_mappings.items():
        if col in df.columns:
            df[col] = df[col].map(lambda x: mapping.get(str(x).lower(), x) if pd.notna(x) else x)

    # Build samples dataframe - extract only available columns
    samples_cols = {
        'sample_id': 'sample_id',
        'lab_name': 'lab_name',
        'collection_date': 'collection_date',
        'region': 'region',
        'district': 'district',
        'source_category': 'source_category',
        'source_type': 'source_type'
    }

    # Only include columns that exist in the dataframe
    available_samples_cols = {k: v for k, v in samples_cols.items() if v in df.columns}
    
    samples_df = pd.DataFrame({
        key: df[src] for key, src in available_samples_cols.items()
    })
    
    # Add missing columns with default values
    for col in ['site_type', 'food_matrix', 'environment_matrix', 'latitude', 'longitude']:
        if col not in samples_df.columns:
            if col in ['latitude', 'longitude']:
                samples_df[col] = None
            else:
                samples_df[col] = ''
    
    # Parse geopoint field if present (format: "latitude longitude altitude precision")
    if 'geolocation' in df.columns:
        def parse_geopoint(geopoint_str):
            """Parse geopoint string to latitude and longitude."""
            if pd.isna(geopoint_str) or geopoint_str == '':
                return None, None
            try:
                parts = str(geopoint_str).strip().split()
                if len(parts) >= 2:
                    lat = float(parts[0])
                    lon = float(parts[1])
                    return lat, lon
            except (ValueError, IndexError):
                pass
            return None, None
        
        geopoint_data = df['geolocation'].apply(parse_geopoint)
        samples_df['latitude'] = [x[0] for x in geopoint_data]
        samples_df['longitude'] = [x[1] for x in geopoint_data]
    
    samples_df['site_type'] = df['site_type'].fillna('Laboratory') if 'site_type' in df.columns else 'Laboratory'
    samples_df['food_matrix'] = df['food_matrix'].fillna('') if 'food_matrix' in df.columns else ''
    samples_df['environment_matrix'] = df['environment_matrix'].fillna('') if 'environment_matrix' in df.columns else ''

    # Remove duplicates by sample_id
    if 'sample_id' in samples_df.columns:
        samples_df = samples_df.drop_duplicates(subset=['sample_id'])

    # Build AST dataframe
    ast_cols = {
        'sample_id': 'sample_id',
        'isolate_id': 'isolate_id',
        'organism': 'organism',
        'antibiotic': 'antibiotic',
        'result': 'result',
        'method': 'method',
        'guideline': 'guideline',
        'test_date': 'test_date'
    }

    # Only include columns that exist
    available_ast_cols = {k: v for k, v in ast_cols.items() if v in df.columns}
    
    ast_df = pd.DataFrame({
        key: df[src] for key, src in available_ast_cols.items()
    })
    
    # Add missing columns and convert numeric fields
    ast_df['mic_value'] = pd.to_numeric(df['mic_value'], errors='coerce') if 'mic_value' in df.columns else None
    ast_df['zone_diameter'] = pd.to_numeric(df['zone_diameter'], errors='coerce') if 'zone_diameter' in df.columns else None

    return samples_df, ast_df


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
