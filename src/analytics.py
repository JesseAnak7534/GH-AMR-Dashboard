"""
Advanced Analytics Module for AMR Surveillance Dashboard.
Provides comprehensive epidemiological analysis and predictions.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta


# ============================================================================
# RESISTANCE MECHANISM DETECTION
# ============================================================================

def detect_esbl_patterns(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect Extended-Spectrum Beta-Lactamase (ESBL) patterns."""
    if ast_df.empty:
        return pd.DataFrame()
    
    esbl_indicators = []
    
    # ESBL screening antibiotics (3rd generation cephalosporins)
    esbl_antibiotics = ['Ceftazidime', 'Cefotaxime', 'Ceftriaxone', 'Cefpodoxime']
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        # Focus on Enterobacteriaceae (common ESBL producers)
        if not any(term in organism.lower() for term in ['escherichia', 'klebsiella', 'enterobacter', 'salmonella', 'proteus', 'citrobacter']):
            continue
            
        esbl_resistant = 0
        total_esbl_tests = 0
        
        for ab in esbl_antibiotics:
            ab_data = isolate_data[isolate_data['antibiotic'].str.contains(ab, case=False, na=False)]
            if not ab_data.empty:
                total_esbl_tests += 1
                if (ab_data['result'] == 'R').any():
                    esbl_resistant += 1
        
        if total_esbl_tests >= 2 and esbl_resistant >= 2:
            esbl_indicators.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistance_mechanism': 'ESBL',
                'confidence': 'High' if esbl_resistant == total_esbl_tests else 'Moderate',
                'resistant_antibiotics': esbl_resistant,
                'total_tests': total_esbl_tests
            })
    
    return pd.DataFrame(esbl_indicators)


def detect_carbapenemase_patterns(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect Carbapenemase-producing organisms."""
    if ast_df.empty:
        return pd.DataFrame()
    
    carbapenem_indicators = []
    
    # Carbapenem antibiotics
    carbapenems = ['Imipenem', 'Meropenem', 'Ertapenem', 'Doripenem']
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        carbapenem_resistant = 0
        total_carbapenem_tests = 0
        
        for ab in carbapenems:
            ab_data = isolate_data[isolate_data['antibiotic'].str.contains(ab, case=False, na=False)]
            if not ab_data.empty:
                total_carbapenem_tests += 1
                if (ab_data['result'] == 'R').any():
                    carbapenem_resistant += 1
        
        if total_carbapenem_tests >= 1 and carbapenem_resistant >= 1:
            carbapenem_indicators.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistance_mechanism': 'Carbapenemase',
                'confidence': 'High',
                'resistant_antibiotics': carbapenem_resistant,
                'total_tests': total_carbapenem_tests
            })
    
    return pd.DataFrame(carbapenem_indicators)


def detect_mrsa_patterns(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect Methicillin-Resistant Staphylococcus aureus (MRSA)."""
    if ast_df.empty:
        return pd.DataFrame()
    
    mrsa_indicators = []
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        # Only check Staphylococcus aureus
        if 'staphylococcus aureus' not in organism.lower():
            continue
        
        # Check for methicillin/oxacillin resistance
        methicillin_data = isolate_data[isolate_data['antibiotic'].str.contains('oxacillin|methicillin', case=False, na=False)]
        
        if not methicillin_data.empty and (methicillin_data['result'] == 'R').any():
            mrsa_indicators.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistance_mechanism': 'MRSA',
                'confidence': 'High',
                'resistant_antibiotics': 1,
                'total_tests': 1
            })
    
    return pd.DataFrame(mrsa_indicators)


