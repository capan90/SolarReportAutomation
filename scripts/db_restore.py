import os
import sys
import subprocess
import re
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings, BASE_DIR

def run_restore():
    print("===== PostgreSQL Veritabanı Geri Yükleme (Restore) İşlemi =====")
    
    if len(sys.argv) < 2:
        print("Hata: Geri yüklenecek yedek dosyasının yolunu belirtmeniz gerekir.")
        print("Kullanım: python db_restore.py backups/backup_file.sql")
        sys.exit(1)
        
    backup_path = Path(sys.argv[1])
    if not backup_path.exists():
        # backups/ klasörü altında aramayı dene
        alternative_path = BASE_DIR / "backups" / backup_path.name
        if alternative_path.exists():
            backup_path = alternative_path
        else:
            print(f"Hata: Belirtilen yedek dosyası bulunamadı: {backup_path}")
            sys.exit(1)
        
    # Database URL parametrelerini ayrıştır
    db_url = settings.database_url
    if not db_url.startswith("postgresql"):
        print("Hata: DATABASE_URL geçerli bir PostgreSQL bağlantı adresi değil.")
        sys.exit(1)
        
    pattern = r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    match = re.match(pattern, db_url)
    if not match:
        print("Hata: DATABASE_URL ayrıştırılamadı. Formatı kontrol edin.")
        sys.exit(1)
        
    user, password, host, port, db_name = match.groups()
    
    print(f"  - Sunucu: {host}:{port}")
    print(f"  - Veritabanı: {db_name}")
    print(f"  - Geri Yüklenecek Dosya: {backup_path.name}")
    
    # Kullanıcı onayı iste
    print("DİKKAT: Veritabanındaki mevcut tüm veriler silinebilir veya üzerine yazılabilir.")
    confirm = input("Devam etmek istiyor musunuz? (evet/hayir): ")
    if confirm.lower().strip() != "evet":
        print("İşlem kullanıcı tarafından iptal edildi.")
        sys.exit(0)
        
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    
    # SQL formatındaki plain text yedeği psql ile geri yükle
    cmd = [
        "psql",
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", db_name,
        "-f", str(backup_path)
    ]
    
    try:
        subprocess.run(cmd, env=env, check=True)
        print("  - [SUCCESS] Veritabanı başarıyla geri yüklendi.")
    except Exception as e:
        print(f"  - [FAILED] Geri yükleme hatası: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_restore()
