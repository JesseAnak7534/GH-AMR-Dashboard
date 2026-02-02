"""
Setup script to create lab user accounts in the database.
Run this once to initialize all lab user accounts.

Each lab gets a unique username and password.
Only labs and the admin can access the system.
"""

import bcrypt
import secrets
from src import db
from src.lab_management import get_lab_credentials, get_lab_names

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
    
    for idx, lab_name in enumerate(lab_names, 1):
        # Create short username: LAB01, LAB02, etc.
        username = f"LAB{idx:02d}"
        # Create short password: 6 characters (uppercase + number)
        password = f"{secrets.token_urlsafe(3)[:4].upper()}{secrets.randbelow(100):02d}"
        
        # Create email format: lab_username@sentinel-amr.lab
        email = f"{username.lower()}@sentinel-amr.lab"
        
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
                    
                    print(f"✓ Lab {idx}: {lab_name}")
                    print(f"  Email: {email}")
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
    print("  Email: lab##@sentinel-amr.lab")
    print("  Password: (provided above)")
    print()
    print("For security, request each lab to change their password on first login.")
    print()

if __name__ == "__main__":
    setup_lab_accounts()
