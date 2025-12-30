#!/usr/bin/env python3
"""
Test script to verify the analytics changes are working
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
from src import analytics

# Create test data with different resistance rates
test_data = pd.DataFrame({
    'organism': ['E. coli', 'E. coli', 'E. coli', 'S. aureus', 'S. aureus', 'K. pneumoniae', 'K. pneumoniae', 'K. pneumoniae', 'K. pneumoniae'],
    'antibiotic': ['Ampicillin', 'Ampicillin', 'Ampicillin', 'Methicillin', 'Methicillin', 'Ceftriaxone', 'Ceftriaxone', 'Ceftriaxone', 'Ceftriaxone'],
    'result': ['R', 'R', 'S', 'R', 'R', 'R', 'R', 'R', 'R'],  # E. coli: 66.7%, S. aureus: 100%, K. pneumoniae: 100%
    'sample_id': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9']
})

print("Testing high-risk organisms function...")
high_risk = analytics.get_high_risk_organisms(test_data, 50)
print(f"Found {len(high_risk)} high-risk organisms (resistance rate >= 50%):")
for org in high_risk:
    print(f"  {org['organism']}: {org['resistance_rate']:.1f}% resistance")

print("\nExpected: All three organisms should be included (all >= 50%)")
print("E. coli: 66.7%, S. aureus: 100%, K. pneumoniae: 100%")