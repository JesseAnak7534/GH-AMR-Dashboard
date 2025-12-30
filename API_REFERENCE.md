# Advanced AMR Analysis Functions - API Reference

## Module: `src.plots`

### Core Functions

#### `calculate_resistance_percentage(ast_df: pd.DataFrame) -> pd.DataFrame`
Calculates resistance percentage for organism-antibiotic combinations.

**Parameters:**
- `ast_df`: AST results DataFrame

**Returns:**
- DataFrame with columns:
  - organism, antibiotic, total_tests
  - resistant, intermediate, susceptible counts
  - percent_resistant, percent_intermediate, percent_susceptible

**Example:**
```python
from src import db, plots
ast_data = db.get_all_ast_results()
resistance_stats = plots.calculate_resistance_percentage(ast_data)
print(resistance_stats.head())
```

---

### Visualization Functions

#### `plot_top_antibiotics(ast_df, max_items=30) -> go.Figure`
Creates bar chart of top antibiotics by resistance percentage.

**Usage:**
```python
fig = plots.plot_top_antibiotics(ast_df)
st.plotly_chart(fig, use_container_width=True)
```

---

#### `plot_resistance_by_category(ast_df, samples_df) -> go.Figure`
Creates stacked bar chart showing resistance by source category (ENVIRONMENT vs FOOD).

**Usage:**
```python
fig = plots.plot_resistance_by_category(filtered_ast, filtered_samples)
st.plotly_chart(fig, use_container_width=True)
```

---

#### `plot_resistance_by_source_type(ast_df, samples_df) -> go.Figure`
Creates stacked bar chart showing resistance by specific source type (water, meat, etc.).

**Usage:**
```python
fig = plots.plot_resistance_by_source_type(ast_df, samples_df)
st.plotly_chart(fig, use_container_width=True)
```

---

#### `plot_resistance_trends(ast_df, time_aggregation='Monthly') -> go.Figure`
Creates line chart showing resistance trends over time.

**Parameters:**
- `ast_df`: AST results with valid test_date
- `time_aggregation`: 'Monthly', 'Quarterly', or 'Yearly'

**Usage:**
```python
fig = plots.plot_resistance_trends(ast_df, 'Monthly')
st.plotly_chart(fig, use_container_width=True)
```

---

#### `plot_organism_antibiotic_heatmap(ast_df) -> go.Figure`
Creates heatmap showing resistance % for organism-antibiotic combinations.

**Features:**
- Shows top 8 organisms vs top 10 antibiotics
- Color scale: green=low, red=high resistance
- Interactive hover for exact percentages

**Usage:**
```python
fig = plots.plot_organism_antibiotic_heatmap(ast_df)
st.plotly_chart(fig, use_container_width=True)
```

---

#### `plot_resistance_distribution(ast_df) -> go.Figure`
Creates pie chart showing overall S/I/R distribution.

**Usage:**
```python
fig = plots.plot_resistance_distribution(ast_df)
st.plotly_chart(fig, use_container_width=True)
```

---

#### `plot_point_map(samples_df, ast_df) -> go.Figure`
Creates geographic point map with resistance indicators.

**Requirements:**
- Samples must have latitude and longitude

**Usage:**
```python
samples_with_coords = samples_df[samples_df['latitude'].notna()]
fig = plots.plot_point_map(samples_with_coords, ast_df)
st.plotly_chart(fig, use_container_width=True)
```

---

### Advanced Analysis Functions

#### `detect_mdr_isolates(ast_df, resistance_threshold=3) -> pd.DataFrame`
Detects multi-drug resistant (MDR) isolates.

**Definition:**
- MDR: Resistant to ≥3 different drug classes

**Supported Drug Classes:**
- Beta-lactams (Ampicillin, Cephalosporin, etc.)
- Quinolones (Ciprofloxacin, Norfloxacin)
- Aminoglycosides (Gentamicin, Streptomycin)
- Tetracyclines (Tetracycline, Doxycycline)
- Sulfonamides, Macrolides, etc.

**Returns:**
- DataFrame with columns:
  - isolate_id, organism, sample_id
  - resistant_drug_classes (count)

**Example:**
```python
mdr_data = plots.detect_mdr_isolates(ast_df)
if not mdr_data.empty:
    st.warning(f"⚠️ {len(mdr_data)} MDR isolates detected")
    st.dataframe(mdr_data)
```

---

