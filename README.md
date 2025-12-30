# AMR Surveillance Dashboard
**Environment & Food Samples | Ghana**

A production-ready Streamlit application for monitoring Antimicrobial Resistance (AMR) in environmental and food samples across Ghana. Built for academic research and policy decision-making.

---

## Features

✅ **Data Upload & Validation**
- Excel import with strict schema validation
- Auto-generated template for consistent data entry
- Human-readable error reporting

✅ **Interactive Dashboards**
- **Resistance Overview**: Multi-filter analysis with charts
- **Trends**: Time-series tracking of resistance patterns
- **Map Hotspots**: Geographic visualization with district rankings
- **Report Export**: HTML reports with summary statistics

✅ **Local Data Storage**
- SQLite database (auto-created)
- No external APIs or internet required
- Full data privacy and control

---

## Quick Start

### 1. Install Python 3.10+

Verify installation:
```bash
python --version
```

### 2. Clone or Extract Project

```bash
cd amr_env_food_dashboard
```

### 3. Create Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the Dashboard

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

### Optional: Admin Account Setup

To enable an initial admin user, create a `.env` file in the project root:

```env
ADMIN_EMAIL=your.admin@example.com
ADMIN_PASSWORD=StrongPassword123!
```

On first launch, the app will create this admin account if it does not exist. Otherwise, you can use the Sign Up tab to create standard users.


## Project Structure

```
amr_env_food_dashboard/
├── app.py                  # Main Streamlit app
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── .gitignore            # Git ignore rules
│
├── src/
│   ├── db.py            # Database operations
│   ├── validate.py      # Data validation
│   ├── plots.py         # Chart generation
│   └── report.py        # Report generation
│
├── db/                  # SQLite database (auto-created)
├── templates/           # Excel template
├── data/
│   ├── geo/            # GeoJSON files (optional)
│   └── lookups/        # Reference data
│
└── [venv/]             # Virtual environment (auto-created)
```

---

## Data Upload Guide

### Step 1: Download Template
1. Navigate to **Upload & Data Quality** page
2. Click **📥 Download Template**
3. Fill in your data in Excel

### Step 2: Excel Format

**Sheet 1: `samples`**
| Column | Required | Format | Example |
|--------|----------|--------|---------|
| sample_id | ✓ | Text | SAMPLE_001 |
| collection_date | ✓ | YYYY-MM-DD | 2024-01-15 |
| region | ✓ | Text | Ashanti |
| district | ✓ | Text | Kumasi |
| site_type | ✓ | Text | Water Treatment |
| source_category | ✓ | ENVIRONMENT or FOOD | ENVIRONMENT |
| source_type | ✓ | Text | water, meat, etc. |
| food_matrix | • | Text | chicken, milk |
| environment_matrix | • | Text | treated_water |
| latitude | • | Decimal (-90 to 90) | 6.6326 |
| longitude | • | Decimal (-180 to 180) | -1.6243 |

**Sheet 2: `ast_results`**
| Column | Required | Format | Example |
|--------|----------|--------|---------|
| sample_id | ✓ | Text | SAMPLE_001 |
| isolate_id | ✓ | Text | ISO_001 |
| organism | ✓ | Text | E. coli |
| antibiotic | ✓ | Text | Ampicillin |
| result | ✓ | S, I, or R | R |
| method | ✓ | DD or MIC | DD |
| guideline | ✓ | CLSI or EUCAST | CLSI |
| test_date | ✓ | YYYY-MM-DD | 2024-01-20 |
| mic_value | • | Decimal (numeric) | 0.5 |

✓ = Required  
• = Optional

### Step 3: Validate & Upload
1. Click **Upload Excel file**
2. Click **✓ Validate Upload**
3. Review error messages if validation fails
4. Data automatically saved to database

---

## Validation Rules

The system enforces strict validation:

- ✓ All required columns must be present
- ✓ Dates must be in YYYY-MM-DD format
- ✓ `source_category` must be ENVIRONMENT or FOOD
- ✓ `result` must be S (susceptible), I (intermediate), or R (resistant)
- ✓ `method` must be DD (disk diffusion) or MIC (broth microdilution)
- ✓ `guideline` must be CLSI or EUCAST
- ✓ All AST results must reference existing sample_id
- ✓ No duplicate isolate_id + antibiotic combinations
- ✓ Coordinates (if provided) must be valid latitude/longitude
- ✓ No duplicate sample_id values

---

## Database Schema

### datasets
Metadata about each upload:
```sql
CREATE TABLE datasets (
    dataset_id TEXT PRIMARY KEY,
    dataset_name TEXT,
    uploaded_by TEXT,
    uploaded_at TEXT,
    rows_samples INTEGER,
    rows_tests INTEGER
);
```

