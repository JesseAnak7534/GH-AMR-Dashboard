"""
Automated Alerts System for AMR Surveillance Dashboard.
Provides threshold-based alerts, outbreak detection, and MDR organism notifications.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import os
import json


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts."""
    RESISTANCE_THRESHOLD = "resistance_threshold"
    OUTBREAK_DETECTION = "outbreak_detection"
    MDR_ORGANISM = "mdr_organism"
    NEW_RESISTANCE = "new_resistance"
    DATA_QUALITY = "data_quality"
    TREND_INCREASE = "trend_increase"


@dataclass
class Alert:
    """Alert data structure."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    organism: Optional[str]
    antibiotic: Optional[str]
    region: Optional[str]
    lab_name: Optional[str]
    current_value: float
    threshold_value: Optional[float]
    created_at: datetime
    is_acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    metadata: Optional[Dict] = None


# Default thresholds for resistance rates
DEFAULT_THRESHOLDS = {
    "critical": 80.0,  # >= 80% resistance is critical
    "high": 60.0,      # >= 60% resistance is high
    "medium": 40.0,    # >= 40% resistance is medium
    "low": 20.0        # >= 20% resistance is low
}

# MDR definitions - organisms resistant to 3+ antibiotic classes
MDR_ANTIBIOTIC_CLASSES = {
    "Penicillins": ["Ampicillin", "Amoxicillin", "Penicillin", "Piperacillin", "Amoxicillin-Clavulanic Acid"],
    "Cephalosporins": ["Ceftriaxone", "Ceftazidime", "Cefotaxime", "Cefepime", "Cefuroxime", "Cephalexin", "Cefixime"],
    "Carbapenems": ["Meropenem", "Imipenem", "Ertapenem", "Doripenem"],
    "Aminoglycosides": ["Gentamicin", "Amikacin", "Tobramycin", "Streptomycin", "Kanamycin"],
    "Fluoroquinolones": ["Ciprofloxacin", "Levofloxacin", "Ofloxacin", "Norfloxacin", "Moxifloxacin"],
    "Tetracyclines": ["Tetracycline", "Doxycycline", "Minocycline", "Tigecycline"],
    "Sulfonamides": ["Trimethoprim-Sulfamethoxazole", "Sulfamethoxazole", "Trimethoprim"],
    "Macrolides": ["Azithromycin", "Erythromycin", "Clarithromycin"],
    "Polymyxins": ["Colistin", "Polymyxin B"],
    "Glycopeptides": ["Vancomycin", "Teicoplanin"],
    "Nitrofurans": ["Nitrofurantoin"],
    "Chloramphenicol": ["Chloramphenicol"],
}


def get_antibiotic_class(antibiotic: str) -> Optional[str]:
    """Get the class of an antibiotic."""
    antibiotic_lower = antibiotic.lower()
    for cls, antibiotics in MDR_ANTIBIOTIC_CLASSES.items():
        for ab in antibiotics:
            if ab.lower() in antibiotic_lower or antibiotic_lower in ab.lower():
                return cls
    return None


def detect_mdr_organisms(ast_df: pd.DataFrame) -> List[Dict]:
    """
    Detect Multi-Drug Resistant (MDR) organisms.
    MDR = Resistant to at least 3 antibiotic classes.
    """
    mdr_isolates = []
    
    if ast_df.empty:
        return mdr_isolates
    
    # Group by isolate
    for isolate_id, isolate_data in ast_df.groupby('isolate_id'):
        organism = isolate_data['organism'].iloc[0]
        resistant_tests = isolate_data[isolate_data['result'] == 'R']
        
        if resistant_tests.empty:
            continue
        
        # Get unique antibiotic classes with resistance
        resistant_classes = set()
        resistant_antibiotics = []
        
        for _, row in resistant_tests.iterrows():
            ab_class = get_antibiotic_class(row['antibiotic'])
            if ab_class:
                resistant_classes.add(ab_class)
                resistant_antibiotics.append(row['antibiotic'])
        
        # MDR if resistant to >= 3 classes
        if len(resistant_classes) >= 3:
            mdr_isolates.append({
                'isolate_id': isolate_id,
                'organism': organism,
                'resistant_classes': list(resistant_classes),
                'resistant_antibiotics': resistant_antibiotics,
                'num_classes': len(resistant_classes),
                'sample_id': isolate_data['sample_id'].iloc[0] if 'sample_id' in isolate_data.columns else None
            })
    
    return mdr_isolates


def detect_outbreak(ast_df: pd.DataFrame, samples_df: pd.DataFrame, 
                    window_days: int = 14, threshold_multiplier: float = 2.0) -> List[Dict]:
    """
    Detect potential outbreaks using statistical anomaly detection.
    Looks for unusual clustering of resistance patterns in time and space.
    """
    outbreaks = []
    
    if ast_df.empty or samples_df.empty:
        return outbreaks
    
    # Merge data
    merged = ast_df.merge(samples_df[['sample_id', 'collection_date', 'region', 'lab_name']], 
                          on='sample_id', how='left')
    
    if 'collection_date' not in merged.columns:
        return outbreaks
    
    # Convert dates
    merged['collection_date'] = pd.to_datetime(merged['collection_date'], errors='coerce')
    merged = merged.dropna(subset=['collection_date'])
    
    if merged.empty:
        return outbreaks
    
    # Analyze by organism and region
    for (organism, region), group in merged.groupby(['organism', 'region']):
        if len(group) < 5:
            continue
        
        # Calculate rolling resistance rate
        group = group.sort_values('collection_date')
        group['is_resistant'] = (group['result'] == 'R').astype(int)
        
        # Get recent window
        max_date = group['collection_date'].max()
        window_start = max_date - timedelta(days=window_days)
        
        recent = group[group['collection_date'] >= window_start]
        historical = group[group['collection_date'] < window_start]
        
        if len(recent) < 3 or len(historical) < 5:
            continue
        
        # Compare rates
        recent_rate = recent['is_resistant'].mean() * 100
        historical_rate = historical['is_resistant'].mean() * 100
        historical_std = historical['is_resistant'].std() * 100
        
        # Detect anomaly if recent rate exceeds historical by threshold
        if historical_std > 0 and recent_rate > historical_rate + (threshold_multiplier * historical_std):
            outbreaks.append({
                'organism': organism,
                'region': region,
                'recent_rate': recent_rate,
                'historical_rate': historical_rate,
                'increase_pct': recent_rate - historical_rate,
                'recent_samples': len(recent),
                'window_days': window_days,
                'start_date': window_start.isoformat(),
                'end_date': max_date.isoformat()
            })
    
    return outbreaks


def check_resistance_thresholds(ast_df: pd.DataFrame, 
                                 thresholds: Dict[str, float] = None) -> List[Dict]:
    """
    Check resistance rates against configurable thresholds.
    Returns alerts for organism-antibiotic combinations exceeding thresholds.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS
    
    alerts = []
    
    if ast_df.empty:
        return alerts
    
    # Calculate resistance rates by organism-antibiotic
    for (organism, antibiotic), group in ast_df.groupby(['organism', 'antibiotic']):
        total = len(group)
        if total < 10:  # Minimum sample size for meaningful rate
            continue
        
        resistant = (group['result'] == 'R').sum()
        rate = (resistant / total) * 100
        
        # Determine severity
        severity = None
        if rate >= thresholds.get('critical', 80):
            severity = AlertSeverity.CRITICAL
        elif rate >= thresholds.get('high', 60):
            severity = AlertSeverity.HIGH
        elif rate >= thresholds.get('medium', 40):
            severity = AlertSeverity.MEDIUM
        elif rate >= thresholds.get('low', 20):
            severity = AlertSeverity.LOW
        
        if severity:
            alerts.append({
                'organism': organism,
                'antibiotic': antibiotic,
                'resistance_rate': rate,
                'total_tests': total,
                'resistant_count': resistant,
                'severity': severity.value,
                'threshold_exceeded': thresholds.get(severity.value, 0)
            })
    
    return alerts