#### `get_co_resistance_patterns(ast_df, min_samples=5) -> pd.DataFrame`
Identifies common antibiotic resistance combinations within isolates.

**Parameters:**
- `ast_df`: AST results
- `min_samples`: Minimum occurrence threshold (default: 5)

**Returns:**
- DataFrame with columns:
  - antibiotic_combination (comma-separated)
  - count (number of isolates with this pattern)

**Example:**
```python
patterns = plots.get_co_resistance_patterns(ast_df, min_samples=3)
st.dataframe(patterns.head(10))
```

**Interpretation:**
- Identifies which antibiotics commonly resist together
- Helps understand resistance mechanisms
- Informs combination therapy strategies

---

#### `get_top_districts_by_resistance(ast_df, samples_df, top_n=10) -> pd.DataFrame`
Ranks districts by resistance percentage.

**Returns:**
- DataFrame with columns:
  - district, total_tests
  - resistant (count), percent_resistant

**Example:**
```python
hotspots = plots.get_top_districts_by_resistance(ast_df, samples_df, top_n=15)
st.dataframe(hotspots)
```

---

#### `get_surveillance_alerts(ast_df, samples_df) -> List[Dict]`
Generates automated surveillance alerts based on thresholds.

**Alert Types:**
1. **Overall Resistance Alert**: Triggered if >30% overall resistance
2. **MDR Detection**: Alerts if MDR isolates present
3. **High-Risk Combinations**: If organism-antibiotic >50% R with ≥10 tests

**Alert Structure:**
```python
{
    'severity': 'HIGH' | 'MEDIUM' | 'INFO',
    'message': str,
    'type': str  # resistance_threshold, mdr_detection, high_resistance_combo
}
```

**Example:**
```python
alerts = plots.get_surveillance_alerts(ast_df, samples_df)
for alert in alerts:
    if alert['severity'] == 'HIGH':
        st.error(f"🔴 {alert['message']}")
    elif alert['severity'] == 'MEDIUM':
        st.warning(f"🟠 {alert['message']}")
```

---

## Integration Examples

### Complete Analysis Pipeline

```python
from src import db, plots
import streamlit as st

# Load data
all_ast = db.get_all_ast_results()
all_samples = db.get_all_samples()

# Get resistance statistics
resistance_stats = plots.calculate_resistance_percentage(all_ast)

# Display top antibiotics
st.plotly_chart(plots.plot_top_antibiotics(all_ast))

# Detect MDR
mdr = plots.detect_mdr_isolates(all_ast)
st.metric("MDR Isolates", len(mdr))

# Identify patterns
patterns = plots.get_co_resistance_patterns(all_ast)
st.dataframe(patterns.head(10))

# Find hotspots
hotspots = plots.get_top_districts_by_resistance(all_ast, all_samples)
st.dataframe(hotspots)

# Generate alerts
alerts = plots.get_surveillance_alerts(all_ast, all_samples)
for alert in alerts:
    st.warning(alert['message'])
```

---

## AMR Interpretation Guide

### Resistance Thresholds (WHO Standards)

| Category | Interpretation |
|----------|-----------------|
| 0-10% | Wild-type, normal susceptibility |
| 10-25% | Low-level resistance |
| 25-50% | Moderate resistance |
| >50% | High resistance, treatment concern |

### MDR vs XDR vs PDR

- **MDR**: Resistant to ≥3 drug classes
- **XDR** (Extensively Drug Resistant): Susceptible to <5 drug classes
- **PDR** (Pandrug Resistant): Resistant to ALL available options

### Co-Resistance Implications

Common patterns indicate:
- **Shared resistance mechanisms**: Same gene/enzyme affecting multiple drugs
- **Selective pressure**: Multiple drugs used in same setting
- **Treatment constraints**: Limited therapeutic options

---

## Performance Considerations

- **Large datasets (>100K tests)**: Use filtering before analysis
- **Memory**: Heatmap limited to top 8 organisms, top 10 antibiotics
- **Date parsing**: Ensure YYYY-MM-DD format for trend analysis
- **Null handling**: All functions gracefully handle missing data

---

## Future Enhancements

Planned additions:
- [ ] Machine learning-based resistance prediction
- [ ] Temporal hotspot tracking
- [ ] Integration with clinical outcomes
- [ ] Automated report generation
- [ ] Statistical significance testing
- [ ] Epidemiological curve fitting

---

**Documentation Version:** 2.0  
**Last Updated:** December 2025  
**Status:** Complete & Tested
