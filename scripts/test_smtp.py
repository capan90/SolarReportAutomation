import sys
import socket
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.notifications.email_sender import EmailSender
from app.notifications.notification_models import NotificationEvent
from app.database.db_session import SessionLocal
from app.database.models import NotificationHistory

def test_smtp_connection():
    print("====================================================")
    print("      SolarReportAutomation SMTP E-Posta Testi      ")
    print("====================================================")

    # 1. Ortam ve Yapılandırma Doğrulama
    if not settings.smtp_enabled:
        print("HATA: SMTP_ENABLED=false olarak ayarlanmış.")
        print("Lütfen .env dosyasından SMTP_ENABLED=true yapıp tekrar deneyin.")
        sys.exit(1)

    print(f"SMTP Host       : {settings.smtp_host}")
    print(f"SMTP Port       : {settings.smtp_port}")
    print(f"SMTP Username   : {settings.smtp_username}")
    print(f"SMTP From       : {settings.smtp_from}")
    print(f"SMTP Recipient  : {settings.alert_email}")
    print("SMTP Password   : ********")
    print("----------------------------------------------------")
    print("Test e-postası gönderiliyor...")

    # 2. Test Notification Event Oluşturma
    run_id = "test-run-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
    event = NotificationEvent(
        run_id=run_id,
        event_type="SUCCESS",
        exit_code=0,
        duration_ms=4500,
        machine_name=socket.gethostname(),
        git_commit="test-commit",
        stage_summary="Bu bir SolarReportAutomation SMTP entegrasyonu test e-postasıdır. Lütfen dikkate almayınız.",
        validation_summary="Sistem testi: BAŞARILI"
    )

    sender = EmailSender()
    
    # 3. Maili Gönder
    success, attempt_count, error_msg = sender.send(event)

    # 4. Veritabanına Log Kaydı Yaz
    db = None
    try:
        db = SessionLocal()
        history = NotificationHistory(
            run_id=run_id,
            channel="email_test",
            recipient=settings.alert_email or "unknown",
            status="SENT" if success else "FAILED",
            attempt_count=attempt_count,
            error_message=error_msg if error_msg else None,
            sent_at=datetime.utcnow()
        )
        db.add(history)
        db.commit()
    except Exception as e:
        print(f"UYARI: Test logu veritabanına yazılamadı: {e}")
    finally:
        if db:
            db.close()

    # 5. Console Sonucu Raporla
    if success:
        print("\nSMTP test mail sent successfully.")
        print("E-posta başarıyla iletildi.")
        sys.exit(0)
    else:
        # Şifre maskeleme güvencesi
        safe_error = error_msg if error_msg else "Bilinmeyen SMTP hatası"
        if settings.smtp_password and settings.smtp_password in safe_error:
            safe_error = safe_error.replace(settings.smtp_password, "********")
        print(f"\nSMTP test failed: {safe_error}")
        sys.exit(1)

if __name__ == "__main__":
    test_smtp_connection()
