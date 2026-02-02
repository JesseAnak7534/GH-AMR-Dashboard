"""
Setup script to create lab user accounts in the database.
Run this once to initialize all lab user accounts.

Each lab gets a unique username and password.
Only labs and the admin can access the system.
"""

import bcrypt
from src import db
from src.lab_management import get_lab_credentials, get_lab_names

# Pre-defined passwords for each lab (should be changed on first login)
LAB_CREDENTIALS = {
    "Eastern Regional Hospital": "ERH@Sentinel2024",
    "St. Martin De Porres Hospital Eikwe": "SMDP@Sentinel2024",
    "Sekondi Public Health Reference Laboratory": "SPRL@Sentinel2024",
    "Ho Teaching Hospital": "HTH@Sentinel2024",
    "Tamale Teaching Hospital": "TTH@Sentinel2024",
    "Komfo Anokye Teaching Hospital": "KATH@Sentinel2024",
    "Korle-Bu Teaching Hospital": "KBTH@Sentinel2024",
    "Lekma Hospital": "LEKMA@Sentinel2024",
    "Sunyani Teaching Hospital": "STH@Sentinel2024",
    "Cape Coast Teaching Hospital": "CCTH@Sentinel2024",
    "National Food Safety Laboratory": "NFSL@Sentinel2024",
    "CSIR – Water Research Institute (Microbiology Laboratory)": "CWRI@Sentinel2024",
    "Accra Veterinary Laboratory": "AVL@Sentinel2024",
    "Kumasi Veterinary Laboratory": "KVL@Sentinel2024",
    "Quadushah Medical Diagnostic Limited": "QMDL@Sentinel2024",
    "Central Veterinary Laboratory": "CVL@Sentinel2024",
    "Pong Tamale School": "PTS@Sentinel2024",
    "Metropolis Health Care Limited": "MHCL@Sentinel2024",
    "Alma Medical Laboratory Ltd": "AML@Sentinel2024"
}

def setup_lab_accounts():
    """Create lab user accounts in the database."""
    
    db.init_database()
    
    lab_credentials = get_lab_credentials()
    lab_names = get_lab_names()
    
    print("=" * 70)
    print("LAB USER ACCOUNT SETUP")
    print("=" * 70)
    print()
    
    created_count = 0
    failed_count = 0
    
    for lab_name in lab_names:
        if lab_name not in LAB_CREDENTIALS:
            print(f"WARNING: No password defined for {lab_name}")
            continue
        
        # Create email based on lab name
        username = lab_credentials.get(lab_name, lab_name.lower().replace(" ", "_"))
        password = LAB_CREDENTIALS[lab_name]
        
        # Create email format: lab_username@sentinel-amr.lab
        email = f"{username}@sentinel-amr.lab"
        
        try:
            # Check if user already exists
            existing_user = db.get_user_by_email(email)
            
            if existing_user:
                print(f"✓ User already exists: {email} ({lab_name})")
                created_count += 1
            else:
                # Hash password
                password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                
                # Create user
                success, msg = db.create_user(email, password_hash, is_admin=False)
                
                if success:
                    # Mark as verified
                    db.set_user_verified(email, True)
                    db.update_user_status(db.get_user_by_email(email)['user_id'], True)
                    
                    print(f"✓ Created: {email} ({lab_name})")
                    print(f"  Username: {username}")
                    print(f"  Password: {password}")
                    print()
                    
                    created_count += 1
                else:
                    print(f"✗ Failed to create {email}: {msg}")
                    failed_count += 1
        
        except Exception as e:
            print(f"✗ Error creating {lab_name}: {str(e)}")
            failed_count += 1
    
    print()
    print("=" * 70)
    print(f"SETUP COMPLETE: {created_count} lab accounts ready")
    print(f"FAILED: {failed_count} accounts")
    print("=" * 70)
    print()
    print("Lab users can now login with:")
    print("  Email: {username}@sentinel-amr.lab")
    print("  Password: (provided above)")
    print()
    print("For security, request each lab to change their password on first login.")
    print()

if __name__ == "__main__":
    setup_lab_accounts()
