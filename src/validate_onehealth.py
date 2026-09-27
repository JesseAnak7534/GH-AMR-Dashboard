"""
Validation of the One Health sheets of a unified upload.

One workbook carries every submission type. The AMR sheets -- samples,
isolates, ast_results and genomics -- are defined by ``src.upload_schema`` and
checked by ``src.validate``. This module covers the remaining four sheets:
pps_survey, prescriptions, amu_data and amc_data. Users fill only the sheets
they need.
"""
import pandas as pd
from typing import Tuple, List, Dict
from io import BytesIO
from openpyxl import load_workbook
from src.lab_management import APPROVED_LABS


# ════════════════════════════════════════════════════════════════════════════
# COLUMN SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

REQUIRED_PPS_SURVEY_COLS = {
    'facility_name', 'survey_date', 'region', 'district',
    'total_patients', 'patients_on_antibiotics'
}

REQUIRED_PPS_RX_COLS = {
    'ward', 'patient_age_group', 'antibiotic_name', 'route',
    'indication', 'indication_documented', 'guideline_compliant', 'duration_days'
}

#: Columns that tie a prescription row to its survey. Optional when the workbook
#: contains exactly one survey, required beyond that -- see
#: ``attribute_prescriptions``.
PPS_RX_LINK_COLS = ('facility_name', 'survey_date')

REQUIRED_AMU_COLS = {
    'facility_name', 'report_period', 'region', 'antibiotic_name',
    'quantity_dispensed'
}

REQUIRED_AMC_COLS = {
    'report_period', 'sector', 'antibiotic_class', 'quantity_kg'
}



# ════════════════════════════════════════════════════════════════════════════
# PPS PRESCRIPTION ATTRIBUTION
# ════════════════════════════════════════════════════════════════════════════

def _normalise_key(value) -> str:
    text = "" if value is None else str(value).strip()
    return text[:10] if text[:4].isdigit() and "-" in text[:10] else text.lower()


def attribute_prescriptions(survey_df: pd.DataFrame,
                            rx_df: pd.DataFrame) -> Tuple[Dict[int, pd.DataFrame], List[str]]:
    """Assign each prescription row to the survey it belongs to.

    Returns a mapping of survey row position to its prescriptions, plus any
    errors.

    The upload page previously divided the prescriptions sheet into equal blocks
    by row position and handed one block to each survey in turn. With two
    surveys and seven prescriptions that gave three rows to each and discarded
    the seventh, and it attributed every prescription to whichever facility
    happened to occupy the same position in the other sheet. The facility, ward
    mix and compliance figures of a multi-facility PPS were therefore wrong in a
    way nothing in the output revealed.

    Attribution is now by key. One survey takes every prescription, which is
    unambiguous. More than one survey requires the prescriptions sheet to name
    its facility, and a row that matches no survey is reported rather than
    assigned to a neighbour.
    """
    errors: List[str] = []
    if survey_df is None or survey_df.empty:
        return {}, ["[PPS] No survey rows to attribute prescriptions to."]
    if rx_df is None or rx_df.empty:
        return {i: rx_df.iloc[0:0] for i in range(len(survey_df))}, errors

    if len(survey_df) == 1:
        return {0: rx_df.copy()}, errors

    if 'facility_name' not in rx_df.columns:
        return {}, [
            "[PPS] The workbook holds "
            f"{len(survey_df)} surveys, so each prescription must say which "
            "facility it belongs to. Add a 'facility_name' column to the "
            "prescriptions sheet (and 'survey_date' if one facility was "
            "surveyed more than once). Prescriptions are not split by row "
            "order, because that would attribute them to the wrong facility."
        ]

    use_date = ('survey_date' in rx_df.columns
                and 'survey_date' in survey_df.columns)

    def key_of(facility, date=None):
        parts = [_normalise_key(facility)]
        if use_date:
            parts.append(_normalise_key(date))
        return tuple(parts)

    survey_keys: Dict[tuple, List[int]] = {}
    for position, (_, srow) in enumerate(survey_df.iterrows()):
        key = key_of(srow.get('facility_name'), srow.get('survey_date'))
        survey_keys.setdefault(key, []).append(position)

    ambiguous = {k: v for k, v in survey_keys.items() if len(v) > 1}
    if ambiguous:
        label = "; ".join(" / ".join(str(part) for part in k) for k in ambiguous)
        hint = ("" if use_date else
                " Add a 'survey_date' column to the prescriptions sheet to tell "
                "them apart.")
        errors.append(
            f"[PPS] More than one survey shares the same identity ({label}), so "
            f"prescriptions cannot be attributed unambiguously.{hint}")
        return {}, errors

    rx_keys = [key_of(r.get('facility_name'), r.get('survey_date'))
               for _, r in rx_df.iterrows()]
    assigned: Dict[int, List[int]] = {i: [] for i in range(len(survey_df))}
    unmatched: Dict[tuple, int] = {}
    for row_index, key in zip(rx_df.index, rx_keys):
        positions = survey_keys.get(key)
        if positions:
            assigned[positions[0]].append(row_index)
        else:
            unmatched[key] = unmatched.get(key, 0) + 1

    for key, count in sorted(unmatched.items(), key=lambda kv: -kv[1])[:5]:
        errors.append(
            f"[PPS] {count} prescription row(s) name "
            f"'{' / '.join(str(part) for part in key)}', which matches no "
            "survey on the pps_survey sheet.")

    empty = [position for position, rows in assigned.items() if not rows]
    for position in empty[:5]:
        facility = survey_df.iloc[position].get('facility_name')
        errors.append(
            f"[PPS] The survey for '{facility}' has no prescriptions attributed "
            "to it. Check the spelling of facility_name on the prescriptions "
            "sheet.")

    return ({position: rx_df.loc[rows] for position, rows in assigned.items()},
            errors)

