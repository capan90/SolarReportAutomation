"""
Neden: Zamanlanmış bir iş yakalanmamış istisnayla öldüğünde (2026-07-22
DailySettlement olayı: cwd System32 → PermissionError → stderr'e giden, hiçbir
yerde görünmeyen ölüm) NotificationService devreye giremiyor ve kullanıcı işin
öldüğünü ancak mail gelmeyince fark ediyor. Bu modül main.py'nin except
dallarından çağrılır: SMTP_TO_SYSTEM alıcısına hata + son log satırlarıyla
uyarı maili atar. Best-effort: kendi hatası işi asla etkilemez, sonuç loglanır.
Graceful FAILED yolları zaten notify_pipeline ile mail attığından burada yalnızca
yakalanmamış istisna yolu hedeflenir (çift mail olmaz).
"""
import html
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger("SystemAlert")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_TAIL_LINES = 40


def build_subject(job_name: str, now: datetime) -> str:
    # E-posta marka standardı: "{emoji} Erdemsoft GES — {Durum} ({Tarih})", <= 60 karakter
    return f"🔴 Erdemsoft GES — {job_name} Başarısız ({now.strftime('%d.%m.%Y %H:%M')})"


def collect_log_tail(lines: int = LOG_TAIL_LINES) -> str:
    """En güncel log dosyasının kuyruğunu döndürür; okunamazsa nedenini söyler."""
    try:
        log_dir = PROJECT_ROOT / "logs"
        log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            return "(logs/ altında log dosyası bulunamadı)"
        content = log_files[0].read_text(encoding="utf-8", errors="replace").splitlines()
        tail = content[-lines:]
        return f"[{log_files[0].name} — son {len(tail)} satır]\n" + "\n".join(tail)
    except Exception as e:
        return f"(log kuyruğu okunamadı: {e})"


def build_body(job_name: str, error: str, now: datetime, log_tail: str = "") -> str:
    log_section = ""
    if log_tail:
        log_section = (
            '<p><b>Son log kayıtları:</b></p>'
            '<pre style="background:#1e293b;color:#e2e8f0;padding:10px 14px;'
            'border-radius:6px;font-size:12px;overflow-x:auto;white-space:pre-wrap;">'
            f"{html.escape(log_tail)}</pre>"
        )
    return f"""
    <p><b>{html.escape(job_name)} beklenmeyen bir hatayla sonlandı.</b></p>
    <p>İş, hatayı kendi bildirim akışına ulaşamadan kaybetti (yakalanmamış istisna) —
    bu mail olmasaydı başarısızlık yalnızca gelmeyen rapordan anlaşılacaktı.</p>
    <p style="background:#f6f8fa;padding:8px 12px;">
    <b>Zaman:</b> {now.strftime("%d.%m.%Y %H:%M:%S")}<br>
    <b>Hata:</b> <code>{html.escape(error)}</code></p>
    {log_section}
    <p>Bu e-posta Erdemsoft GES Yönetim Sistemi tarafından otomatik olarak oluşturulmuştur.</p>
    """


def send_job_failure_alert(job_name: str, error: str) -> bool:
    """İş çökme uyarısını gönderir. Best-effort: hiçbir durumda exception fırlatmaz."""
    try:
        now = datetime.now()
        recipient = settings.smtp_to_system or settings.alert_email

        if not settings.smtp_enabled:
            logger.warning(f"{job_name} çökme uyarısı gönderilemedi: SMTP devre dışı.")
            return False
        if not settings.smtp_host or not recipient:
            logger.warning(f"{job_name} çökme uyarısı gönderilemedi: SMTP sunucusu veya sistem alıcısı eksik.")
            return False

        msg = MIMEMultipart()
        msg["From"] = settings.smtp_from if settings.smtp_from else settings.smtp_username
        msg["To"] = recipient
        msg["Subject"] = build_subject(job_name, now)
        msg.attach(MIMEText(build_body(job_name, error, now, collect_log_tail()), "html", "utf-8"))

        server = None
        try:
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
            logger.info(f"{job_name} çökme uyarısı gönderildi: {recipient}")
            return True
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"{job_name} çökme uyarısı gönderilemedi: {e}")
        return False
