import os
import sys
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings, BASE_DIR
from app.database import test_connection
from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.sources.registry import SourceRegistry

def run_verification():
    print("====================================================")
    print("   SolarReportAutomation Kurulum Dogrulama Testi    ")
    print("====================================================")
    
    success = True
    
    # 1. Klasör Kontrolleri
    print("\n[1] Dizin Varligi ve Yazma Izinleri Kontrolu...")
    required_dirs = {
        "Base Directory": BASE_DIR,
        "Logs Directory": settings.log_directory,
        "Raw Exports Directory": settings.download_directory,
        "Backups Directory": BASE_DIR / "backups"
    }
    
    for name, path in required_dirs.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            # Yazma testi yap
            test_file = path / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            print(f"  [OK] {name}: ({path})")
        except Exception as e:
            print(f"  [FAIL] {name}: ({path}) - Hata: {e}")
            success = False
            
    # 2. Yapılandırma Kontrolü
    print("\n[2] Yapilandirma ve .env Kontrolu...")
    try:
        settings.validate()
        print(f"  [OK] .env Ayarlari: (Ortam: {settings.app_env})")
        print(f"  [OK] Dashboard Erisim Modu: {settings.dashboard_access_mode} (Port: {settings.dashboard_port})")
    except Exception as e:
        print(f"  [FAIL] Yapilandirma Hatasi: {e}")
        success = False
        
    # 3. PostgreSQL Bağlantı Kontrolü
    print("\n[3] Veritabanı Baglanti Kontrolu...")
    try:
        if test_connection():
            print("  [OK] Veritabanı Baglantisi")
        else:
            print("  [FAIL] Veritabanı Baglantisi (Baglanti kurulamadi)")
            success = False
    except Exception as e:
        print(f"  [FAIL] Veritabanı Baglanti Hatasi: {e}")
        success = False
        
    # 4. Tarayıcı (Playwright) Kontrolü
    print("\n[4] Chromium Web Browser (Playwright) Kontrolu...")
    try:
        with PlaywrightClient(headless=True) as client:
            page = client.create_page()
            page.goto("about:blank")
            print("  [OK] Playwright Browser Motoru")
    except Exception as e:
        print(f"  [FAIL] Playwright Motor Hatasi: {e}")
        print("    Ipucu: '.venv\\Scripts\\playwright install chromium' komutunu calistirmanız gerekebilir.")
        success = False
        
    # 5. Multi-Source Registry Kontrolü
    print("\n[5] Multi-Source ve Kayıtli Portallar Kontrolu...")
    try:
        registry = SourceRegistry()
        sources = registry.list_sources()
        print(f"  [OK] Kayitli Veri Kaynaklari: {sources}")
        for s in sources:
            is_active = registry.validate_source(s)
            print(f"    - {s}: {'AKTIF' if is_active else 'PASIF'}")
    except Exception as e:
        print(f"  [FAIL] Registry Yukleme Hatasi: {e}")
        success = False
        
    # 6. Disk Alanı Kontrolü
    print("\n[6] Disk Alani Kontrolu...")
    try:
        total, used, free = shutil.disk_usage(BASE_DIR)
        free_gb = free / (1024**3)
        print(f"  [OK] Bos Disk Alani: {free_gb:.2f} GB")
    except Exception as e:
        print(f"  [FAIL] Disk Alani Okunamadi: {e}")

    # Raporlama
    print("\n====================================================")
    if success:
        print("   SONUC: KURULUM BASARIYLA DOGRULANDI (READY)")
        print("====================================================")
        sys.exit(0)
    else:
        print("   SONUC: KURULUMDA EKSİKLİKLER BULUNDU (FAILED)")
        print("====================================================")
        sys.exit(1)

if __name__ == "__main__":
    run_verification()
