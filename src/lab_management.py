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

load_dotenv()
KOBO_USERNAME = os.getenv("KOBO_USERNAME")
KOBO_PASSWORD = os.getenv("KOBO_PASSWORD")

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
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        """Initialize KoboToolbox manager with credentials."""
        self.username = username or KOBO_USERNAME
        self.password = password or KOBO_PASSWORD
        self.session = None
        self.auth_token = None
        
    def authenticate(self) -> Tuple[bool, str]:
        """Authenticate with KoboToolbox API."""
        try:
            if not self.username or not self.password:
                return False, "KoboToolbox credentials are not configured. Set KOBO_USERNAME and KOBO_PASSWORD."
            auth_url = f"{KOBO_API_BASE}/auth/login/"
            response = requests.post(
                auth_url,
                json={"username": self.username, "password": self.password},
                timeout=10
            )
            
            if response.status_code == 200:
                self.auth_token = response.json().get("token")
                self.session = requests.Session()
                self.session.headers.update({
                    "Authorization": f"Token {self.auth_token}",
                    "Content-Type": "application/json"
                })
                return True, "Authentication successful"
            else:
                return False, f"Authentication failed: {response.text}"
        except Exception as e:
            return False, f"Authentication error: {str(e)}"
    
    def create_amr_form(self, form_name: str = "AMR Surveillance Data Entry") -> Tuple[bool, str, Optional[Dict]]:
        """Create KoboToolbox form for AMR data entry."""
        try:
            if not self.session:
                success, msg = self.authenticate()
                if not success:
                    return False, msg, None
            
            # Form definition in XLSForm format
            form_definition = {
                "title": form_name,
                "name": form_name.lower().replace(" ", "_"),
                "sections": [
                    {
                        "name": "lab_info",
                        "label": "Laboratory Information",
                        "fields": [
                            {
                                "name": "lab_name",
                                "label": "Select Your Laboratory",
                                "type": "select_one",
                                "required": True,
                                "options": list(APPROVED_LABS.keys())
                            },
                            {
                                "name": "collection_date",
                                "label": "Sample Collection Date",
                                "type": "date",
                                "required": True
                            }
                        ]
                    },
                    {
                        "name": "sample_info",
                        "label": "Sample Information",
                        "fields": [
                            {
                                "name": "sample_id",
                                "label": "Sample ID",
                                "type": "text",
                                "required": True
                            },
                            {
                                "name": "source_category",
                                "label": "Source Category",
                                "type": "select_one",
                                "required": True,
                                "options": ["ENVIRONMENT", "FOOD", "HUMAN", "ANIMAL", "AQUACULTURE"]
                            },
                            {
                                "name": "source_type",
                                "label": "Source Type",
                                "type": "text",
                                "required": True
                            },
                            {
                                "name": "region",
                                "label": "Region",
                                "type": "text",
                                "required": True
                            },
                            {
                                "name": "district",
                                "label": "District",
                                "type": "text",
                                "required": True
                            }
                        ]
                    },
                    {
                        "name": "ast_results",
                        "label": "Antibiotic Susceptibility Testing Results",
                        "fields": [
                            {
                                "name": "isolate_id",
                                "label": "Isolate ID",
                                "type": "text",
                                "required": True
                            },
                            {
                                "name": "organism",
                                "label": "Organism",
                                "type": "text",
                                "required": True
                            },
                            {
                                "name": "antibiotic",
                                "label": "Antibiotic Tested",
                                "type": "text",
                                "required": True
                            },
                            {
                                "name": "result",
                                "label": "AST Result",
                                "type": "select_one",
                                "required": True,
                                "options": ["S", "I", "R"]
                            },
                            {
                                "name": "method",
                                "label": "Testing Method",
                                "type": "select_one",
                                "required": True,
                                "options": ["DD", "MIC"]
                            },
                            {
                                "name": "guideline",
                                "label": "Breakpoint Guideline",
                                "type": "select_one",
                                "required": True,
                                "options": ["CLSI", "EUCAST"]
                            },
                            {
                                "name": "test_date",
                                "label": "Test Date",
                                "type": "date",
                                "required": True
                            }
                        ]
                    }
                ]
            }
            
            # Create form via API
            url = f"{KOBO_API_BASE}/forms/"
            response = self.session.post(url, json=form_definition, timeout=10)
            
            if response.status_code in [200, 201]:
                form_data = response.json()
                return True, "Form created successfully", form_data
            else:
                return False, f"Form creation failed: {response.text}", None
        
        except Exception as e:
            return False, f"Form creation error: {str(e)}", None
    
    def fetch_submitted_data(self, form_id: str) -> Tuple[bool, str, Optional[pd.DataFrame]]:
        """Fetch submitted AST data from KoboToolbox form."""
        try:
            if not self.session:
                success, msg = self.authenticate()
                if not success:
                    return False, msg, None
            
            url = f"{KOBO_API_BASE}/data/{form_id}/"
            response = self.session.get(url, params={"format": "json"}, timeout=10)
            
            if response.status_code == 200:
                submissions = response.json()
                
                # Convert to DataFrame
                if submissions:
                    df = pd.DataFrame(submissions)
                    return True, f"Retrieved {len(df)} submissions", df
                else:
                    return True, "No submissions found", pd.DataFrame()
            else:
                return False, f"Failed to fetch data: {response.text}", None
        
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
    if submissions_df is None or submissions_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Normalize column names
    df = submissions_df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Build samples dataframe
    samples_cols = {
        'sample_id': 'sample_id',
        'lab_name': 'lab_name',
        'collection_date': 'collection_date',
        'region': 'region',
        'district': 'district',
        'source_category': 'source_category',
        'source_type': 'source_type'
    }

    samples_df = pd.DataFrame({
        key: df.get(src) for key, src in samples_cols.items()
    })

    samples_df['site_type'] = 'Laboratory'
    samples_df['food_matrix'] = ''
    samples_df['environment_matrix'] = ''
    samples_df['latitude'] = None
    samples_df['longitude'] = None

    # Remove duplicates by sample_id and lab_name
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

    ast_df = pd.DataFrame({
        key: df.get(src) for key, src in ast_cols.items()
    })

    ast_df['mic_value'] = None
    ast_df['zone_diameter'] = None

    return samples_df, ast_df