### samples
Sample information:
```sql
CREATE TABLE samples (
    dataset_id TEXT,
    sample_id TEXT,
    collection_date TEXT,
    region TEXT,
    district TEXT,
    site_type TEXT,
    source_category TEXT,      -- ENVIRONMENT or FOOD
    source_type TEXT,
    food_matrix TEXT,
    environment_matrix TEXT,
    latitude REAL,
    longitude REAL,
    PRIMARY KEY (dataset_id, sample_id)
);
```

### ast_results
Antimicrobial susceptibility test results:
```sql
CREATE TABLE ast_results (
    dataset_id TEXT,
    sample_id TEXT,
    isolate_id TEXT,
    organism TEXT,
    antibiotic TEXT,
    result TEXT,               -- S/I/R
    method TEXT,              -- DD/MIC
    guideline TEXT,           -- CLSI/EUCAST
    test_date TEXT,
    mic_value REAL,
    PRIMARY KEY (dataset_id, isolate_id, antibiotic)
);
```

---

## Filtering & Analysis

### Available Filters
- **Organism**: Filter by pathogen
- **Antibiotic**: Filter by antimicrobial agent
- **Source Category**: ENVIRONMENT or FOOD
- **Region**: Geographic region
- **District**: Specific district
- **Date Range**: Time period (coming soon)

### Time Aggregation
- **Monthly**: Month-by-month trends
- **Quarterly**: 3-month aggregation
- **Yearly**: Annual trends

---

## Geographic Data (Choropleth Maps)

To enable district-level choropleth maps:

1. **Obtain Ghana District GeoJSON**
   - Sources: World Bank Data, Ghana Statistical Service, OSM
   
2. **Save file**: `data/geo/ghana_districts.geojson`

3. **Format requirements**:
   - Must be valid GeoJSON FeatureCollection
   - Each feature must include district name in properties
   - District names must match your sample data

4. **Example**:
   ```json
   {
     "type": "FeatureCollection",
     "features": [
       {
         "type": "Feature",
         "properties": {"district": "Accra"},
         "geometry": { "type": "Polygon", "coordinates": [...] }
       }
     ]
   }
   ```

---

## Report Export

Generate downloadable HTML reports with:
- Summary statistics (samples, tests, organisms)
- Overall resistance percentage
- Resistance by source category and type
- Top antibiotics by resistance
- Top districts by hotspot ranking
- Professional formatting for presentations and publications

---

## Troubleshooting

### App won't start
```bash
# Activate virtual environment
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Run with verbose output
streamlit run app.py --logger.level=debug
```

### Import errors
```bash
# Check installed packages
pip list

# Reinstall specific package
pip install --force-reinstall pandas==2.1.4
```

### Database errors
```bash
# Delete old database to reset
rm db/amr_data.db
# Re-run app (database will recreate)
streamlit run app.py
```

### Upload validation issues
- Ensure Excel sheet names are exactly: `samples` and `ast_results`
- Check that all required columns are present (case-sensitive)
- Verify date format is YYYY-MM-DD
- Ensure sample_id values in ast_results match samples sheet

---

## Technology Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.10+ | Core language |
| Streamlit | 1.31.1 | Web interface |
| pandas | 2.1.4 | Data manipulation |
| numpy | 1.24.3 | Numerical operations |
| Plotly | 5.18.0 | Interactive charts |
| SQLite3 | Built-in | Database |
| openpyxl | 3.1.2 | Excel handling |
| pydantic | 2.5.3 | Data validation |

---

## For Policy & Academic Use

### Citation
When using data from this dashboard in publications:
```
AMR Surveillance Dashboard for Environment & Food Samples, Ghana
Version 1.0 | Generated [Date]
Data: [Your Dataset Name]
```

### Data Quality Considerations
- Ensure consistent laboratory methods across samples
- Document any changes in collection or testing protocols
- Consider temporal and geographic bias in interpretations
- Always validate findings with domain experts

### Recommendations
- Regular data quality audits
- Staff training on standard protocols
- Integration with national AMR surveillance systems
- Linkage with clinical AMR data for context

---

## License & Support

**License**: Open source (academic and policy use)

**Support**:
- Check README for common issues
- Review validation error messages carefully
- Consult AMR experts for interpretations
- Test with small datasets first

---

## Version History

**v1.0 (Dec 2024)**
- Initial release
- 5 interactive dashboards
- Excel upload & validation
- HTML report export
- SQLite backend
- Ghana geographic focus

---

## Future Enhancements

🔜 **Planned Features**
- Predictive modeling (resistance risk prediction)
- Choropleth maps (with GeoJSON integration)
- Multi-file batch uploads
- User authentication & roles
- Automated data quality reports
- Integration with LIMS systems
- Mobile-responsive interface
- Advanced statistical analysis

---

**Built for surveillance, science, and safety.**  
*Environment + Food AMR Monitoring | Ghana*

Last Updated: December 2024
#   A M R - S u r v e i l l a n c e - D a s h b o a r d 
 
 #   A M R - S u r v e i l l a n c e - D a s h b o a r d 
 
 