# ════════════════════════════════════════════════════════════════════════════
# UNIFIED VALIDATOR  –  detects which sheets are present, validates each
# ════════════════════════════════════════════════════════════════════════════

def validate_unified_upload(file_obj) -> Tuple[bool, List[str], Dict]:
    """
    Validate a unified One Health Excel upload.

    Returns (ok, errors, result_dict) where result_dict may contain:
        'pps_survey'       -> dict   (single survey row)
        'pps_prescriptions'-> DataFrame
        'amu_data'         -> DataFrame
        'amc_data'         -> DataFrame
    Only keys for detected sheets are present.
    """
    errors: List[str] = []
    result: Dict = {}
    found_any = False

    try:
        wb = load_workbook(file_obj, read_only=True)
        sheets = wb.sheetnames
        wb.close()
    except Exception as e:
        return False, [f"Cannot read Excel file: {e}"], {}

    # ── PPS (needs both sheets) ─────────────────────────────────────────
    if 'pps_survey' in sheets and 'prescriptions' in sheets:
        found_any = True
        file_obj.seek(0)
        survey_df = pd.read_excel(file_obj, sheet_name='pps_survey')
        file_obj.seek(0)
        rx_df = pd.read_excel(file_obj, sheet_name='prescriptions')

        if survey_df.empty:
            errors.append("[PPS] pps_survey sheet is empty")
        else:
            missing = REQUIRED_PPS_SURVEY_COLS - set(survey_df.columns)
            if missing:
                errors.append(f"[PPS] Missing pps_survey columns: {', '.join(sorted(missing))}")
            else:
                result['pps_survey'] = survey_df

        if rx_df.empty:
            errors.append("[PPS] prescriptions sheet is empty")
        else:
            missing = REQUIRED_PPS_RX_COLS - set(rx_df.columns)
            if missing:
                errors.append(f"[PPS] Missing prescriptions columns: {', '.join(sorted(missing))}")
            else:
                result['pps_prescriptions'] = rx_df

    elif 'pps_survey' in sheets or 'prescriptions' in sheets:
        errors.append("[PPS] Both 'pps_survey' and 'prescriptions' sheets are needed for PPS data")

    # ── AMU ─────────────────────────────────────────────────────────────
    if 'amu_data' in sheets:
        found_any = True
        file_obj.seek(0)
        amu_df = pd.read_excel(file_obj, sheet_name='amu_data')
        if amu_df.empty:
            errors.append("[AMU] amu_data sheet is empty")
        else:
            missing = REQUIRED_AMU_COLS - set(amu_df.columns)
            if missing:
                errors.append(f"[AMU] Missing columns: {', '.join(sorted(missing))}")
            else:
                for col in ['quantity_dispensed']:
                    if col in amu_df.columns:
                        bad = pd.to_numeric(amu_df[col], errors='coerce').isna() & amu_df[col].notna()
                        if bad.any():
                            errors.append(f"[AMU] Non-numeric values in {col}")
                if not errors or not any('[AMU]' in e for e in errors):
                    result['amu_data'] = amu_df

    # ── AMC ─────────────────────────────────────────────────────────────
    if 'amc_data' in sheets:
        found_any = True
        file_obj.seek(0)
        amc_df = pd.read_excel(file_obj, sheet_name='amc_data')
        if amc_df.empty:
            errors.append("[AMC] amc_data sheet is empty")
        else:
            missing = REQUIRED_AMC_COLS - set(amc_df.columns)
            if missing:
                errors.append(f"[AMC] Missing columns: {', '.join(sorted(missing))}")
            else:
                for col in ['quantity_kg', 'biomass_kg', 'mg_per_kg_biomass']:
                    if col in amc_df.columns:
                        bad = pd.to_numeric(amc_df[col], errors='coerce').isna() & amc_df[col].notna()
                        if bad.any():
                            errors.append(f"[AMC] Non-numeric values in {col}")
                valid_sectors = {'ANIMAL', 'AQUACULTURE'}
                if 'sector' in amc_df.columns:
                    inv = amc_df[~amc_df['sector'].isin(valid_sectors)]['sector'].dropna().unique()
                    if len(inv) > 0:
                        errors.append(f"[AMC] Invalid sector values: {', '.join(str(s) for s in inv)}")
                if not any('[AMC]' in e for e in errors):
                    result['amc_data'] = amc_df

    if not found_any:
        errors.append(
            "No recognised One Health sheets found. "
            "Expected some of: pps_survey, prescriptions, amu_data, amc_data"
        )

    return len(errors) == 0, errors, result


