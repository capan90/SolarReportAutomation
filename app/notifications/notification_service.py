from datetime import datetime
import socket
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.logger import setup_logger
from app.database.db_session import SessionLocal
from app.database.models import NotificationHistory
from app.notifications.notification_models import NotificationEvent
from app.notifications.policy_evaluator import NotificationPolicyEvaluator
from app.notifications.queue import InMemoryNotificationQueue, INotificationQueue
from app.notifications.email_sender import EmailSender

logger = setup_logger("NotificationService")

class NotificationService:
    """
    Neden: Bildirim gönderim sürecini yöneten, politika değerlendirici,
    kuyruk katmanı ve SMTP göndericiyi koordine eden üst düzey facade/service (SOLID - ISP).
    """
    def __init__(
        self,
        policy_evaluator: Optional[NotificationPolicyEvaluator] = None,
        queue: Optional[INotificationQueue] = None,
        email_sender: Optional[EmailSender] = None
    ):
        self.policy_evaluator = policy_evaluator or NotificationPolicyEvaluator()
        self.queue = queue or InMemoryNotificationQueue()
        self.email_sender = email_sender or EmailSender()

    def notify(self, event: NotificationEvent, force: bool = False, email_profile: str = "default") -> None:
        """
        Neden: ETL Pipeline veya CLI seviyesinden tetiklenen olay bildirim isteğini karşılamak.
        Politika uygunsa kuyruğa alır ve best-effort olarak gönderimi başlatır.
        force=True ise politika kontrolü atlanır (ör. başarı raporunun ekli gönderimi).
        """
        try:
            # 1. Politika Uygunluk Kontrolü (force ile atlanabilir)
            if not force and not self.policy_evaluator.should_notify(event.event_type):
                logger.info(f"Bildirim politikası gereği '{event.event_type}' olay tipi için mail gönderimi atlandı.")
                return
            if force:
                logger.info(f"Bildirim politikası atlandı (force=True): '{event.event_type}' gönderilecek.")

            logger.info(f"Bildirim politikası onaylandı. Olay kuyruğa ekleniyor: {event.event_type} (Run ID: {event.run_id})")
            
            # 2. Kuyruğa Ekle
            self.queue.push(event)
            
            # 3. Kuyruğu Tüket (In-Memory kuyruk olduğu için senkron olarak hemen tüketilir)
            self.process_queue(email_profile=email_profile)
            
        except Exception as e:
            # Bildirim altyapısının patlaması ana pipeline akışını asla bozmamalıdır (Best-Effort).
            logger.error(f"Bildirim servisi çalışırken hata oluştu (Best-Effort): {e}")

    def notify_pipeline(
        self,
        run_id: str,
        exit_code: int,
        duration_ms: int,
        stage_summary: str,
        validation_summary: Optional[str] = None,
        event_type: Optional[str] = None,
        attachment_path: Optional[str] = None,
        force: bool = False,
        email_profile: str = "default"
    ) -> None:
        """
        Neden: Pipeline sonuçlarına göre uygun olay tipini belirlemek, Git/Sunucu metriklerini toplamak
        ve asıl notify sürecini başlatmak.
        """
        if event_type is None:
            if exit_code == 0:
                event_type = "SUCCESS"
            elif exit_code == 2:
                event_type = "VALIDATION_FAILED"
            elif exit_code == 3:
                event_type = "LOCK_EXISTS"
            elif exit_code == 4:
                event_type = "CONFIG_ERROR"
            else:
                event_type = "FAILED"
                # Stage summary içeriğine göre özel hata tipi seçimi
                summary_lower = stage_summary.lower()
                if "login" in summary_lower or "oturum" in summary_lower:
                    event_type = "LOGIN_FAILED"
                elif "download" in summary_lower or "indir" in summary_lower:
                    event_type = "DOWNLOAD_FAILED"
                elif "database" in summary_lower or "veritabanı" in summary_lower:
                    event_type = "DATABASE_FAILED"

        # Git commit hash
        git_commit = "unknown"
        try:
            import subprocess
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], 
                stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            pass

        # Sunucu makine adı
        machine_name = socket.gethostname()

        # Olay nesnesi
        event = NotificationEvent(
            run_id=run_id,
            event_type=event_type,
            exit_code=exit_code,
            duration_ms=duration_ms,
            machine_name=machine_name,
            git_commit=git_commit,
            stage_summary=stage_summary,
            validation_summary=validation_summary,
            attachment_path=attachment_path
        )
        self.notify(event, force=force, email_profile=email_profile)

    def process_queue(self, email_profile: str = "default") -> None:
        """
        Neden: Kuyruktaki bekleyen bildirimleri sırayla çıkarıp göndermek ve veritabanına loglamak.
        """
        while not self.queue.is_empty():
            event = self.queue.pop()
            if not event:
                break

            logger.info(f"Kuyruktan bildirim alınıyor ve gönderiliyor: {event.event_type}")
            
            # E-Posta gönder
            success, attempt_count, error_msg = self.email_sender.send(event, email_profile=email_profile)
            
            # Sonucu veritabanına logla
            self._save_audit(event, success, attempt_count, error_msg, email_profile=email_profile)

    def _save_audit(self, event: NotificationEvent, success: bool, attempt_count: int, error_msg: Optional[str], email_profile: str = "default") -> None:
        """
        Neden: Gönderilen bildirimlerin denetim izini (audit trail) veritabanında saklamak.
        """
        db = None
        recipient = settings.alert_email
        if email_profile == "daily":
            recipient = settings.smtp_to_daily
        elif email_profile == "monthly":
            recipient = settings.smtp_to_monthly
        elif email_profile == "plant_alert":
            recipient = settings.smtp_to_plant_alert
        elif email_profile == "system":
            recipient = settings.smtp_to_system

        try:
            db = SessionLocal()
            history = NotificationHistory(
                run_id=event.run_id,
                channel="email",
                recipient=recipient or "unknown",
                status="SENT" if success else "FAILED",
                attempt_count=attempt_count,
                error_message=error_msg if error_msg else None,
                sent_at=datetime.utcnow()
            )
            db.add(history)
            db.commit()
            logger.info("Bildirim geçmişi (notification_history) veritabanına başarıyla kaydedildi.")
        except Exception as e:
            logger.error(f"Bildirim denetim kaydı veritabanına yazılamadı (Best-effort): {e}")
        finally:
            if db:
                db.close()