def detect_new_resistance_patterns(ast_df: pd.DataFrame, 
                                    historical_df: pd.DataFrame) -> List[Dict]:
    """
    Detect new resistance patterns not seen historically.
    Useful for early detection of emerging resistance.
    """
    new_patterns = []
    
    if ast_df.empty:
        return new_patterns
    
    # Get current resistant combinations
    current_resistant = ast_df[ast_df['result'] == 'R'][['organism', 'antibiotic']].drop_duplicates()
    
    if historical_df is not None and not historical_df.empty:
        # Get historical resistant combinations
        historical_resistant = historical_df[historical_df['result'] == 'R'][['organism', 'antibiotic']].drop_duplicates()
        
        # Find new combinations
        merged = current_resistant.merge(historical_resistant, on=['organism', 'antibiotic'], 
                                         how='left', indicator=True)
        new_combos = merged[merged['_merge'] == 'left_only']
        
        for _, row in new_combos.iterrows():
            new_patterns.append({
                'organism': row['organism'],
                'antibiotic': row['antibiotic'],
                'first_detected': datetime.now().isoformat()
            })
    
    return new_patterns


def check_trend_increases(ast_df: pd.DataFrame, samples_df: pd.DataFrame,
                          lookback_months: int = 3, increase_threshold: float = 15.0) -> List[Dict]:
    """
    Detect significant increasing trends in resistance rates.
    """
    trend_alerts = []
    
    if ast_df.empty or samples_df.empty:
        return trend_alerts
    
    # Merge with collection dates
    merged = ast_df.merge(samples_df[['sample_id', 'collection_date']], on='sample_id', how='left')
    merged['collection_date'] = pd.to_datetime(merged['collection_date'], errors='coerce')
    merged = merged.dropna(subset=['collection_date'])
    
    if merged.empty:
        return trend_alerts
    
    # Calculate monthly rates
    merged['month'] = merged['collection_date'].dt.to_period('M')
    
    for (organism, antibiotic), group in merged.groupby(['organism', 'antibiotic']):
        monthly = group.groupby('month').agg({
            'result': [lambda x: (x == 'R').sum(), 'count']
        })
        monthly.columns = ['resistant', 'total']
        monthly['rate'] = (monthly['resistant'] / monthly['total']) * 100
        
        if len(monthly) < 2:
            continue
        
        # Compare recent to earlier period
        if len(monthly) >= lookback_months:
            recent_rate = monthly['rate'].iloc[-1]
            earlier_rate = monthly['rate'].iloc[-(lookback_months):-1].mean()
            
            increase = recent_rate - earlier_rate
            
            if increase >= increase_threshold:
                trend_alerts.append({
                    'organism': organism,
                    'antibiotic': antibiotic,
                    'recent_rate': recent_rate,
                    'earlier_rate': earlier_rate,
                    'increase': increase,
                    'months_analyzed': lookback_months
                })
    
    return trend_alerts


