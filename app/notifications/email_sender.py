import datetime
import os
import re
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from string import Template

from app.core.config import settings, BASE_DIR
from app.core.logger import setup_logger
from app.notifications.notification_models import NotificationEvent

logger = setup_logger("EmailSender")

class EmailSender:
    """
    Neden: SMTP protokolünü kullanarak HTML e-postaları göndermek,
    şablonları render etmek ve başarısız gönderimlerde retry mekanizmasını yönetmek.
    """
    def __init__(self):
        self.templates_dir = BASE_DIR / "templates"
        self.retry_delays = [1.0, 3.0, 5.0]  # Denemeler arası bekleme süreleri

    def _get_template_content(self, event_type: str) -> str:
        """
        Neden: Olay tipine göre uygun HTML şablon dosyasını okumak.
        Bulunamazsa güvenli bir yedek (fallback) şablon dönmek.
        """
        template_name = "failed.html"
        if event_type.upper() == "SUCCESS":
            template_name = "success.html"
        elif event_type.upper() == "VALIDATION_FAILED":
            template_name = "validation_failed.html"
        elif event_type.upper() == "CAPTCHA_REQUIRED":
            template_name = "captcha_required.html"
            
        template_file = self.templates_dir / template_name
        
        if template_file.exists():
            try:
                return template_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Şablon dosyası okunamadı ({template_name}): {e}")
                
        # Fallback düz metin/HTML şablonu
        return """
        <html>
        <body>
            <h2>Solar ETL Alert: $STATUS</h2>
            <p>Run ID: $RUN_ID</p>
            <p>Süre: $DURATION_MS ms</p>
            <p>Detay: $STAGE_SUMMARY</p>
        </body>
        </html>
        """

    def _extract_report_date(self, event: NotificationEvent) -> str:
        """
        Neden: Yönetici dostu konu/gövde için rapor tarihini (DD.MM.YYYY) üretmek.
        Olay nesnesi tarih alanı taşımadığından, ek dosya adındaki YYYYMMDD deseni
        (ör. mahsup_20260706.xlsx) kaynak alınır; bulunamazsa bugünün tarihi kullanılır.
        """
        if event.attachment_path:
            m = re.search(r"(\d{4})(\d{2})(\d{2})", Path(event.attachment_path).name)
            if m:
                return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
        return datetime.date.today().strftime("%d.%m.%Y")

    def _friendly_error_summary(self, event: NotificationEvent) -> str:
        """
        Neden: Hata e-postası yöneticiye gider; ham exception metni yerine
        anlaşılır bir özet gösterilir. Kaynak, stage_summary içindeki hata
        ifadelerinden/istisna adlarından tespit edilir.
        """
        text = event.stage_summary or ""
        reasons = []
        if "SourceAuthenticationError" in text or "GAOSB raporu indirme aşaması başarısız" in text:
            reasons.append("GAOSB bağlantı hatası")
        if "IsolarError" in text or "iSolar Curve indirme aşaması başarısız" in text:
            reasons.append("iSolar bağlantı hatası")
        if not reasons:
            reasons.append("Veri işleme hatası")
        return ", ".join(reasons)

    def render_body(self, event: NotificationEvent) -> str:
        """
        Neden: HTML şablonundaki değişkenleri ($RUN_ID vb.) olay verileriyle güvenli
        şekilde değiştirmek (string.Template kullanarak sıfır bağımlılıklı şablonlama).
        """
        raw_template = self._get_template_content(event.event_type)

        # None olan alanları boş dizeye dönüştür
        stage_summary = event.stage_summary if event.stage_summary else ""
        validation_summary = event.validation_summary if event.validation_summary else ""

        # Neden: Çok satırlı özetlerin HTML gövdede satır satır görünmesi için.
        stage_summary = stage_summary.replace("\n", "<br>")

        # Neden: Ek varsa kullanıcıya "rapor ekte" notunu göster; yoksa boş bırak.
        # Dosya adı/yolu gibi teknik detaylar yönetici e-postasında gösterilmez.
        attachment_note = ""
        if event.attachment_path:
            attachment_note = (
                '<p style="background-color: #e8f5e9; padding: 10px; border-radius: 4px;">'
                "&#128206; Günlük mahsuplaşma raporu ekte sunulmaktadır.</p>"
            )

        template_data = {
            "RUN_ID": event.run_id,
            "STATUS": event.event_type,
            "DURATION_MS": str(event.duration_ms),
            "EXIT_CODE": str(event.exit_code),
            "MACHINE_NAME": event.machine_name,
            "GIT_COMMIT": event.git_commit,
            "STAGE_SUMMARY": stage_summary,
            "VALIDATION_SUMMARY": validation_summary,
            "ATTACHMENT_NOTE": attachment_note,
            "REPORT_DATE": self._extract_report_date(event),
            "ERROR_SUMMARY": self._friendly_error_summary(event),
            "DASHBOARD_URL": os.environ.get("DASHBOARD_URL", "http://localhost:8081")
        }
        
        # string.Template kullanarak placeholderları değiştir (safe_substitute hata vermesini önler)
        return Template(raw_template).safe_substitute(template_data)

    def send(self, event: NotificationEvent) -> tuple[bool, int, str]:
        """
        Neden: E-posta gönderimini SMTP üzerinden gerçekleştirmek. 
        Başarısızlık durumunda belirlenen saniyelerle 3 kez tekrar dener.
        Geriye: (Başarı Durumu, Deneme Sayısı, Varsa Hata Mesajı)
        """
        if not settings.smtp_enabled:
            logger.info("SMTP_ENABLED=false. Mail gönderimi devre dışı bırakılmıştır.")
            return False, 0, "SMTP_ENABLED=false"

        if not settings.smtp_host or not settings.alert_email:
            logger.warning("SMTP ayarları veya ALERT_EMAIL eksik. Mail gönderimi atlanıyor.")
            return False, 0, "SMTP_HOST veya ALERT_EMAIL eksik."

        body = self.render_body(event)
        
        # Mail nesnesi oluştur
        msg = MIMEMultipart()
        msg["From"] = settings.smtp_from if settings.smtp_from else settings.smtp_username
        msg["To"] = settings.alert_email
        # Neden: E-postalar yöneticiye gider; konu satırında teknik detay (Run ID vb.) olmaz.
        if event.event_type.upper() == "SUCCESS":
            msg["Subject"] = f"GES Mahsuplaşma Raporu - {self._extract_report_date(event)}"
        elif event.event_type.upper() == "FAILED":
            msg["Subject"] = f"GES Mahsuplaşma Raporu — Hata - {self._extract_report_date(event)}"
        elif event.event_type.upper() == "CAPTCHA_REQUIRED":
            msg["Subject"] = "GES Sistemi — GAOSB Doğrulaması Gerekiyor"
        else:
            msg["Subject"] = f"Solar ETL Alert - {event.event_type} (Run ID: {event.run_id[:8]})"
        msg.attach(MIMEText(body, "html", "utf-8"))

        # Neden: Olayda ek dosya (ör. mahsup Excel raporu) tanımlıysa e-postaya iliştir.
        if event.attachment_path:
            att_path = Path(event.attachment_path)
            if att_path.exists():
                try:
                    part = MIMEApplication(
                        att_path.read_bytes(),
                        _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    part.add_header("Content-Disposition", "attachment", filename=att_path.name)
                    msg.attach(part)
                    logger.info(f"E-posta eki iliştirildi: {att_path.name} ({att_path.stat().st_size} bayt)")
                except Exception as e:
                    # Ek iliştirilemese bile gövde gönderilmeye devam eder (best-effort).
                    logger.error(f"E-posta eki iliştirilemedi ({att_path}): {e}")
            else:
                logger.warning(f"E-posta eki bulunamadı, eksiz gönderilecek: {att_path}")

        max_attempts = len(self.retry_delays) + 1
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            server = None
            try:
                logger.info(f"E-posta gönderiliyor... Deneme {attempt}/{max_attempts}")
                
                if settings.smtp_port == 465:
                    server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10.0)
                else:
                    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10.0)
                    server.ehlo()
                    if settings.smtp_use_tls and server.has_extn("starttls"):
                        server.starttls()
                        server.ehlo()
                        
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                    
                server.send_message(msg)
                logger.info("E-posta başarıyla gönderildi.")
                return True, attempt, ""
                
            except Exception as e:
                last_error = str(e)
                # Şifre varsa hata mesajından temizle
                if settings.smtp_password and settings.smtp_password in last_error:
                    last_error = last_error.replace(settings.smtp_password, "********")
                logger.error(f"E-posta gönderim denemesi {attempt} başarısız: {last_error}")
                
                # Eğer daha deneme hakkımız varsa bekle
                if attempt < max_attempts:
                    delay = self.retry_delays[attempt - 1]
                    logger.info(f"{delay} saniye bekleniyor...")
                    time.sleep(delay)
            finally:
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass

        return False, max_attempts, last_error
