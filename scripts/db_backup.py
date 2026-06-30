import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings, BASE_DIR

def run_backup():
    print("===== PostgreSQL Veritabanı Yedekleme İşlemi Başlatıldı =====")
    
    # 1. Klasörleri hazırla
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Database URL parametrelerini ayrıştır
    db_url = settings.database_url
    if not db_url.startswith("postgresql"):
        print("Hata: DATABASE_URL geçerli bir PostgreSQL bağlantı adresi değil.")
        sys.exit(1)
        
    # postgresql://username:password@host:port/dbname
    pattern = r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    match = re.match(pattern, db_url)
    if not match:
        print("Hata: DATABASE_URL ayrıştırılamadı. Formatı kontrol edin.")
        sys.exit(1)
        
    user, password, host, port, db_name = match.groups()
    
    # 3. Dosya ismini oluştur
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"backup_{db_name}_{timestamp}.sql"
    
    print(f"  - Sunucu: {host}:{port}")
    print(f"  - Veritabanı: {db_name}")
    print(f"  - Çıktı Dosyası: backups/{backup_file.name}")
    
    # 4. pg_dump çalıştır (PGPASSWORD env ile güvenli kimlik doğrulama)
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    
    cmd = [
        "pg_dump",
        "-h", host,
        "-p", port,
        "-U", user,
        "-F", "p",  # plain text SQL format
        "-f", str(backup_file),
        db_name
    ]
    
    try:
        # pg_dump'ın sistem yolunda kurulu olması gerekir
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
        print("  - [SUCCESS] Veritabanı başarıyla yedeklendi.")
    except Exception as e:
        error_msg = f"Yedekleme Hatası: {e}"
        if hasattr(e, "stderr") and e.stderr:
            error_msg += f"\nDetay: {e.stderr}"
        print(f"  - [FAILED] {error_msg}")
        
        # Hata kaydını logla
        log_dir = settings.log_directory
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "backup_error.log", "a", encoding="utf-8") as lf:
            lf.write(f"[{datetime.now().isoformat()}] {error_msg}\n")
        sys.exit(1)
        
    # 5. Retention Policy (14 Günlük döngü temizliği)
    print("\n[RETENTION] 14 günden eski yedek dosyaları temizleniyor...")
    now = datetime.now()
    retention_days = 14
    
    deleted_count = 0
    for f in backup_dir.glob("backup_*.sql"):
        # Dosya adından tarih bilgisini çöz (backup_dbname_YYYYMMDD_HHMMSS.sql)
        name = f.stem
        parts = name.split("_")
        if len(parts) >= 3:
            date_str = parts[-2]
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                age_days = (now - file_date).days
                if age_days > retention_days:
                    f.unlink()
                    print(f"  - Silindi: {f.name} (Yaş: {age_days} gün)")
                    deleted_count += 1
            except ValueError:
                pass
    print(f"  - Temizlik tamamlandı. Toplam {deleted_count} eski yedek silindi.")

if __name__ == "__main__":
    run_backup()