def generate_all_alerts(ast_df: pd.DataFrame, samples_df: pd.DataFrame,
                        historical_ast_df: pd.DataFrame = None,
                        thresholds: Dict[str, float] = None) -> List[Alert]:
    """
    Generate all types of alerts for the current data.
    """
    all_alerts = []
    timestamp = datetime.now()
    
    # 1. MDR Organisms
    mdr_results = detect_mdr_organisms(ast_df)
    for i, mdr in enumerate(mdr_results):
        all_alerts.append(Alert(
            alert_id=f"MDR-{timestamp.strftime('%Y%m%d%H%M%S')}-{i}",
            alert_type=AlertType.MDR_ORGANISM,
            severity=AlertSeverity.CRITICAL if mdr['num_classes'] >= 5 else AlertSeverity.HIGH,
            title=f"MDR {mdr['organism']} Detected",
            description=f"Isolate {mdr['isolate_id']} is resistant to {mdr['num_classes']} antibiotic classes: {', '.join(mdr['resistant_classes'])}",
            organism=mdr['organism'],
            antibiotic=None,
            region=None,
            lab_name=None,
            current_value=mdr['num_classes'],
            threshold_value=3,
            created_at=timestamp,
            metadata={'resistant_antibiotics': mdr['resistant_antibiotics']}
        ))
    
    # 2. Outbreak Detection
    outbreaks = detect_outbreak(ast_df, samples_df)
    for i, outbreak in enumerate(outbreaks):
        all_alerts.append(Alert(
            alert_id=f"OUTBREAK-{timestamp.strftime('%Y%m%d%H%M%S')}-{i}",
            alert_type=AlertType.OUTBREAK_DETECTION,
            severity=AlertSeverity.CRITICAL,
            title=f"Potential Outbreak: {outbreak['organism']} in {outbreak['region']}",
            description=f"Resistance rate increased from {outbreak['historical_rate']:.1f}% to {outbreak['recent_rate']:.1f}% (+{outbreak['increase_pct']:.1f}%) in the last {outbreak['window_days']} days",
            organism=outbreak['organism'],
            antibiotic=None,
            region=outbreak['region'],
            lab_name=None,
            current_value=outbreak['recent_rate'],
            threshold_value=outbreak['historical_rate'],
            created_at=timestamp,
            metadata=outbreak
        ))
    
    # 3. Resistance Threshold Alerts
    threshold_alerts = check_resistance_thresholds(ast_df, thresholds)
    for i, alert in enumerate(threshold_alerts):
        severity = AlertSeverity(alert['severity'])
        all_alerts.append(Alert(
            alert_id=f"THRESHOLD-{timestamp.strftime('%Y%m%d%H%M%S')}-{i}",
            alert_type=AlertType.RESISTANCE_THRESHOLD,
            severity=severity,
            title=f"{severity.value.upper()}: {alert['organism']} - {alert['antibiotic']}",
            description=f"Resistance rate of {alert['resistance_rate']:.1f}% ({alert['resistant_count']}/{alert['total_tests']}) exceeds {alert['severity']} threshold of {alert['threshold_exceeded']}%",
            organism=alert['organism'],
            antibiotic=alert['antibiotic'],
            region=None,
            lab_name=None,
            current_value=alert['resistance_rate'],
            threshold_value=alert['threshold_exceeded'],
            created_at=timestamp,
            metadata=alert
        ))
    
    # 4. Trend Increases
    trends = check_trend_increases(ast_df, samples_df)
    for i, trend in enumerate(trends):
        all_alerts.append(Alert(
            alert_id=f"TREND-{timestamp.strftime('%Y%m%d%H%M%S')}-{i}",
            alert_type=AlertType.TREND_INCREASE,
            severity=AlertSeverity.HIGH if trend['increase'] >= 25 else AlertSeverity.MEDIUM,
            title=f"Rising Resistance: {trend['organism']} - {trend['antibiotic']}",
            description=f"Resistance increased by {trend['increase']:.1f}% (from {trend['earlier_rate']:.1f}% to {trend['recent_rate']:.1f}%) over {trend['months_analyzed']} months",
            organism=trend['organism'],
            antibiotic=trend['antibiotic'],
            region=None,
            lab_name=None,
            current_value=trend['recent_rate'],
            threshold_value=trend['earlier_rate'],
            created_at=timestamp,
            metadata=trend
        ))
    
    # 5. New Resistance Patterns
    if historical_ast_df is not None:
        new_patterns = detect_new_resistance_patterns(ast_df, historical_ast_df)
        for i, pattern in enumerate(new_patterns):
            all_alerts.append(Alert(
                alert_id=f"NEWRES-{timestamp.strftime('%Y%m%d%H%M%S')}-{i}",
                alert_type=AlertType.NEW_RESISTANCE,
                severity=AlertSeverity.HIGH,
                title=f"New Resistance: {pattern['organism']} - {pattern['antibiotic']}",
                description=f"First detection of {pattern['organism']} resistance to {pattern['antibiotic']}",
                organism=pattern['organism'],
                antibiotic=pattern['antibiotic'],
                region=None,
                lab_name=None,
                current_value=1,
                threshold_value=0,
                created_at=timestamp,
                metadata=pattern
            ))
    
    return all_alerts


