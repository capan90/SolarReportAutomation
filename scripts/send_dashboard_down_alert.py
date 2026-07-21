"""
Neden: run_dashboard_hidden.vbs, dashboard art arda 4 kez çöktüğünde yeniden
başlatmayı bırakır (sonsuz çökme döngüsü koruması) — bu script o anda VBS
tarafından çağrılıp sistem yöneticisine e-posta uyarısı gönderir; aksi halde
dashboard'ın kapalı kaldığı ancak biri fark edince anlaşılır (2026-07-21 olayı).
Best-effort çalışır: gönderim başarısız olsa da exit 0 döner (VBS'i bloklamaz),
sonuç her durumda log dosyasına yazılır (sessiz hata yok).
"""
import smtplib
import socket
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.logger import setup_logger  # noqa: E402

logger = setup_logger("DashboardDownAlert")


def build_subject(now: datetime) -> str:
    # E-posta marka standardı: "{emoji} Erdemsoft GES — {Durum} ({Tarih})", <= 60 karakter
    return f"🔴 Erdemsoft GES — Dashboard Kapalı ({now.strftime('%d.%m.%Y %H:%M')})"


def build_body(now: datetime, hostname: str) -> str:
    return f"""
    <p><b>Dashboard web sunucusu kapalı kaldı.</b></p>
    <p>Başlatıcı döngüsü (run_dashboard_hidden.vbs) art arda 4 çökmenin ardından
    yeniden başlatmayı bıraktı ve görev sonlandı.</p>
    <p style="background:#f6f8fa;padding:8px 12px;">
    <b>Sunucu:</b> {hostname}<br>
    <b>Zaman:</b> {now.strftime("%d.%m.%Y %H:%M:%S")}<br>
    <b>Gereken aksiyon:</b> RDP ile bağlanıp <code>logs\\</code> altındaki son
    kayıtlardan çökme nedenini inceleyin, ardından görevi elle başlatın:<br>
    <code>Start-ScheduledTask SolarReportAutomation_Dashboard</code></p>
    <p>Bu e-posta Erdemsoft GES Yönetim Sistemi tarafından otomatik olarak oluşturulmuştur.</p>
    """


def main() -> int:
    now = datetime.now()
    hostname = socket.gethostname()
    recipient = settings.smtp_to_system or settings.alert_email

    if not settings.smtp_enabled:
        logger.warning("Dashboard kapalı uyarısı gönderilemedi: SMTP devre dışı.")
        return 0
    if not settings.smtp_host or not recipient:
        logger.warning("Dashboard kapalı uyarısı gönderilemedi: SMTP sunucusu veya sistem alıcısı eksik.")
        return 0

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from if settings.smtp_from else settings.smtp_username
    msg["To"] = recipient
    msg["Subject"] = build_subject(now)
    msg.attach(MIMEText(build_body(now, hostname), "html", "utf-8"))

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
        logger.info(f"Dashboard kapalı uyarısı gönderildi: {recipient}")
    except Exception as e:
        logger.error(f"Dashboard kapalı uyarısı gönderilemedi: {e}")
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
