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

# Neden: Konu satırı ve dönem metinlerinde Türkçe ay adı gösterilir.
AY_ADLARI = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

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

    def _extract_report_month(self, event: NotificationEvent) -> str:
        """
        Neden: Aylık rapor konu/gövdesi için dönemi ("Temmuz 2026") üretmek.
        Ek dosya adındaki YYYYMM deseni (ör. mahsup_202607_aylik.xlsx) kaynak alınır;
        bulunamazsa içinde bulunulan ay kullanılır.
        """
        if event.attachment_path:
            m = re.search(r"(\d{4})(\d{2})", Path(event.attachment_path).name)
            if m and 1 <= int(m.group(2)) <= 12:
                return f"{AY_ADLARI[int(m.group(2)) - 1]} {m.group(1)}"
        today = datetime.date.today()
        return f"{AY_ADLARI[today.month - 1]} {today.year}"

    def _build_subject(self, event: NotificationEvent, email_profile: str) -> str:
        """
        Neden: Tüm senaryolarda tek kurumsal konu formatı kullanılır:
        "{emoji} Erdemsoft GES — {Durum} ({Tarih/Dönem})" (maks. 60 karakter).
        Run ID, olay tipi gibi teknik detaylar gövdedeki "Teknik Detaylar" bölümündedir.
        """
        event_type = event.event_type.upper()
        if event_type == "SUCCESS":
            if email_profile == "monthly":
                return f"✅ Erdemsoft GES — Aylık Mahsuplaşma Raporu ({self._extract_report_month(event)})"
            return f"✅ Erdemsoft GES — Günlük Mahsuplaşma Raporu ({self._extract_report_date(event)})"
        if event_type == "CAPTCHA_REQUIRED":
            return f"🔐 Erdemsoft GES — Doğrulama Gerekiyor ({datetime.date.today().strftime('%d.%m.%Y')})"
        return f"❌ Erdemsoft GES — Rapor Oluşturulamadı ({self._extract_report_date(event)})"

    def _friendly_error_summary(self, event: NotificationEvent) -> str:
        """
        Neden: Hata e-postası yöneticiye gider; ham exception metni yerine
        anlaşılır bir özet gösterilir. Kaynak, stage_summary içindeki hata
        ifadelerinden/istisna adlarından tespit edilir.
        """
        text = event.stage_summary or ""
        event_type = event.event_type.upper()
        reasons = []
        if "SourceAuthenticationError" in text or "GAOSB raporu indirme aşaması başarısız" in text:
            reasons.append("GAOSB portalından rapor alınamadı")
        if "IsolarError" in text or "iSolar Curve indirme aşaması başarısız" in text:
            reasons.append("iSolar portalından üretim verisi alınamadı")
        if not reasons:
            if event_type == "LOGIN_FAILED":
                reasons.append("Portala giriş yapılamadı")
            elif event_type == "DOWNLOAD_FAILED":
                reasons.append("Rapor dosyası indirilemedi")
            elif event_type == "DATABASE_FAILED":
                reasons.append("Veriler veritabanına kaydedilemedi")
            else:
                reasons.append("Veri işleme sırasında hata oluştu")
        return ", ".join(reasons)

    def _render_summary_html(self, summary: str) -> str:
        """
        Neden: stage_summary düz metnindeki "Etiket: X kWh" satırlarını kalın etiketli,
        iki nokta hizalı ve hafif yeşil arkaplanlı bir istatistik tablosuna dönüştürmek.
        Diğer satırlar paragraf olarak korunur. E-posta istemcisi uyumluluğu için
        stiller inline verilir (head CSS'e bağımlılık yok).
        """
        stat_re = re.compile(r"^([^:]{2,40}):\s*(.+kWh)$")
        parts: list[str] = []
        stat_rows: list[tuple[str, str]] = []

        def flush_stats() -> None:
            if not stat_rows:
                return
            # Neden: Şablonların global "td { border-bottom }" ve "table { width: 100% }"
            # kuralları inline stillerle ezilir; istatistik tablosu çizgisiz ve dar kalır.
            cell = "border-bottom: none; padding: 4px"
            rows = "".join(
                "<tr>"
                f'<td style="font-weight: bold; {cell} 4px 4px 0; white-space: nowrap;">{label}</td>'
                f'<td style="{cell} 10px 4px 0;">:</td>'
                f'<td style="{cell} 0;">{value}</td>'
                "</tr>"
                for label, value in stat_rows
            )
            parts.append(
                '<div style="background-color: #f1f8e9; border: 1px solid #dcedc8; '
                'border-radius: 6px; padding: 14px 18px; margin-top: 15px;">'
                f'<table style="border-collapse: collapse; width: auto; margin: 0;" role="presentation">{rows}</table>'
                "</div>"
            )
            stat_rows.clear()

        for line in summary.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = stat_re.match(line)
            if m:
                stat_rows.append((m.group(1), m.group(2)))
            else:
                flush_stats()
                parts.append(f'<p style="margin: 12px 0 0 0;">{line}</p>')
        flush_stats()
        return "".join(parts)

    def render_body(self, event: NotificationEvent, email_profile: str = "default") -> str:
        """
        Neden: HTML şablonundaki değişkenleri ($RUN_ID vb.) olay verileriyle güvenli
        şekilde değiştirmek (string.Template kullanarak sıfır bağımlılıklı şablonlama).
        email_profile, günlük/aylık başlık ve dönem metinlerini ayrıştırmak için kullanılır.
        """
        raw_template = self._get_template_content(event.event_type)

        # None olan alanları boş dizeye dönüştür
        stage_summary = event.stage_summary if event.stage_summary else ""
        validation_summary = event.validation_summary if event.validation_summary else ""

        # Neden: "Etiket: X kWh" satırları hizalı istatistik tablosuna,
        # diğer satırlar paragrafa dönüştürülür.
        stage_summary = self._render_summary_html(stage_summary)

        # Neden: Günlük ve aylık rapor aynı şablonu paylaşır; başlık, dönem etiketi
        # ve ek notu profile göre ayrışır.
        is_monthly = email_profile == "monthly"
        report_kind = "Aylık" if is_monthly else "Günlük"
        report_period = self._extract_report_month(event) if is_monthly else self._extract_report_date(event)

        # Neden: Ek varsa kullanıcıya "rapor ekte" notunu göster; yoksa boş bırak.
        # Dosya adı/yolu gibi teknik detaylar yönetici e-postasında gösterilmez.
        attachment_note = ""
        if event.attachment_path:
            attachment_note = (
                '<p style="background-color: #e8f5e9; padding: 10px; border-radius: 4px;">'
                f"&#128206; {report_kind} mahsuplaşma raporu ekte sunulmaktadır.</p>"
            )

        # Neden: Konu satırından çıkarılan teknik bilgiler (Run ID, olay tipi vb.)
        # gövdenin en altında sade bir "Teknik Detaylar" bölümünde tutulur.
        tech_details = (
            '<div style="font-size: 0.75em; color: #999; margin-top: 20px; '
            'border-top: 1px dashed #e0e0e0; padding-top: 8px;">'
            "<strong>Teknik Detaylar:</strong> "
            f"Run ID: {event.run_id} &middot; Olay: {event.event_type} &middot; "
            f"Süre: {event.duration_ms} ms &middot; Sunucu: {event.machine_name} &middot; "
            f"Commit: {event.git_commit}</div>"
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
            "REPORT_TITLE": f"{report_kind} Mahsuplaşma Raporu Hazır",
            "REPORT_KIND": report_kind,
            "PERIOD_LABEL": "Dönem" if is_monthly else "Tarih",
            "REPORT_PERIOD": report_period,
            "TECH_DETAILS": tech_details,
            "ERROR_SUMMARY": self._friendly_error_summary(event),
            "DASHBOARD_URL": os.environ.get("DASHBOARD_URL", "http://localhost:8081")
        }
        
        # string.Template kullanarak placeholderları değiştir (safe_substitute hata vermesini önler)
        return Template(raw_template).safe_substitute(template_data)

    def send(self, event: NotificationEvent, email_profile: str = "default") -> tuple[bool, int, str]:
        """
        Neden: E-posta gönderimini SMTP üzerinden gerçekleştirmek. 
        Başarısızlık durumunda belirlenen saniyelerle 3 kez tekrar dener.
        Geriye: (Başarı Durumu, Deneme Sayısı, Varsa Hata Mesajı)
        """
        if not settings.smtp_enabled:
            logger.info("SMTP_ENABLED=false. Mail gönderimi devre dışı bırakılmıştır.")
            return False, 0, "SMTP_ENABLED=false"

        # Alıcı adresini profile göre belirle
        recipient = settings.alert_email
        if email_profile == "daily":
            recipient = settings.smtp_to_daily
        elif email_profile == "monthly":
            recipient = settings.smtp_to_monthly
        elif email_profile == "plant_alert":
            recipient = settings.smtp_to_plant_alert
        elif email_profile == "system":
            recipient = settings.smtp_to_system

        if not settings.smtp_host or not recipient:
            logger.warning(f"SMTP ayarları veya alıcı adresi ({email_profile}) eksik. Mail gönderimi atlanıyor.")
            return False, 0, f"SMTP_HOST veya alıcı adresi ({email_profile}) eksik."

        body = self.render_body(event, email_profile=email_profile)

        # Mail nesnesi oluştur
        msg = MIMEMultipart()
        msg["From"] = settings.smtp_from if settings.smtp_from else settings.smtp_username
        msg["To"] = recipient
        # Neden: Konu satırında teknik detay (Run ID vb.) olmaz; tek kurumsal format kullanılır.
        msg["Subject"] = self._build_subject(event, email_profile)
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