# ════════════════════════════════════════════════════════════════════════════
# UNIFIED TEMPLATE  –  one Excel file, 6 sheets
# ════════════════════════════════════════════════════════════════════════════

def create_unified_template() -> bytes:
    """Generate ONE Excel workbook covering every submission type.

    The AMR sheets -- samples, isolates, ast_results and genomics -- are built by
    ``src.upload_template`` from the single column contract in
    ``src.upload_schema``, which is also what the validator enforces. This
    function used to define its own ``samples`` and ``ast_results`` columns, so
    the workbook people downloaded and the format the validator accepted could
    and did diverge. The One Health sheets below are appended to that workbook.
    """
    from src.upload_template import build_template

    lab_names = sorted(APPROVED_LABS.keys())

    # ── PPS ─────────────────────────────────────────────────────────────
    pps_survey = pd.DataFrame({
        'facility_name': ['Korle-Bu Teaching Hospital'],
        'survey_date': ['2026-03-15'],
        'region': ['Greater Accra'],
        'district': ['Accra Metropolis'],
        'total_patients': [120],
        'patients_on_antibiotics': [45],
    })

    prescriptions = pd.DataFrame({
        # These two tie each prescription to its survey. They may be left blank
        # when the workbook holds a single survey; with more than one they are
        # required, because prescriptions are never split by row order.
        'facility_name': ['Korle-Bu Teaching Hospital'] * 3,
        'survey_date': ['2026-03-15'] * 3,
        'ward': ['Medical', 'Surgical', 'Paediatric'],
        'patient_age_group': ['Adult (25-44)', 'Geriatric (65+)', 'Child (5-14)'],
        'antibiotic_name': ['Amoxicillin', 'Ceftriaxone', 'Metronidazole'],
        'route': ['Oral', 'IV', 'Oral'],
        'indication': ['Community-acquired pneumonia', 'Surgical prophylaxis',
                       'Intra-abdominal infection'],
        'indication_documented': [1, 1, 0],
        'guideline_compliant': [1, 0, 1],
        'duration_days': [7, 1, 5],
    })

    # ── AMU ─────────────────────────────────────────────────────────────
    amu = pd.DataFrame({
        'facility_name': ['Korle-Bu Teaching Hospital', 'Korle-Bu Teaching Hospital',
                          'Tamale Teaching Hospital'],
        'report_period': ['2026-Q1', '2026-Q1', '2026-Q1'],
        'region': ['Greater Accra', 'Greater Accra', 'Northern'],
        'district': ['Accra Metropolis', 'Accra Metropolis', 'Tamale Metropolis'],
        'sector': ['HUMAN', 'HUMAN', 'HUMAN'],
        'antibiotic_name': ['Amoxicillin', 'Ciprofloxacin', 'Ceftriaxone'],
        'atc_code': ['J01CA04', 'J01MA02', 'J01DD04'],
        'formulation': ['500mg capsule', '500mg tablet', '1g injection'],
        'unit_of_measure': ['DDD', 'DDD', 'DDD'],
        'quantity_dispensed': [1500, 800, 350],
        'ddd_per_1000': [45.2, 22.1, 12.8],
        'patient_days': [33200, 33200, 15600],
    })

    # ── AMC ─────────────────────────────────────────────────────────────
    amc = pd.DataFrame({
        'report_period': ['2026-Q1', '2026-Q1', '2026-Q1'],
        'region': ['Greater Accra', 'Ashanti', 'Northern'],
        'sector': ['ANIMAL', 'ANIMAL', 'AQUACULTURE'],
        'species': ['Poultry', 'Bovine', 'Tilapia'],
        'production_type': ['Broiler', 'Dairy', 'Farm'],
        'antibiotic_class': ['Tetracyclines', 'Penicillins', 'Fluoroquinolones'],
        'antibiotic_name': ['Oxytetracycline', 'Amoxicillin', 'Enrofloxacin'],
        'atc_vet_code': ['QJ01AA06', 'QJ01CA04', 'QJ01MA90'],
        'quantity_kg': [120.5, 45.0, 8.2],
        'biomass_kg': [500000, 300000, 100000],
        'mg_per_kg_biomass': [241.0, 150.0, 82.0],
        'route': ['Oral (water)', 'Injection', 'Oral (feed)'],
        'purpose': ['Therapeutic', 'Therapeutic', 'Prophylactic'],
    })

    return build_template(
        lab_names=lab_names,
        extra_sheets=(
            ('pps_survey', pps_survey, '548235'),
            ('prescriptions', prescriptions, '70AD47'),
            ('amu_data', amu, 'BF8F00'),
            ('amc_data', amc, 'C55A11'),
        ),
    )


