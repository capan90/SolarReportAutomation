import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.utils import with_retry
from app.scheduler import get_scheduler
from app.database import create_tables, SessionLocal, RetryHistory

# Örnek hata sınıfları
class TransientTestError(Exception):
    pass

class PermanentTestError(Exception):
    pass

# Retry sayacı
attempt_counter = 0

class TargetOperation:
    def __init__(self, run_id: str):
        self.run_id = run_id

    @with_retry(
        max_retries=3,
        backoff_factor=0.1,  # Hızlı test için bekleme süresini küçük tut
        retryable_exceptions=(TransientTestError,),
        non_retryable_exceptions=(PermanentTestError,)
    )
    def run_unstable_operation(self):
        global attempt_counter
        attempt_counter += 1
        if attempt_counter < 3:
            raise TransientTestError("Geçici hata simüle edildi.")
        return "SUCCESS"

def test_production_readiness():
    print("===== Production Readiness Testleri Başlatılıyor =====")
    
    # 1. Config Profiles Testi
    print(f"\n[TEST 1] Config Profile: APP_ENV = {settings.app_env}")
    print(f"  - Log Level: {settings.log_level}")
    print(f"  - Timeout Multiplier: {settings.timeout_multiplier}")
    print(f"  - Dry Run: {settings.dry_run}")
    print(f"  - Strict Validation: {settings.strict_validation}")
    
    # 2. Retry Policy ve Audit Trail Testi
    print("\n[TEST 2] Retry Policy ve Database Log Testi...")
    create_tables()
    
    operation = TargetOperation(run_id="test-retry-uuid-999")
    result = operation.run_unstable_operation()
    
    print(f"  - Operasyon Sonucu: {result} (Toplam Deneme: {attempt_counter})")
    
    # Veritabanını sorgula
    db = SessionLocal()
    try:
        retries = db.query(RetryHistory).filter(RetryHistory.run_id == "test-retry-uuid-999").all()
        print(f"  - Veritabanındaki Retry Log Sayısı: {len(retries)}")
        for log in retries:
            print(f"    * Operasyon: {log.operation} | Deneme: {log.attempt} | Gecikme: {log.delay_seconds}s | Hata: {log.error_message}")
            
        assert len(retries) == 2, "2 adet retry kaydı veritabanında olmalıydı."
        print("  - [SUCCESS] Retry Audit veritabanı kaydı doğrulandı.")
    finally:
        db.close()
        
    # 3. Scheduler Factory Testi
    print("\n[TEST 3] Scheduler Factory Testi...")
    scheduler = get_scheduler()
    print(f"  - Tespit edilen işletim sistemi scheduler'ı: {scheduler.__class__.__name__}")
    
    print("\n===== Tüm Testler Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    test_production_readiness()