def alerts_to_dataframe(alerts: List[Alert]) -> pd.DataFrame:
    """Convert alerts to DataFrame for display."""
    if not alerts:
        return pd.DataFrame()
    
    data = []
    for alert in alerts:
        data.append({
            'Alert ID': alert.alert_id,
            'Type': alert.alert_type.value.replace('_', ' ').title(),
            'Severity': alert.severity.value.upper(),
            'Title': alert.title,
            'Description': alert.description,
            'Organism': alert.organism or '-',
            'Antibiotic': alert.antibiotic or '-',
            'Region': alert.region or '-',
            'Current Value': f"{alert.current_value:.1f}",
            'Threshold': f"{alert.threshold_value:.1f}" if alert.threshold_value else '-',
            'Created': alert.created_at.strftime('%Y-%m-%d %H:%M'),
            'Acknowledged': '✓' if alert.is_acknowledged else '✗'
        })
    
    return pd.DataFrame(data)


def get_alert_summary(alerts: List[Alert]) -> Dict:
    """Get summary statistics for alerts."""
    if not alerts:
        return {
            'total': 0,
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0,
            'by_type': {}
        }
    
    summary = {
        'total': len(alerts),
        'critical': sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL),
        'high': sum(1 for a in alerts if a.severity == AlertSeverity.HIGH),
        'medium': sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM),
        'low': sum(1 for a in alerts if a.severity == AlertSeverity.LOW),
        'by_type': {}
    }
    
    for alert_type in AlertType:
        count = sum(1 for a in alerts if a.alert_type == alert_type)
        if count > 0:
            summary['by_type'][alert_type.value] = count
    
    return summary
