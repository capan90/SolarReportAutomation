import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.notifications import NotificationService, NotificationEvent
from app.database import create_tables, SessionLocal, NotificationHistory

def test_runs():
    print("Notification System Integration Test başlatılıyor...")
    
    # 1. DB tablolarının (özellikle notification_history) oluşturulduğundan emin ol
    create_tables()
    
    # 2. Örnek bir validation_failed olay bildirimi simüle edelim
    # Politika: VALIDATION_FAILED -> true (mail gönder)
    service = NotificationService()
    
    event = NotificationEvent(
        run_id="test-run-uuid-1234",
        event_type="VALIDATION_FAILED",
        exit_code=2,
        duration_ms=1520,
        machine_name="TEST_MACHINE",
        git_commit="a1b2c3d",
        stage_summary="Validation aşamasında 3 adet kritik şema hatası bulundu.",
        validation_summary="Sütun eksik: 'Yield Today (kWh)'. Beklenen: float. Alınan: None."
    )
    
    print("\n[TEST] VALIDATION_FAILED olayı tetikleniyor...")
    service.notify(event)
    
    # 3. Veritabanını sorgulayarak audit kaydının atıldığını kontrol edelim
    db = SessionLocal()
    try:
        records = db.query(NotificationHistory).filter(NotificationHistory.run_id == "test-run-uuid-1234").all()
        print(f"\n[TEST RESULTS] Bulunan log kaydı sayısı: {len(records)}")
        for rec in records:
            print(f"  - ID: {rec.id}")
            print(f"  - Run ID: {rec.run_id}")
            print(f"  - Channel: {rec.channel}")
            print(f"  - Status: {rec.status}")
            print(f"  - Attempt: {rec.attempt_count}")
            print(f"  - Sent At: {rec.sent_at}")
            print(f"  - Error Msg: {rec.error_message}")
    finally:
        db.close()

if __name__ == "__main__":
    test_runs()