# ════════════════════════════════════════════════════════════════════════════
# Legacy single-module templates (kept for backward compat in dashboard tabs)
# ════════════════════════════════════════════════════════════════════════════

def create_pps_template() -> bytes:
    pps_survey = pd.DataFrame({
        'facility_name': ['Korle-Bu Teaching Hospital'],
        'survey_date': ['2026-03-15'],
        'region': ['Greater Accra'],
        'district': ['Accra Metropolis'],
        'total_patients': [120],
        'patients_on_antibiotics': [45],
    })
    rx = pd.DataFrame({
        'ward': ['Medical', 'Surgical', 'Paediatric'],
        'patient_age_group': ['Adult (25-44)', 'Geriatric (65+)', 'Child (5-14)'],
        'antibiotic_name': ['Amoxicillin', 'Ceftriaxone', 'Metronidazole'],
        'route': ['Oral', 'IV', 'Oral'],
        'indication': ['Community-acquired pneumonia', 'Surgical prophylaxis', 'Intra-abdominal infection'],
        'indication_documented': [1, 1, 0],
        'guideline_compliant': [1, 0, 1],
        'duration_days': [7, 1, 5],
    })
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        pps_survey.to_excel(w, sheet_name='pps_survey', index=False)
        rx.to_excel(w, sheet_name='prescriptions', index=False)
    return buf.getvalue()


def create_amu_template() -> bytes:
    data = pd.DataFrame({
        'facility_name': ['Korle-Bu Teaching Hospital', 'Tamale Teaching Hospital'],
        'report_period': ['2026-Q1', '2026-Q1'],
        'region': ['Greater Accra', 'Northern'],
        'district': ['Accra Metropolis', 'Tamale Metropolis'],
        'sector': ['HUMAN', 'HUMAN'],
        'antibiotic_name': ['Amoxicillin', 'Ceftriaxone'],
        'atc_code': ['J01CA04', 'J01DD04'],
        'formulation': ['500mg capsule', '1g injection'],
        'unit_of_measure': ['DDD', 'DDD'],
        'quantity_dispensed': [1500, 350],
        'ddd_per_1000': [45.2, 12.8],
        'patient_days': [33200, 15600],
    })
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        data.to_excel(w, sheet_name='amu_data', index=False)
    return buf.getvalue()


def create_amc_template() -> bytes:
    data = pd.DataFrame({
        'report_period': ['2026-Q1', '2026-Q1'],
        'region': ['Greater Accra', 'Ashanti'],
        'sector': ['ANIMAL', 'AQUACULTURE'],
        'species': ['Poultry', 'Tilapia'],
        'production_type': ['Broiler', 'Farm'],
        'antibiotic_class': ['Tetracyclines', 'Fluoroquinolones'],
        'antibiotic_name': ['Oxytetracycline', 'Enrofloxacin'],
        'atc_vet_code': ['QJ01AA06', 'QJ01MA90'],
        'quantity_kg': [120.5, 8.2],
        'biomass_kg': [500000, 100000],
        'mg_per_kg_biomass': [241.0, 82.0],
        'route': ['Oral (water)', 'Oral (feed)'],
        'purpose': ['Therapeutic', 'Prophylactic'],
    })
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        data.to_excel(w, sheet_name='amc_data', index=False)
    return buf.getvalue()


# Legacy aliases
def validate_pps_upload(file_obj):
    """Legacy: validate PPS-only upload via unified validator."""
    ok, errs, result = validate_unified_upload(file_obj)
    survey = result.get('pps_survey', {})
    rx = result.get('pps_prescriptions', pd.DataFrame())
    return ok, errs, survey, rx

def validate_amu_upload(file_obj):
    ok, errs, result = validate_unified_upload(file_obj)
    return ok, errs, result.get('amu_data', pd.DataFrame())

def validate_amc_upload(file_obj):
    ok, errs, result = validate_unified_upload(file_obj)
    return ok, errs, result.get('amc_data', pd.DataFrame())
