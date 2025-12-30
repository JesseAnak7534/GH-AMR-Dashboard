# Quick Start Guide - Testing AMR Dashboard

## 🚀 Getting Started with Sample Data

### Step 1: Launch the App
```powershell
cd amr_env_food_dashboard
.\venv\Scripts\python.exe -m streamlit run app.py
```

The app will open at: **http://localhost:8501**

---

## 📥 Upload Sample Data

### Method 1: Use Auto-Generated Template

1. Go to **Upload & Data Quality** page
2. Click **📥 Download Template**
3. A template file will download

### Method 2: Create Sample Data Manually

**Excel File Structure:**

**Sheet 1: "samples"**
```
sample_id | collection_date | region | district | site_type | source_category | source_type | food_matrix | environment_matrix | latitude | longitude
SAM_001   | 2024-01-15      | Ashanti | Kumasi   | Farm      | FOOD            | chicken     | poultry     |                    | 6.6326   | -1.6243
SAM_002   | 2024-01-20      | Ashanti | Sekondi  | Water     | ENVIRONMENT     | water       |             | treated_water      | 5.0000   | -2.4333
SAM_003   | 2024-02-05      | Greater Accra | Accra | Hospital | ENVIRONMENT | effluent | | surface_water | 5.6037 | -0.1870
SAM_004   | 2024-02-15      | Central | Cape Coast | Market | FOOD | fish | seafood | | 5.1000 | -1.2500
```

**Sheet 2: "ast_results"**
```
sample_id | isolate_id | organism | antibiotic | result | method | guideline | test_date | mic_value
SAM_001   | ISO_001    | E. coli  | Ampicillin | R      | DD     | CLSI      | 2024-01-18|
SAM_001   | ISO_001    | E. coli  | Ciprofloxacin | S   | DD     | CLSI      | 2024-01-18|
SAM_001   | ISO_002    | E. coli  | Ampicillin | R      | DD     | CLSI      | 2024-01-19|
SAM_001   | ISO_002    | E. coli  | Tetracycline | R    | DD     | CLSI      | 2024-01-19|
SAM_001   | ISO_002    | E. coli  | Gentamicin | R      | MIC    | CLSI      | 2024-01-19| 0.125
SAM_002   | ISO_003    | Salmonella | Ampicillin | I    | DD     | CLSI      | 2024-01-23|
SAM_002   | ISO_003    | Salmonella | Ciprofloxacin | S  | DD     | CLSI      | 2024-01-23|
SAM_003   | ISO_004    | Vibrio   | Tetracycline | S    | DD     | EUCAST    | 2024-02-08|
SAM_003   | ISO_004    | Vibrio   | Ampicillin | S      | DD     | EUCAST    | 2024-02-08|
SAM_004   | ISO_005    | Staphylococcus | Methicillin | R | DD | CLSI | 2024-02-18|
```

---

## 🎯 Step-by-Step Testing

### Step 1: Upload Data
1. Go to **Upload & Data Quality**
2. Click **Upload Excel file**
3. Select your sample Excel file
4. Click **✓ Validate Upload**
5. Should see: "✓ Validation successful!"
6. Data saved with a dataset ID

### Step 2: Explore Resistance Overview
1. Click **Resistance Overview** in sidebar
2. Filters will auto-populate with available values
3. You should see:
   - ✅ Overall resistance % metric
   - ✅ Bar chart of top antibiotics
   - ✅ Pie chart showing S/I/R distribution
   - ✅ Stacked bar charts by category and type
   - ✅ Heatmap of organism-antibiotic resistance
   - ✅ MDR isolates (if any detected)
   - ✅ Co-resistance patterns
   - ✅ Data preview table

### Step 3: View Resistance Trends
1. Click **Trends** in sidebar
2. Select organisms and antibiotics
3. Choose time aggregation (Monthly/Quarterly/Yearly)
4. You should see:
   - ✅ Line chart with trend over time
   - ✅ Date range summary
   - ✅ Recent test data

### Step 4: Explore Geographic Hotspots
1. Click **Map Hotspots** in sidebar
2. If latitude/longitude provided:
   - ✅ Point map showing sample locations
3. Always shows:
   - ✅ Top districts by resistance % table
   - ✅ Bar chart of top hotspots
   - ✅ Surveillance alerts