def detect_ampc_patterns(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect AmpC beta-lactamase patterns."""
    if ast_df.empty:
        return pd.DataFrame()
    
    ampc_indicators = []
    
    # AmpC screening antibiotics (cephalosporins)
    ampc_antibiotics = ['Ceftazidime', 'Cefotaxime', 'Ceftriaxone', 'Cefepime']
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        # Focus on organisms that commonly produce AmpC
        ampc_organisms = ['enterobacter', 'citrobacter', 'serratia', 'pseudomonas', 'acinetobacter']
        if not any(term in organism.lower() for term in ampc_organisms):
            continue
            
        ampc_resistant = 0
        total_ampc_tests = 0
        
        for ab in ampc_antibiotics:
            ab_data = isolate_data[isolate_data['antibiotic'].str.contains(ab, case=False, na=False)]
            if not ab_data.empty:
                total_ampc_tests += 1
                if (ab_data['result'] == 'R').any():
                    ampc_resistant += 1
        
        if total_ampc_tests >= 2 and ampc_resistant >= 2:
            ampc_indicators.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistance_mechanism': 'AmpC',
                'confidence': 'High' if ampc_resistant == total_ampc_tests else 'Moderate',
                'resistant_antibiotics': ampc_resistant,
                'total_tests': total_ampc_tests
            })
    
    return pd.DataFrame(ampc_indicators)


def detect_vrsa_vrsa_patterns(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect Vancomycin-Resistant/Resistant Staphylococcus aureus (VRSA/VISA)."""
    if ast_df.empty:
        return pd.DataFrame()
    
    vrsa_indicators = []
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        # Only check Staphylococcus aureus
        if 'staphylococcus aureus' not in organism.lower():
            continue
        
        # Check for vancomycin resistance
        vancomycin_data = isolate_data[isolate_data['antibiotic'].str.contains('vancomycin', case=False, na=False)]
        
        if not vancomycin_data.empty:
            if (vancomycin_data['result'] == 'R').any():
                mechanism = 'VRSA'
                confidence = 'High'
            elif (vancomycin_data['result'] == 'I').any():
                mechanism = 'VISA'
                confidence = 'High'
            else:
                continue
                
            vrsa_indicators.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistance_mechanism': mechanism,
                'confidence': confidence,
                'resistant_antibiotics': 1,
                'total_tests': 1
            })
    
    return pd.DataFrame(vrsa_indicators)


def detect_resistance_mechanisms(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect all resistance mechanisms in the dataset."""
    if ast_df.empty:
        return pd.DataFrame()

    all_mechanisms = []

    # First, include mechanisms detected by automated interpretation
    if 'suspected_mechanism' in ast_df.columns:
        interpreted_mechanisms = ast_df[ast_df['suspected_mechanism'].notna()].copy()
        if not interpreted_mechanisms.empty:
            interpreted_mechanisms = interpreted_mechanisms[['isolate_id', 'organism', 'suspected_mechanism', 'interpretation_confidence']].copy()
            interpreted_mechanisms.columns = ['isolate_id', 'organism', 'resistance_mechanism', 'confidence']
            interpreted_mechanisms['resistant_antibiotics'] = 1  # Placeholder
            interpreted_mechanisms['total_tests'] = 1  # Placeholder
            all_mechanisms.append(interpreted_mechanisms)

    # Detect each mechanism using pattern analysis
    mechanisms = [
        detect_esbl_patterns,
        detect_carbapenemase_patterns,
        detect_mrsa_patterns,
        detect_ampc_patterns,
        detect_vrsa_vrsa_patterns
    ]

    for detect_func in mechanisms:
        mechanisms_df = detect_func(ast_df)
        if not mechanisms_df.empty:
            all_mechanisms.append(mechanisms_df)

    if all_mechanisms:
        combined_df = pd.concat(all_mechanisms, ignore_index=True)
        # Remove duplicates based on isolate_id and resistance_mechanism
        combined_df = combined_df.drop_duplicates(subset=['isolate_id', 'resistance_mechanism'])
        return combined_df
    else:
        return pd.DataFrame()


# ============================================================================
# CROSS-RESISTANCE ANALYSIS
# ============================================================================

def detect_cross_resistance(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Detect cross-resistance patterns between antibiotic classes."""
    if ast_df.empty:
        return pd.DataFrame()
    
    cross_resistance_patterns = []
    
    # Define antibiotic class relationships for cross-resistance
    cross_resistance_classes = {
        'Penicillins': ['Amoxicillin', 'Ampicillin', 'Penicillin', 'Piperacillin'],
        'Cephalosporins_1st': ['Cefazolin', 'Cephalexin'],
        'Cephalosporins_2nd': ['Cefuroxime', 'Cefaclor'],
        'Cephalosporins_3rd': ['Ceftazidime', 'Cefotaxime', 'Ceftriaxone', 'Cefpodoxime'],
        'Cephalosporins_4th': ['Cefepime'],
        'Carbapenems': ['Imipenem', 'Meropenem', 'Ertapenem'],
        'Aminoglycosides': ['Gentamicin', 'Tobramycin', 'Amikacin'],
        'Fluoroquinolones': ['Ciprofloxacin', 'Levofloxacin', 'Ofloxacin'],
        'Tetracyclines': ['Tetracycline', 'Doxycycline'],
        'Macrolides': ['Erythromycin', 'Clarithromycin', 'Azithromycin'],
        'Sulphonamides': ['Sulfamethoxazole', 'Trimethoprim'],
        'Glycopeptides': ['Vancomycin', 'Teicoplanin']
    }
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        # Check for cross-resistance within related classes
        for class_name, antibiotics in cross_resistance_classes.items():
            class_data = isolate_data[isolate_data['antibiotic'].str.contains('|'.join(antibiotics), case=False, na=False)]
            
            if len(class_data) >= 2:  # Need at least 2 antibiotics from the class
                resistant_count = (class_data['result'] == 'R').sum()
                total_count = len(class_data)
                
                if resistant_count >= 2:  # Cross-resistance if 2+ antibiotics in class are resistant
                    cross_resistance_patterns.append({
                        'isolate_id': isolate_id,
                        'organism': organism,
                        'antibiotic_class': class_name,
                        'resistant_antibiotics': resistant_count,
                        'total_antibiotics': total_count,
                        'cross_resistance_level': 'High' if resistant_count == total_count else 'Moderate'
                    })
    
    return pd.DataFrame(cross_resistance_patterns)


def get_multiple_resistance_patterns(ast_df: pd.DataFrame, min_resistances: int = 3) -> pd.DataFrame:
    """Identify isolates with multiple antibiotic resistance (MDR)."""
    if ast_df.empty:
        return pd.DataFrame()
    
    multiple_resistance = []
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        
        # Count unique antibiotics tested and resistant
        total_antibiotics = isolate_data['antibiotic'].nunique()
        resistant_antibiotics = isolate_data[isolate_data['result'] == 'R']['antibiotic'].nunique()
        
        if resistant_antibiotics >= min_resistances:
            resistance_level = 'MDR' if resistant_antibiotics >= 3 else 'Multi-drug resistant'
            
            multiple_resistance.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistant_antibiotics': resistant_antibiotics,
                'total_antibiotics': total_antibiotics,
                'resistance_level': resistance_level,
                'resistance_percentage': round(resistant_antibiotics / total_antibiotics * 100, 1)
            })
    
    return pd.DataFrame(multiple_resistance)

