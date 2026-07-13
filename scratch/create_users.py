import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import create_tables
from app.dashboard.auth import DashboardAuth

def main():
    print("Veritabanı tabloları oluşturuluyor (eğer yoksa)...")
    create_tables()

    auth = DashboardAuth()
    
    users_to_create = [
        {"username": "admin", "password": "Admin2026!", "display_name": "Sistem Yöneticisi"},
        {"username": "viewer1", "password": "Viewer2026!", "display_name": "Kullanıcı 1"}
    ]
    
    print("\nKullanıcılar oluşturuluyor...")
    for u in users_to_create:
        success = auth.create_user(
            username=u["username"],
            password=u["password"],
            display_name=u["display_name"]
        )
        if success:
            print(f"SUCCESS: {u['username']} ({u['display_name']})")
        else:
            print(f"ALREADY EXISTS/FAILED: {u['username']}")

if __name__ == "__main__":
    main()