### Step 5: Generate Report
1. Click **Report Export** in sidebar
2. Select dataset from dropdown
3. Click **📊 Generate Report**
4. Click **📥 Download HTML Report**
5. Open HTML file in browser for professional report

---

## 📊 Expected Results with Sample Data

### Resistance Overview
- **Overall Resistance**: Should show ~50-60% based on sample data
- **Top Antibiotics**: Ampicillin should rank highest
- **Source Category**: FOOD vs ENVIRONMENT comparison
- **Heatmap**: Shows E. coli with high ampicillin resistance

### MDR Detection
- Should detect **ISO_002** as MDR (resistant to 3 drugs: Ampicillin, Tetracycline, Gentamicin)
- Warning: "⚠️ 1 multi-drug resistant isolate detected"

### Co-Resistance Patterns
- "Ampicillin, Tetracycline, Gentamicin" = 1 occurrence
- Shows natural clustering of resistance mechanisms

### Hotspots
- Kumasi should rank highest (2 resistant tests out of samples)
- Accra, Sekondi, Cape Coast, others follow

---

## 🔍 Testing Different Scenarios

### Scenario 1: FOOD vs ENVIRONMENT Comparison
1. Go to Resistance Overview
2. Filter: source_category = "FOOD" only
3. Notice higher resistance in food samples
4. Switch to "ENVIRONMENT" to compare

### Scenario 2: Organism-Specific Analysis
1. Go to Resistance Overview
2. Filter: organism = "E. coli" only
3. See that E. coli has highest resistance
4. Check co-resistance patterns

### Scenario 3: Temporal Trends
1. Go to Trends
2. Select time_aggregation = "Monthly"
3. See resistance increase over time
4. Switch to "Quarterly" for broader view

### Scenario 4: Geographic Risk
1. Go to Map Hotspots
2. Check which districts have highest resistance
3. Look at surveillance alerts
4. Note MDR and high-risk combinations

---

## ✅ Validation Checklist

After uploading sample data, verify:

- [ ] Data saved successfully (dataset ID shown)
- [ ] Overall metrics display correctly
- [ ] All charts render without errors
- [ ] Filters work and update charts
- [ ] Trends show temporal patterns
- [ ] Hotspots identify high-risk districts
- [ ] MDR detection works
- [ ] Co-resistance patterns detected
- [ ] Surveillance alerts generated
- [ ] HTML report downloads and displays

---

## 🐛 Troubleshooting

### Issue: "No data available"
**Solution:**
- Verify both sheets exist (samples, ast_results)
- Check required columns are present
- Ensure sample_id values match between sheets
- Confirm no empty cells in required fields

### Issue: Charts not displaying
**Solution:**
- Check data type - ensure organisms/antibiotics are strings
- Verify date format is YYYY-MM-DD
- Try filtering to subset of data
- Reload page (F5)

### Issue: MDR not detected
**Solution:**
- Verify isolates have 3+ resistant antibiotics
- Check antibiotic names match drug class mapping
- Use consistent spelling (e.g., "Ampicillin" not "Amoxicillin")

### Issue: Trends show no line
**Solution:**
- Confirm test_date column has valid dates
- Ensure dates span multiple months for Monthly aggregation
- Check date format matches YYYY-MM-DD

---

## 📝 Sample Data Download

Click "📥 Download Template" in the Upload page to get a pre-formatted Excel file with proper column names and example data.

---

## 🎓 Learning Path

1. **Beginner**: Upload sample data → Explore Resistance Overview
2. **Intermediate**: Add filters → Analyze by region/source
3. **Advanced**: Check trends → Detect MDR → Identify patterns
4. **Expert**: Generate reports → Integrate findings → Make recommendations

---

## 🔗 Next Steps

After testing with sample data:

1. **Replace with Real Data**: Upload actual AMR surveillance data
2. **Configure Regions**: Add your specific regions/districts
3. **Set Thresholds**: Adjust MDR and alert thresholds
4. **Create Reports**: Generate regular surveillance reports
5. **Share Results**: Export and distribute findings

---

**Ready to test?** 🚀  
Start with the **Upload & Data Quality** page and follow the steps above!
