#!/usr/bin/env python3
"""
Test script to verify the analytics changes are working
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
from datetime import datetime
from src import analytics

# Create test data
test_data = pd.DataFrame({
    'organism': ['E. coli', 'E. coli', 'S. aureus', 'S. aureus', 'S. aureus', 'K. pneumoniae'],
    'antibiotic': ['Ampicillin', 'Ampicillin', 'Methicillin', 'Methicillin', 'Methicillin', 'Ceftriaxone'],
    'result': ['R', 'R', 'R', 'R', 'S', 'R'],  # E. coli: 100% resistant, S. aureus: 66.7% resistant, K. pneumoniae: 100% resistant
    'sample_id': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']
})

print("Testing high-risk organisms function...")
high_risk = analytics.get_high_risk_organisms(test_data, 50)

print(f"Found {len(high_risk)} high-risk organisms:")
for org in high_risk:
    print(f"  {org['organism']}: {org['resistance_rate']:.1f}% resistance")

print("\nTesting date formatting...")
current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(f"Current time: {current_time}")

print("\nAll tests completed!")