def calculate_resistance_statistics(ast_df: pd.DataFrame) -> Dict:
    """Calculate comprehensive resistance statistics."""
    if ast_df.empty:
        return {}
    
    stats = {
        'total_tests': len(ast_df),
        'resistant_count': (ast_df['result'] == 'R').sum(),
        'intermediate_count': (ast_df['result'] == 'I').sum(),
        'susceptible_count': (ast_df['result'] == 'S').sum(),
        'resistance_rate': (ast_df['result'] == 'R').sum() / len(ast_df) * 100,
        'intermediate_rate': (ast_df['result'] == 'I').sum() / len(ast_df) * 100,
        'susceptible_rate': (ast_df['result'] == 'S').sum() / len(ast_df) * 100,
    }
    return stats


def calculate_trend_direction(ast_df: pd.DataFrame) -> Dict:
    """Determine if resistance trend is increasing, stable, or decreasing."""
    if ast_df.empty:
        return {}
    
    ast_df = ast_df.copy()
    ast_df['test_date'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
    ast_df = ast_df.dropna(subset=['test_date'])
    
    if len(ast_df) < 2:
        return {'trend': 'insufficient_data'}
    
    # Split into two halves
    mid_point = len(ast_df) // 2
    first_half = ast_df.iloc[:mid_point]
    second_half = ast_df.iloc[mid_point:]
    
    first_resistance = (first_half['result'] == 'R').sum() / len(first_half) * 100
    second_resistance = (second_half['result'] == 'R').sum() / len(second_half) * 100
    
    change = second_resistance - first_resistance
    
    if change > 5:
        trend = 'increasing'
    elif change < -5:
        trend = 'decreasing'
    else:
        trend = 'stable'
    
    return {
        'trend': trend,
        'first_half_resistance': round(first_resistance, 2),
        'second_half_resistance': round(second_resistance, 2),
        'change_percentage': round(change, 2),
        'risk_level': 'HIGH' if change > 5 else 'MEDIUM' if change > 0 else 'LOW'
    }


def identify_emerging_resistance(ast_df: pd.DataFrame, samples_df: pd.DataFrame) -> List[Dict]:
    """Identify emerging resistance patterns in recent data."""
    if ast_df.empty:
        return []
    
    emerging = []
    ast_df = ast_df.copy()
    ast_df['test_date'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
    ast_df = ast_df.dropna(subset=['test_date'])
    
    # Look at last 3 months
    cutoff_date = ast_df['test_date'].max() - timedelta(days=90)
    recent_data = ast_df[ast_df['test_date'] >= cutoff_date]
    
    if not recent_data.empty:
        # Find organism-antibiotic combos with high recent resistance
        combos = recent_data.groupby(['organism', 'antibiotic']).agg({
            'result': ['count', lambda x: (x == 'R').sum()]
        }).reset_index()
        combos.columns = ['organism', 'antibiotic', 'tests', 'resistant']
        combos['resistance_rate'] = combos['resistant'] / combos['tests'] * 100
        
        # Filter for significant patterns
        high_resistance = combos[(combos['resistance_rate'] > 60) & (combos['tests'] >= 5)]
        
        for _, row in high_resistance.iterrows():
            emerging.append({
                'organism': row['organism'],
                'antibiotic': row['antibiotic'],
                'resistance_rate': round(row['resistance_rate'], 2),
                'tests': int(row['tests']),
                'severity': 'CRITICAL' if row['resistance_rate'] > 80 else 'HIGH'
            })
    
    return sorted(emerging, key=lambda x: x['resistance_rate'], reverse=True)


# ============================================================================
# QUALITY METRICS
# ============================================================================

def assess_data_quality(samples_df: pd.DataFrame, ast_df: pd.DataFrame) -> Dict:
    """Assess overall data quality and completeness."""
    quality_metrics = {
        'total_samples': len(samples_df),
        'total_tests': len(ast_df),
        'samples_with_coordinates': 0,
        'tests_with_dates': 0,
        'completeness_score': 0,
        'data_quality_issues': []
    }
    
    if not samples_df.empty:
        quality_metrics['samples_with_coordinates'] = samples_df[
            samples_df['latitude'].notna() & samples_df['longitude'].notna()
        ].shape[0]
    
    if not ast_df.empty:
        ast_df_copy = ast_df.copy()
        ast_df_copy['test_date'] = pd.to_datetime(ast_df_copy['test_date'], errors='coerce')
        quality_metrics['tests_with_dates'] = ast_df_copy['test_date'].notna().sum()
    
    # Calculate completeness
    if len(samples_df) > 0:
        coord_completeness = quality_metrics['samples_with_coordinates'] / len(samples_df) * 100
        if coord_completeness < 50:
            quality_metrics['data_quality_issues'].append('Low geographic data coverage')
    
    if len(ast_df) > 0:
        date_completeness = quality_metrics['tests_with_dates'] / len(ast_df) * 100
        if date_completeness < 80:
            quality_metrics['data_quality_issues'].append('Missing test dates')
    
    # Overall score
    quality_metrics['completeness_score'] = round(
        (quality_metrics['tests_with_dates'] / max(len(ast_df), 1) * 100), 2
    )
    
    return quality_metrics


# ============================================================================
# RISK ASSESSMENT
# ============================================================================

def calculate_organism_risk_score(ast_df: pd.DataFrame, organism: str) -> Dict:
    """Calculate risk score for a specific organism based on resistance patterns."""
    if ast_df.empty:
        return {}
    
    org_data = ast_df[ast_df['organism'] == organism]
    if org_data.empty:
        return {}
    
    resistance_rate = (org_data['result'] == 'R').sum() / len(org_data) * 100
    test_count = len(org_data)
    unique_antibiotics = org_data['antibiotic'].nunique()
    
    # Calculate risk score (0-100)
    risk_score = 0
    risk_factors = []
    
    # Resistance rate (0-40 points)
    if resistance_rate > 70:
        risk_score += 40
        risk_factors.append('Very high resistance rate (>70%)')
    elif resistance_rate > 50:
        risk_score += 30
        risk_factors.append('High resistance rate (>50%)')
    elif resistance_rate > 30:
        risk_score += 20
        risk_factors.append('Moderate resistance rate (>30%)')
    
    # Data volume (0-20 points)
    if test_count > 100:
        risk_score += 20
        risk_factors.append('Significant data volume (>100 tests)')
    elif test_count > 50:
        risk_score += 15
    elif test_count > 20:
        risk_score += 10
    
    # Antibiotic diversity (0-40 points)
    if unique_antibiotics > 10:
        risk_score += 40
        risk_factors.append('High antibiotic diversity')
    elif unique_antibiotics > 5:
        risk_score += 25
    elif unique_antibiotics > 2:
        risk_score += 15
    
    return {
        'organism': organism,
        'risk_score': min(risk_score, 100),
        'risk_level': 'CRITICAL' if risk_score >= 70 else 'HIGH' if risk_score >= 50 else 'MODERATE' if risk_score >= 30 else 'LOW',
        'resistance_rate': round(resistance_rate, 2),
        'test_count': test_count,
        'antibiotic_diversity': unique_antibiotics,
        'risk_factors': risk_factors
    }


def get_high_risk_organisms(ast_df: pd.DataFrame, threshold: int = 50) -> List[Dict]:
    """Get organisms with resistance rates above the threshold."""
    if ast_df.empty:
        return []

    organisms = ast_df['organism'].unique()
    high_risk_organisms = []

    for org in organisms:
        score = calculate_organism_risk_score(ast_df, org)
        if score and score['resistance_rate'] >= threshold:
            high_risk_organisms.append(score)

    return sorted(high_risk_organisms, key=lambda x: x['resistance_rate'], reverse=True)


# ============================================================================
# ANTIBIOTIC ROTATION RECOMMENDATIONS
# ============================================================================

def generate_antibiotic_recommendations(ast_df: pd.DataFrame) -> List[Dict]:
    """Generate antibiotic usage recommendations based on resistance patterns."""
    if ast_df.empty:
        return []
    
    recommendations = []
    
    # Get antibiotics ranked by susceptibility
    antibiotic_stats = ast_df.groupby('antibiotic').agg({
        'result': ['count', lambda x: (x == 'S').sum()]
    }).reset_index()
    antibiotic_stats.columns = ['antibiotic', 'tests', 'susceptible']
    antibiotic_stats['susceptibility_rate'] = antibiotic_stats['susceptible'] / antibiotic_stats['tests'] * 100
    antibiotic_stats = antibiotic_stats.sort_values('susceptibility_rate', ascending=False)
    
    for _, row in antibiotic_stats.iterrows():
        if row['tests'] >= 5:  # Only consider with sufficient data
            antibiotic = row['antibiotic']
            susc_rate = row['susceptibility_rate']
            
            if susc_rate > 80:
                recommendation = 'PREFERRED - Excellent susceptibility'
            elif susc_rate > 60:
                recommendation = 'GOOD - Acceptable for use'
            elif susc_rate > 40:
                recommendation = 'CAUTION - Declining efficacy'
            else:
                recommendation = 'AVOID - Poor efficacy'
            
            recommendations.append({
                'antibiotic': antibiotic,
                'susceptibility_rate': round(susc_rate, 2),
                'tests': int(row['tests']),
                'recommendation': recommendation,
                'priority': 1 if susc_rate > 80 else 2 if susc_rate > 60 else 3 if susc_rate > 40 else 4
            })
    
    return recommendations


# ============================================================================
# BURDEN OF RESISTANCE
# ============================================================================

def calculate_resistance_burden(samples_df: pd.DataFrame, ast_df: pd.DataFrame) -> Dict:
    """Calculate overall resistance burden for public health assessment."""
    if samples_df.empty or ast_df.empty:
        return {}
    
    # Merge to get sample-level information
    merged = ast_df.merge(samples_df[['sample_id', 'source_category']], on='sample_id', how='left')
    
    burden = {
        'total_resistant_tests': (merged['result'] == 'R').sum(),
        'total_tests': len(merged),
        'overall_resistance_rate': (merged['result'] == 'R').sum() / len(merged) * 100,
        'resistance_by_category': {},
        'public_health_impact': ''
    }
    
    # By source category
    for category in merged['source_category'].unique():
        if pd.notna(category):
            cat_data = merged[merged['source_category'] == category]
            cat_resistance = (cat_data['result'] == 'R').sum() / len(cat_data) * 100
            burden['resistance_by_category'][category] = round(cat_resistance, 2)
    
    # Impact assessment
    overall_rate = burden['overall_resistance_rate']
    if overall_rate > 50:
        burden['public_health_impact'] = 'CRITICAL - Urgent intervention needed'
    elif overall_rate > 30:
        burden['public_health_impact'] = 'HIGH - Enhanced surveillance recommended'
    elif overall_rate > 15:
        burden['public_health_impact'] = 'MODERATE - Continued monitoring'
    else:
        burden['public_health_impact'] = 'LOW - Maintain current practices'
    
    return burden


# ============================================================================
# COMPARATIVE ANALYSIS
# ============================================================================

def compare_organisms(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Compare resistance profiles across organisms."""
    if ast_df.empty:
        return pd.DataFrame()
    
    comparison = ast_df.groupby(['organism', 'result']).size().unstack(fill_value=0)
    comparison['total'] = comparison.sum(axis=1)
    comparison['resistance_rate'] = (comparison.get('R', 0) / comparison['total'] * 100).round(2)
    comparison = comparison.sort_values('resistance_rate', ascending=False)
    
    return comparison


def compare_antibiotics(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Compare efficacy across antibiotics."""
    if ast_df.empty:
        return pd.DataFrame()
    
    comparison = ast_df.groupby(['antibiotic', 'result']).size().unstack(fill_value=0)
    comparison['total'] = comparison.sum(axis=1)
    comparison['resistance_rate'] = (comparison.get('R', 0) / comparison['total'] * 100).round(2)
    comparison['susceptibility_rate'] = (comparison.get('S', 0) / comparison['total'] * 100).round(2)
    comparison = comparison.sort_values('susceptibility_rate', ascending=False)
    
    return comparison


# ============================================================================
# PREDICTION & FORECASTING
# ============================================================================

def forecast_resistance_trend(ast_df: pd.DataFrame, periods: int = 3) -> Dict:
    """Simple forecast of resistance trends using linear regression."""
    if ast_df.empty:
        return {}
    
    ast_df = ast_df.copy()
    ast_df['test_date'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
    ast_df = ast_df.dropna(subset=['test_date'])
    
    if len(ast_df) < 3:
        return {'error': 'Insufficient data for forecast'}
    
    # Monthly aggregation
    monthly = ast_df.groupby(ast_df['test_date'].dt.to_period('M')).agg({
        'result': ['count', lambda x: (x == 'R').sum()]
    }).reset_index()
    monthly.columns = ['period', 'tests', 'resistant']
    monthly['resistance_rate'] = monthly['resistant'] / monthly['tests'] * 100
    
    if len(monthly) < 2:
        return {'error': 'Insufficient monthly data for forecast'}
    
    # Simple linear regression
    x = np.arange(len(monthly))
    y = monthly['resistance_rate'].values
    
    try:
        coeffs = np.polyfit(x, y, 1)
        slope, intercept = coeffs[0], coeffs[1]
        
        forecasts = []
        last_month = len(monthly) - 1
        
        for i in range(1, periods + 1):
            predicted_rate = slope * (last_month + i) + intercept
            forecasts.append({
                'months_ahead': i,
                'predicted_resistance_rate': max(0, min(100, round(predicted_rate, 2))),
                'trend': 'increasing' if slope > 0 else 'decreasing'
            })
        
        return {
            'forecasts': forecasts,
            'trend_slope': round(slope, 4),
            'confidence': 'moderate' if len(monthly) >= 6 else 'low'
        }
    except:
        return {'error': 'Unable to generate forecast'}


# ============================================================================
# KEY PERFORMANCE INDICATORS
# ============================================================================

def calculate_kpis(samples_df: pd.DataFrame, ast_df: pd.DataFrame) -> Dict:
    """Calculate key performance indicators for the surveillance system."""
    if ast_df.empty or samples_df.empty:
        return {}
    
    ast_df = ast_df.copy()
    ast_df['test_date'] = pd.to_datetime(ast_df['test_date'], errors='coerce')
    
    recent_30days = ast_df[
        (ast_df['test_date'] >= (datetime.now() - timedelta(days=30))) &
        (ast_df['test_date'].notna())
    ]
    
    kpis = {
        'total_samples_collected': len(samples_df),
        'total_tests_performed': len(ast_df),
        'tests_per_sample': round(len(ast_df) / max(len(samples_df), 1), 2),
        'organisms_identified': ast_df['organism'].nunique(),
        'antibiotics_tested': ast_df['antibiotic'].nunique(),
        'tests_last_30_days': len(recent_30days),
        'testing_trend': 'active' if len(recent_30days) > 0 else 'inactive',
        'geographic_coverage': len(samples_df[samples_df['latitude'].notna()]) / max(len(samples_df), 1) * 100,
    }
    
    return kpis
