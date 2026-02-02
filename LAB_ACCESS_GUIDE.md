# Lab Access & KoboToolbox Integration Guide

## Overview

The AMR Surveillance Dashboard has been updated to:
1. **Restrict access to only authorized labs and admin**
2. **Add lab field to data collection template**
3. **Integrate with KoboToolbox for remote data entry**
4. **Provide lab-specific credentials**

## Lab-Only Access System

### Approved Laboratories

Only personnel from the following sentinel site laboratories have system access:

1. Eastern Regional Hospital
2. St. Martin De Porres Hospital, Eikwe
3. Sekondi Public Health Reference Laboratory
4. Ho Teaching Hospital
5. Tamale Teaching Hospital
6. Komfo Anokye Teaching Hospital
7. Korle-Bu Teaching Hospital
8. Lekma Hospital
9. Sunyani Teaching Hospital
10. Cape Coast Teaching Hospital
11. National Food Safety Laboratory
12. CSIR – Water Research Institute (Microbiology Laboratory)
13. Accra Veterinary Laboratory
14. Kumasi Veterinary Laboratory
15. Quadushah Medical Diagnostic Limited
16. Central Veterinary Laboratory
17. Pong Tamale School
18. Metropolis Health Care Limited
19. Alma Medical Laboratory Ltd

### Lab User Credentials

Each laboratory has been assigned unique login credentials in the format:
- **Email**: `{lab_username}@sentinel-amr.lab`
- **Password**: (Provided separately to each laboratory)

#### Lab Username Mappings

| Laboratory Name | Username |
|---|---|
| Eastern Regional Hospital | eastern_regional_hospital |
| St. Martin De Porres Hospital Eikwe | st_martin_de_porres_hospital |
| Sekondi Public Health Reference Lab | sekondi_public_health_lab |
| Ho Teaching Hospital | ho_teaching_hospital |
| Tamale Teaching Hospital | tamale_teaching_hospital |
| Komfo Anokye Teaching Hospital | komfo_anokye_teaching_hospital |
| Korle-Bu Teaching Hospital | korle_bu_teaching_hospital |
| Lekma Hospital | lekma_hospital |
| Sunyani Teaching Hospital | sunyani_teaching_hospital |
| Cape Coast Teaching Hospital | cape_coast_teaching_hospital |
| National Food Safety Laboratory | national_food_safety_laboratory |
| CSIR Water Research Institute | csir_water_research_institute |
| Accra Veterinary Laboratory | accra_veterinary_laboratory |
| Kumasi Veterinary Laboratory | kumasi_veterinary_laboratory |
| Quadushah Medical Diagnostic | quadushah_medical_diagnostic |
| Central Veterinary Laboratory | central_veterinary_laboratory |
| Pong Tamale School | pong_tamale_school |
| Metropolis Health Care Limited | metropolis_health_care |
| Alma Medical Laboratory Ltd | alma_medical_laboratory |

### Setting Up Lab Accounts

Lab accounts have been pre-configured. To set them up in a fresh installation:

```bash
python setup_lab_accounts.py
```

This script will:
- Create user accounts for all approved laboratories
- Set each lab's initial password
- Mark accounts as verified and active
- Display credentials for distribution to each lab

## Lab Field Addition

### Updated Template

The Excel template now includes a required **Lab Name** field:

- **Column Name**: `lab_name`
- **Required**: Yes
- **Format**: Select from dropdown list of approved laboratories
- **Purpose**: Track which laboratory submitted each sample

### Using the Template

1. Open the downloaded template file
2. In the `samples` sheet, fill in the `lab_name` column
3. Select from the list of approved laboratories
4. Complete other required fields as usual

### Lab-Specific Data Viewing

Lab users can only view and work with data that includes their laboratory in the `lab_name` field.

## KoboToolbox Integration

### Overview

KoboToolbox provides a mobile-friendly interface for remote data entry. Labs can use the form to:
- Submit AST results from the field
- Sync data with the central dashboard
- View their laboratory's historical data

### KoboToolbox Setup

#### 1. Administrator Configuration

The system administrator should:

1. Have KoboToolbox account with credentials:
   - **Username**: jesseanak
   - **Password**: Jese@1998

2. Create the AMR form in KoboToolbox using the integrated form builder

3. Share the KoboToolbox form link with each laboratory

#### 2. Lab Configuration

Each laboratory:

