import os
import sys
import shutil
import socket
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings, BASE_DIR
from app.database import test_connection
from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.sources.registry import SourceRegistry

def run_verification():
    print("====================================================")
    print("   SolarReportAutomation Production Health Report   ")
    print("====================================================")
    
    score = 100
    checks = {}
    
    # 1. Klasör Kontrolleri (Dizin varlığı ve yazma izinleri) - Ağırlık: 15 Puan
    required_dirs = {
        "Base Directory": BASE_DIR,
        "Logs Directory": settings.log_directory,
        "Raw Exports Directory": settings.download_directory,
        "Backups Directory": BASE_DIR / "backups"
    }
    
    dir_errors = 0
    for name, path in required_dirs.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
        except Exception:
            dir_errors += 1
            
    if dir_errors == 0:
        checks["Dizin Yazma Izinleri"] = ("PASS", "Tüm dizinler yazılabilir.")
    else:
        checks["Dizin Yazma Izinleri"] = ("FAIL", f"{dir_errors} adet dizinde yazma hatası oluştu.")
        score -= 15
        
    # 2. Yapılandırma Kontrolü - Ağırlık: 10 Puan
    try:
        settings.validate()
        checks["Configuration (.env)"] = ("PASS", f"Yapılandırma doğrulandı (Profil: {settings.app_env})")
    except Exception as e:
        checks["Configuration (.env)"] = ("FAIL", f"Eksik parametreler: {e}")
        score -= 10
        
    # 3. PostgreSQL Bağlantı Kontrolü - Ağırlık: 30 Puan
    try:
        if test_connection():
            checks["PostgreSQL Database"] = ("PASS", "Veritabanı bağlantısı başarılı.")
        else:
            checks["PostgreSQL Database"] = ("FAIL", "PostgreSQL bağlantısı kurulamadı.")
            score -= 30
    except Exception as e:
        checks["PostgreSQL Database"] = ("FAIL", f"Veritabanı hatası: {e}")
        score -= 30
        
    # 4. Tarayıcı (Playwright) Kontrolü - Ağırlık: 15 Puan
    try:
        with PlaywrightClient(headless=True) as client:
            page = client.create_page()
            page.goto("about:blank")
            checks["Playwright Browser"] = ("PASS", "Chromium tarayıcı motoru hazır.")
    except Exception as e:
        checks["Playwright Browser"] = ("FAIL", f"Tarayıcı motoru başlatılamadı: {e}")
        score -= 15
        
    # 5. SMTP Mail Bağlantısı - Ağırlık: 10 Puan (Opsiyonel olduğu için WARNING verip skoru 10 kırar)
    smtp_configured = bool(settings.smtp_host and settings.smtp_username)
    if smtp_configured:
        checks["SMTP Notifications"] = ("PASS", f"SMTP sunucusu yapılandırılmış: {settings.smtp_host}")
    else:
        checks["SMTP Notifications"] = ("WARNING", "SMTP mail sunucusu tanımlanmamış. Alarmlar iletilemeyecektir.")
        score -= 10
        
    # 6. Multi-Source Registry Kontrolü - Ağırlık: 10 Puan
    try:
        registry = SourceRegistry()
        sources = registry.list_sources()
        checks["Multi-Source Registry"] = ("PASS", f"Kayıtlı veri kaynakları: {sources}")
    except Exception as e:
        checks["Multi-Source Registry"] = ("FAIL", f"Registry yüklenirken hata: {e}")
        score -= 10
        
    # 7. Disk Alanı Kontrolü - Ağırlık: 10 Puan
    try:
        total, used, free = shutil.disk_usage(BASE_DIR)
        free_gb = free / (1024**3)
        if free_gb > 2.0:  # > 2GB
            checks["Disk Space"] = ("PASS", f"Boş disk alanı: {free_gb:.2f} GB")
        else:
            checks["Disk Space"] = ("WARNING", f"Düşük disk alanı uyarısı: {free_gb:.2f} GB boş.")
            score -= 5
    except Exception as e:
        checks["Disk Space"] = ("FAIL", f"Disk alanı sorgulanamadı: {e}")
        score -= 10

    # Rapor Sonuçlarını Yazdır
    print("\n----------------------------------------------------")
    for check_name, (status, detail) in checks.items():
        print(f"  [{status}] {check_name}: {detail}")
    print("----------------------------------------------------")
    
    # Genel Durum Değerlendirmesi
    overall_status = "PASS"
    if score < 70 or any(stat == "FAIL" for stat, _ in checks.values()):
        overall_status = "FAIL"
    elif score < 95:
        overall_status = "WARNING"
        
    print(f"\nGENEL DURUM            : {overall_status}")
    print(f"PRODUCTION READINESS   : {score} / 100")
    print("====================================================")
    
    # 0 = PASS, 1 = WARNING, 2 = FAIL (Zamanlayıcı çıkış uyumluluğu için)
    if overall_status == "FAIL":
        sys.exit(2)
    elif overall_status == "WARNING":
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    run_verification()
