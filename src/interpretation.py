"""
Breakpoint Database and Interpretation Engine for AMR Surveillance.
Provides automated S/I/R classification based on CLSI and EUCAST breakpoints.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime


# ============================================================================
# BREAKPOINT DATABASE
# ============================================================================

# CLSI 2025 Breakpoints (simplified for common organisms/antibiotics)
CLSI_2025_BREAKPOINTS = {
    # Enterobacteriaceae breakpoints
    ('Enterobacteriaceae', 'Amoxicillin'): {
        'MIC': {'S': '<=8', 'I': '16', 'R': '>=32'},
        'DD': {'S': '>=20', 'I': '14-19', 'R': '<=13'}
    },
    ('Enterobacteriaceae', 'Ampicillin'): {
        'MIC': {'S': '<=8', 'I': None, 'R': '>=16'},
        'DD': {'S': '>=17', 'I': None, 'R': '<=16'}
    },
    ('Enterobacteriaceae', 'Ceftazidime'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=21', 'I': '18-20', 'R': '<=17'}
    },
    ('Enterobacteriaceae', 'Cefotaxime'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=26', 'I': '23-25', 'R': '<=22'}
    },
    ('Enterobacteriaceae', 'Ciprofloxacin'): {
        'MIC': {'S': '<=0.25', 'I': '0.5', 'R': '>=1'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    },
    ('Enterobacteriaceae', 'Gentamicin'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=15', 'I': '13-14', 'R': '<=12'}
    },
    ('Enterobacteriaceae', 'Tetracycline'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=15', 'I': '12-14', 'R': '<=11'}
    },

    # Staphylococcus aureus breakpoints
    ('Staphylococcus aureus', 'Methicillin'): {
        'MIC': {'S': '<=2', 'I': None, 'R': '>=4'},
        'DD': {'S': '>=10', 'I': None, 'R': '<=9'}
    },
    ('Staphylococcus aureus', 'Ciprofloxacin'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    },
    ('Staphylococcus aureus', 'Gentamicin'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=15', 'I': '13-14', 'R': '<=12'}
    },

    # Enterococcus spp. breakpoints
    ('Enterococcus spp.', 'Ampicillin'): {
        'MIC': {'S': '<=8', 'I': None, 'R': '>=16'},
        'DD': {'S': '>=17', 'I': None, 'R': '<=16'}
    },
    ('Enterococcus spp.', 'Vancomycin'): {
        'MIC': {'S': '<=4', 'I': '8-16', 'R': '>=32'},
        'DD': {'S': '>=15', 'I': '10-14', 'R': '<=9'}
    },

    # Pseudomonas aeruginosa breakpoints
    ('Pseudomonas aeruginosa', 'Ceftazidime'): {
        'MIC': {'S': '<=8', 'I': '16', 'R': '>=32'},
        'DD': {'S': '>=18', 'I': '15-17', 'R': '<=14'}
    },
    ('Pseudomonas aeruginosa', 'Ciprofloxacin'): {
        'MIC': {'S': '<=0.5', 'I': '1', 'R': '>=2'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    },
    ('Pseudomonas aeruginosa', 'Gentamicin'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=16', 'I': '13-15', 'R': '<=12'}
    },

    # Acinetobacter spp. breakpoints
    ('Acinetobacter spp.', 'Ceftazidime'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=18', 'I': '15-17', 'R': '<=14'}
    },
    ('Acinetobacter spp.', 'Ciprofloxacin'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    }
}

# EUCAST 2025 Breakpoints (similar structure)
EUCAST_2025_BREAKPOINTS = {
    # Enterobacteriaceae breakpoints
    ('Enterobacteriaceae', 'Amoxicillin'): {
        'MIC': {'S': '<=8', 'I': '16', 'R': '>=32'},
        'DD': {'S': '>=20', 'I': '14-19', 'R': '<=13'}
    },
    ('Enterobacteriaceae', 'Ampicillin'): {
        'MIC': {'S': '<=8', 'I': None, 'R': '>=16'},
        'DD': {'S': '>=17', 'I': None, 'R': '<=16'}
    },
    ('Enterobacteriaceae', 'Ceftazidime'): {
        'MIC': {'S': '<=1', 'I': '2-4', 'R': '>=8'},
        'DD': {'S': '>=23', 'I': '20-22', 'R': '<=19'}
    },
    ('Enterobacteriaceae', 'Cefotaxime'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=23', 'I': '20-22', 'R': '<=19'}
    },
    ('Enterobacteriaceae', 'Ciprofloxacin'): {
        'MIC': {'S': '<=0.25', 'I': '0.5', 'R': '>=1'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    },
    ('Enterobacteriaceae', 'Gentamicin'): {
        'MIC': {'S': '<=2', 'I': '4', 'R': '>=8'},
        'DD': {'S': '>=16', 'I': '13-15', 'R': '<=12'}
    },
    ('Enterobacteriaceae', 'Tetracycline'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=16', 'I': '13-15', 'R': '<=12'}
    },

    # Staphylococcus aureus breakpoints
    ('Staphylococcus aureus', 'Methicillin'): {
        'MIC': {'S': '<=2', 'I': None, 'R': '>=4'},
        'DD': {'S': '>=10', 'I': None, 'R': '<=9'}
    },
    ('Staphylococcus aureus', 'Ciprofloxacin'): {
        'MIC': {'S': '<=0.5', 'I': '1', 'R': '>=2'},
        'DD': {'S': '>=22', 'I': '19-21', 'R': '<=18'}
    },
    ('Staphylococcus aureus', 'Gentamicin'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=16', 'I': '13-15', 'R': '<=12'}
    },

    # Enterococcus spp. breakpoints
    ('Enterococcus spp.', 'Ampicillin'): {
        'MIC': {'S': '<=4', 'I': None, 'R': '>=8'},
        'DD': {'S': '>=17', 'I': None, 'R': '<=16'}
    },
    ('Enterococcus spp.', 'Vancomycin'): {
        'MIC': {'S': '<=4', 'I': '8-16', 'R': '>=32'},
        'DD': {'S': '>=15', 'I': '10-14', 'R': '<=9'}
    },

    # Pseudomonas aeruginosa breakpoints
    ('Pseudomonas aeruginosa', 'Ceftazidime'): {
        'MIC': {'S': '<=8', 'I': '16', 'R': '>=32'},
        'DD': {'S': '>=18', 'I': '15-17', 'R': '<=14'}
    },
    ('Pseudomonas aeruginosa', 'Ciprofloxacin'): {
        'MIC': {'S': '<=0.5', 'I': '1', 'R': '>=2'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    },
    ('Pseudomonas aeruginosa', 'Gentamicin'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=16', 'I': '13-15', 'R': '<=12'}
    },

    # Acinetobacter spp. breakpoints
    ('Acinetobacter spp.', 'Ceftazidime'): {
        'MIC': {'S': '<=4', 'I': '8', 'R': '>=16'},
        'DD': {'S': '>=18', 'I': '15-17', 'R': '<=14'}
    },
    ('Acinetobacter spp.', 'Ciprofloxacin'): {
        'MIC': {'S': '<=1', 'I': '2', 'R': '>=4'},
        'DD': {'S': '>=21', 'I': '16-20', 'R': '<=15'}
    }
}

# Resistance mechanism patterns
RESISTANCE_MECHANISMS = {
    'ESBL': {
        'organisms': ['Escherichia coli', 'Klebsiella pneumoniae', 'Klebsiella spp.', 'Enterobacter spp.',
                     'Serratia spp.', 'Citrobacter spp.', 'Proteus spp.', 'Salmonella spp.'],
        'antibiotics': ['Ceftazidime', 'Cefotaxime', 'Ceftriaxone', 'Cefpodoxime', 'Aztreonam'],
        'pattern': 'resistance to 3rd generation cephalosporins',
        'confidence': 'High'
    },
    'Carbapenemase': {
        'organisms': ['Klebsiella pneumoniae', 'Escherichia coli', 'Enterobacter spp.', 'Serratia spp.',
                     'Citrobacter spp.', 'Acinetobacter spp.', 'Pseudomonas aeruginosa'],
        'antibiotics': ['Imipenem', 'Meropenem', 'Ertapenem', 'Doripenem'],
        'pattern': 'resistance to carbapenems',
        'confidence': 'High'
    },
    'MRSA': {
        'organisms': ['Staphylococcus aureus'],
        'antibiotics': ['Methicillin', 'Oxacillin'],
        'pattern': 'methicillin resistance',
        'confidence': 'High'
    },
    'VRE': {
        'organisms': ['Enterococcus faecalis', 'Enterococcus faecium', 'Enterococcus spp.'],
        'antibiotics': ['Vancomycin'],
        'pattern': 'vancomycin resistance',
        'confidence': 'High'
    },
    'AmpC': {
        'organisms': ['Enterobacter spp.', 'Citrobacter spp.', 'Serratia spp.', 'Morganella spp.',
                     'Providencia spp.', 'Pseudomonas aeruginosa', 'Acinetobacter spp.'],
        'antibiotics': ['Ceftazidime', 'Cefotaxime', 'Ceftriaxone', 'Cefpodoxime'],
        'pattern': 'resistance to cephalosporins with preserved susceptibility to carbapenems',
        'confidence': 'Moderate'
    }
}


class BreakpointInterpreter:
    """Automated breakpoint interpretation engine."""

    def __init__(self, guideline_version: str = "CLSI_2025"):
        """Initialize with specific guideline version."""
        self.guideline_version = guideline_version
        self.breakpoints = self._load_breakpoints()

    def _load_breakpoints(self) -> Dict:
        """Load breakpoint data for the specified guideline."""
        if self.guideline_version == "CLSI_2025":
            return CLSI_2025_BREAKPOINTS
        elif self.guideline_version == "EUCAST_2025":
            return EUCAST_2025_BREAKPOINTS
        else:
            raise ValueError(f"Unsupported guideline version: {self.guideline_version}")

    def _parse_threshold(self, threshold_str: str) -> Tuple[str, float]:
        """Parse threshold string like '<=8', '>=16', '8-16'."""
        if not threshold_str or threshold_str == 'None':
            return None, None

        if '<=' in threshold_str:
            return '<=', float(threshold_str.replace('<=', ''))
        elif '>=' in threshold_str:
            return '>=', float(threshold_str.replace('>=', ''))
        elif '-' in threshold_str:
            parts = threshold_str.split('-')
            return 'range', [float(parts[0]), float(parts[1])]
        else:
            return '=', float(threshold_str)

    def interpret_result(self, organism: str, antibiotic: str, method: str,
                        mic_value: Optional[float] = None,
                        zone_diameter: Optional[float] = None) -> Dict:
        """
        Interpret MIC or zone diameter result against breakpoints.

        Returns:
        {
            'interpretation': 'S'/'I'/'R',
            'guideline': str,
            'confidence': str,
            'suspected_mechanism': str or None,
            'breakpoint_used': dict,
            'notes': str
        }
        """

        # Normalize organism name for matching
        organism_norm = self._normalize_organism(organism)

        # Find matching breakpoint
        breakpoint_key = None
        for key in self.breakpoints.keys():
            org_pattern, ab_pattern = key
            if self._matches_pattern(organism_norm, org_pattern) and self._matches_pattern(antibiotic, ab_pattern):
                breakpoint_key = key
                break

        if not breakpoint_key:
            return {
                'interpretation': 'Unknown',
                'guideline': self.guideline_version,
                'confidence': 'No breakpoint available',
                'suspected_mechanism': None,
                'breakpoint_used': None,
                'notes': f'No breakpoint found for {organism} - {antibiotic}'
            }

        breakpoint_data = self.breakpoints[breakpoint_key]

        # Determine which method to use
        if method.upper() == 'MIC' and mic_value is not None:
            test_value = mic_value
            method_key = 'MIC'
        elif method.upper() == 'DD' and zone_diameter is not None:
            test_value = zone_diameter
            method_key = 'DD'
        else:
            return {
                'interpretation': 'Unknown',
                'guideline': self.guideline_version,
                'confidence': 'Invalid test method or missing value',
                'suspected_mechanism': None,
                'breakpoint_used': None,
                'notes': f'Invalid method ({method}) or missing test value'
            }

        if method_key not in breakpoint_data:
            return {
                'interpretation': 'Unknown',
                'guideline': self.guideline_version,
                'confidence': 'Method not supported for this breakpoint',
                'suspected_mechanism': None,
                'breakpoint_used': breakpoint_data,
                'notes': f'{method_key} breakpoints not available'
            }

        thresholds = breakpoint_data[method_key]

        # Interpret result
        interpretation = self._classify_result(test_value, thresholds, method_key)

        # Check for resistance mechanisms
        suspected_mechanism = self._infer_resistance_mechanism(organism_norm, antibiotic, interpretation)

        confidence = 'High'
        if suspected_mechanism and suspected_mechanism.get('confidence') == 'Moderate':
            confidence = 'Moderate - confirmatory test recommended'

        return {
            'interpretation': interpretation,
            'guideline': self.guideline_version,
            'confidence': confidence,
            'suspected_mechanism': suspected_mechanism.get('mechanism') if suspected_mechanism else None,
            'breakpoint_used': thresholds,
            'notes': f'Based on {method_key} value: {test_value}'
        }

    def _normalize_organism(self, organism: str) -> str:
        """Normalize organism name for matching."""
        # Remove extra spaces, convert to title case
        return ' '.join(organism.split()).title()

    def _matches_pattern(self, value: str, pattern: str) -> bool:
        """Check if value matches pattern (supports taxonomic groups and wildcards)."""
        value_lower = value.lower()
        pattern_lower = pattern.lower()

        if pattern.endswith(' spp.'):
            # Genus matching
            genus = pattern.replace(' spp.', '')
            return value_lower.startswith(genus)
        elif pattern_lower == 'enterobacteriaceae':
            # Enterobacteriaceae family matching
            enterobacteriaceae_genera = [
                'escherichia', 'klebsiella', 'enterobacter', 'salmonella',
                'shigella', 'citrobacter', 'serratia', 'proteus', 'providencia',
                'morganella', 'yersinia', 'erwinia'
            ]
            return any(genus in value_lower for genus in enterobacteriaceae_genera)
        elif pattern == 'staphylococcus spp.' or pattern == 'staphylococcus aureus':
            return 'staphylococcus' in value_lower
        elif pattern == 'enterococcus spp.':
            return 'enterococcus' in value_lower
        elif pattern == 'pseudomonas spp.' or pattern == 'pseudomonas aeruginosa':
            return 'pseudomonas' in value_lower
        elif pattern == 'acinetobacter spp.':
            return 'acinetobacter' in value_lower
        else:
            # Exact match or contains
            return pattern_lower in value_lower or value_lower == pattern_lower

    def _classify_result(self, test_value: float, thresholds: Dict, method: str) -> str:
        """Classify test result as S/I/R based on thresholds."""

        # Parse thresholds
        s_op, s_val = self._parse_threshold(thresholds.get('S'))
        i_op, i_val = self._parse_threshold(thresholds.get('I'))
        r_op, r_val = self._parse_threshold(thresholds.get('R'))

        # For MIC (lower values = more susceptible)
        if method == 'MIC':
            if r_val is not None:
                if r_op == '>=' and test_value >= r_val:
                    return 'R'
                elif r_op == '=' and test_value == r_val:
                    return 'R'

            if i_val is not None:
                if isinstance(i_val, list):
                    if i_val[0] <= test_value <= i_val[1]:
                        return 'I'
                elif i_op == '=' and test_value == i_val:
                    return 'I'

            if s_val is not None:
                if s_op == '<=' and test_value <= s_val:
                    return 'S'
                elif s_op == '>=' and test_value >= s_val:
                    return 'S'

        # For disk diffusion (higher values = more susceptible)
        elif method == 'DD':
            if s_val is not None:
                if s_op == '>=' and test_value >= s_val:
                    return 'S'
                elif s_op == '<=' and test_value <= s_val:
                    return 'S'

            if i_val is not None:
                if isinstance(i_val, list):
                    if i_val[0] <= test_value <= i_val[1]:
                        return 'I'
                elif i_op == '=' and test_value == i_val:
                    return 'I'

            if r_val is not None:
                if r_op == '<=' and test_value <= r_val:
                    return 'R'
                elif r_op == '>=' and test_value >= r_val:
                    return 'R'

        return 'Unknown'

    def _infer_resistance_mechanism(self, organism: str, antibiotic: str, interpretation: str) -> Optional[Dict]:
        """Infer possible resistance mechanism based on patterns."""
        if interpretation != 'R':
            return None

        for mechanism_name, mechanism_data in RESISTANCE_MECHANISMS.items():
            # Check if organism matches
            organism_match = any(self._matches_pattern(organism, org) for org in mechanism_data['organisms'])

            # Check if antibiotic matches
            antibiotic_match = any(self._matches_pattern(antibiotic, ab) for ab in mechanism_data['antibiotics'])

            if organism_match and antibiotic_match:
                return {
                    'mechanism': mechanism_name,
                    'confidence': mechanism_data['confidence'],
                    'pattern': mechanism_data['pattern']
                }

        return None

    def batch_interpret(self, ast_df: pd.DataFrame) -> pd.DataFrame:
        """Interpret all results in a DataFrame."""
        results = []

        for _, row in ast_df.iterrows():
            interpretation = self.interpret_result(
                organism=row['organism'],
                antibiotic=row['antibiotic'],
                method=row['method'],
                mic_value=row.get('mic_value'),
                zone_diameter=row.get('zone_diameter')
            )

            results.append({
                'isolate_id': row['isolate_id'],
                'organism': row['organism'],
                'antibiotic': row['antibiotic'],
                'original_result': row.get('result', ''),
                'interpreted_result': interpretation['interpretation'],
                'guideline': interpretation['guideline'],
                'confidence': interpretation['confidence'],
                'suspected_mechanism': interpretation['suspected_mechanism'],
                'notes': interpretation['notes']
            })

        return pd.DataFrame(results)


# Global interpreter instances
CLSI_INTERPRETER = BreakpointInterpreter("CLSI_2025")
EUCAST_INTERPRETER = BreakpointInterpreter("EUCAST_2025")


def get_interpreter(guideline: str = "CLSI") -> BreakpointInterpreter:
    """Get interpreter instance for specified guideline."""
    if guideline.upper() == "CLSI":
        return CLSI_INTERPRETER
    elif guideline.upper() == "EUCAST":
        return EUCAST_INTERPRETER
    else:
        raise ValueError(f"Unsupported guideline: {guideline}")


def interpret_ast_result(organism: str, antibiotic: str, method: str,
                        mic_value: Optional[float] = None,
                        zone_diameter: Optional[float] = None,
                        guideline: str = "CLSI") -> Dict:
    """Convenience function for single result interpretation."""
    interpreter = get_interpreter(guideline)
    return interpreter.interpret_result(organism, antibiotic, method, mic_value, zone_diameter)


def batch_interpret_results(ast_df: pd.DataFrame, guideline: str = "CLSI") -> pd.DataFrame:
    """Convenience function for batch interpretation."""
    interpreter = get_interpreter(guideline)
    return interpreter.batch_interpret(ast_df)