1. Creates a KoboToolbox account (free at https://kf.kobotoolbox.org)
2. Receives the AMR form link from the administrator
3. Accesses the form on mobile or web browser
4. Submits AST data with proper lab identification

#### 3. Data Synchronization

When labs submit data through KoboToolbox:

1. Click "Sync" in the dashboard
2. System fetches new submissions from KoboToolbox
3. Data is automatically validated and imported
4. Results appear in the lab's dashboard within minutes

### KoboToolbox Form Fields

The integrated form includes:

#### Laboratory Section
- Lab Name (required dropdown)
- Sample Collection Date (required date)

#### Sample Section
- Sample ID (required text)
- Source Category (required: ENVIRONMENT, FOOD, HUMAN, ANIMAL, AQUACULTURE)
- Source Type (required text)
- Region (required text)
- District (required text)

#### AST Results Section
- Isolate ID (required text)
- Organism (required text)
- Antibiotic Tested (required text)
- AST Result (required: S, I, R)
- Testing Method (required: DD, MIC)
- Breakpoint Guideline (required: CLSI, EUCAST)
- Test Date (required date)

### Mobile Data Collection

Benefits of KoboToolbox for labs:

- **Offline capability**: Collect data without internet, sync when connected
- **Form validation**: Automatic checks prevent invalid data entry
- **Mobile-optimized**: Works on smartphones and tablets
- **Easy sharing**: Link can be sent via email or SMS
- **Real-time syncing**: Data available immediately in dashboard
- **Backup**: All submissions stored in KoboToolbox cloud

### Sync Process

```python
from src.lab_management import KoboToolboxManager

# Initialize manager
kobo = KoboToolboxManager(username="jesseanak", password="Jese@1998")

# Authenticate
success, msg = kobo.authenticate()

# Fetch data
success, msg, dataframe = kobo.fetch_submitted_data(form_id="12345")

# Process and import into database
if success and dataframe is not None:
    # Data now available in dashboard
    pass
```

### Setting KoboToolbox Credentials

Set environment variables (or .env file):

```bash
KOBO_USERNAME=jesseanak
KOBO_PASSWORD=Jese@1998
```

## Access Control

### Authentication Flow

1. User enters email and password
2. System checks if email is registered
3. System validates password
4. **New**: System verifies user is either:
   - Admin account, OR
   - Lab account (email ends with @sentinel-amr.lab)
5. If not authorized, access is denied
6. Authenticated users can view lab-filtered data

### Lab Data Filtering

When a lab user logs in:

- They see only data from their laboratory
- "Lab Name" in samples matches their account
- Upload restrictions apply - can only add data for their lab
- Reports are pre-filtered to their lab

### Admin Access

Admin users have full access:

- View all lab data
- Create/manage lab accounts
- Manage datasets across all labs
- Generate system-wide reports
- Configure KoboToolbox

## Security Notes

1. **Passwords**: Change on first login
2. **Lab Separation**: Data is logically separated per lab
3. **Audit Logging**: All data access is logged
4. **Email Restrictions**: Accounts must use `@sentinel-amr.lab` domain
5. **Two-Factor Auth**: Can be enabled for admin accounts (future)

## Troubleshooting

### Issue: Lab user cannot access system

**Solution**: 
- Verify account is active: `SELECT * FROM users WHERE email='{email}'`
- Check email format ends with `@sentinel-amr.lab`
- Run setup_lab_accounts.py to reinitialize

### Issue: KoboToolbox sync not working

**Solution**:
- Verify KOBO_USERNAME and KOBO_PASSWORD are set
- Check internet connection
- Verify form ID in KoboToolbox settings
- Check KoboToolbox account has submissions

### Issue: Lab name dropdown not showing

**Solution**:
- Regenerate template: `python src/validate.py`
- Ensure lab_name column is in samples sheet
- Verify lab names match approved list exactly

## Admin Setup Instructions

### Step 1: Create Lab Accounts

```bash
python setup_lab_accounts.py
```

### Step 2: Distribute Credentials

Send each lab their credentials:
- Email address (username@sentinel-amr.lab)
- Temporary password
- Instructions to change password on first login

### Step 3: Create KoboToolbox Form

```python
from src.lab_management import KoboToolboxManager

kobo = KoboToolboxManager()
success, msg = kobo.authenticate()
success, msg, form_data = kobo.create_amr_form()
```

### Step 4: Share Form Link

1. Get form URL from KoboToolbox dashboard
2. Share link with all laboratories
3. Provide instructions for form submission

### Step 5: Enable Auto-Sync (Optional)

Configure scheduled syncing from KoboToolbox:

```python
# In a separate background job
from src.lab_management import KoboToolboxManager

kobo = KoboToolboxManager()
kobo.authenticate()
success, msg, data = kobo.fetch_submitted_data(form_id="12345")

# Process and import data
```

## Files Modified

- `src/db.py` - Added lab_name column to samples table
- `src/validate.py` - Added lab_name to required columns, updated template
- `src/lab_management.py` - **NEW** - Lab authentication and KoboToolbox integration
- `setup_lab_accounts.py` - **NEW** - Lab account initialization script
- `app.py` - Restricted sign-up to labs only, updated UI messages
- `requirements.txt` - Added requests library for KoboToolbox API

## Testing

Test the lab access system:

1. Run setup: `python setup_lab_accounts.py`
2. Try logging in with: `eastern_regional_hospital@sentinel-amr.lab`
3. Verify admin can see all labs
4. Verify lab users see only their data
5. Upload sample with lab_name field
6. Verify lab-specific data appears correctly

## Support

For issues or questions about:
- **Lab account access**: Contact AMR Program administrator
- **KoboToolbox setup**: See KoboToolbox documentation at https://kf.kobotoolbox.org
- **System issues**: Contact system administrator

---

**Version**: 2.0  
**Last Updated**: February 2, 2026  
**Status**: Production Ready
