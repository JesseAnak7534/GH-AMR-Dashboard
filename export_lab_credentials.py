"""
Export lab credentials to CSV file for distribution.
Run this after setup_lab_accounts.py to generate a CSV with all lab credentials.
"""

import csv
import secrets
from src.lab_management import get_lab_names
from datetime import datetime

def export_lab_credentials_to_csv():
    """Export lab credentials to CSV file."""
    
    lab_names = get_lab_names()
    
    # Generate credentials
    credentials = []
    for idx, lab_name in enumerate(lab_names, 1):
        username = f"LAB{idx:02d}"
        email = f"{username.lower()}@sentinel-amr.lab"
        password = f"{secrets.token_urlsafe(3)[:4].upper()}{secrets.randbelow(100):02d}"
        
        credentials.append({
            'Lab #': idx,
            'Lab Name': lab_name,
            'Email': email,
            'Password': password
        })
    
    # Create CSV file
    csv_filename = f"lab_credentials_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Lab #', 'Lab Name', 'Email', 'Password']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(credentials)
        
        print("=" * 70)
        print("LAB CREDENTIALS EXPORTED TO CSV")
        print("=" * 70)
        print(f"\nFile created: {csv_filename}")
        print(f"Location: {csv_filename}")
        print(f"Total labs: {len(credentials)}")
        print("\nCredentials format:")
        print("  Lab #: 1-19")
        print("  Lab Name: Full laboratory name")
        print("  Email: lab##@sentinel-amr.lab")
        print("  Password: 6-character password")
        print("\nIMPORTANT: Keep this file secure!")
        print("Distribute to labs with instructions to change password on first login.")
        print("=" * 70)
        
        # Also print to console for reference
        print("\nCredential Summary:")
        print("-" * 70)
        for cred in credentials:
            print(f"Lab {cred['Lab #']:02d}: {cred['Lab Name']}")
            print(f"  Email: {cred['Email']}")
            print(f"  Password: {cred['Password']}")
        print("-" * 70)
        
        return True, csv_filename
    
    except Exception as e:
        print(f"Error exporting credentials: {str(e)}")
        return False, None

if __name__ == "__main__":
    success, filename = export_lab_credentials_to_csv()
    if success:
        print(f"\n✓ Successfully exported to {filename}")
    else:
        print(f"\n✗ Failed to export credentials")
