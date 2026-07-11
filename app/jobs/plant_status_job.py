import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from app.extractors.isolar.extractor import IsolarExtractor
from app.database.plant_status_repository import PlantStatusRepository
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger("PlantStatusJob")

def send_status_email(subject: str, html_body: str) -> bool:
    """SMTP üzerinden GES durum uyarısı e-postası gönderir."""
    if not settings.smtp_enabled:
        logger.info("SMTP devre dışı. E-posta gönderilmedi.")
        return False
    if not settings.smtp_host or not settings.alert_email:
        logger.warning("SMTP sunucu adresi veya alıcı adresi eksik.")
        return False

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from if settings.smtp_from else settings.smtp_username
    msg["To"] = settings.alert_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

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
        logger.info(f"E-posta başarıyla gönderildi: {subject}")
        return True
    except Exception as e:
        logger.error(f"E-posta gönderimi başarısız: {e}")
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


class PlantStatusJob:
    """
    Neden: Güneş Enerjisi Santrallerinin (GES) canlı durumlarını iSolarCloud üzerinden çeker,
    durum değişikliklerini (Normal/Abnormal/Offline) algılar ve e-posta bildirimlerini yönetir.
    """

    def __init__(self):
        self.repo = PlantStatusRepository()

    def run(self) -> Dict[str, Any]:
        """
        Santral durum kontrolü akışı.
        """
        logger.info("PlantStatusJob çalıştırılıyor...")

        # 0. Çalışma Saatleri Kontrolü (08:00 - 18:00 arası)
        current_hour = datetime.now().hour
        if not (8 <= current_hour <= 18):
            logger.info(f"Saat {current_hour:02d}:00. Çalışma saatleri (08-18) dışında olduğu için durduruldu.")
            return {"status": "SKIPPED", "reason": "Dış çalışma saatleri"}

        from playwright.sync_api import sync_playwright
        ISOLAR_PROFILE_DIR = Path("config/isolar_browser_profile")

        results = {}
        error_msg = None
        pw = None
        context = None

        # 1. Playwright persistent context ile bağlan
        try:
            ISOLAR_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            pw = sync_playwright().start()
            logger.info("Playwright persistent context başlatılıyor (headless=True)...")
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(ISOLAR_PROFILE_DIR),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            extractor = IsolarExtractor(page, run_id="plant-status")

            # 2. login_and_verify() - Oturum geçerliyse atla
            logger.info("Mevcut oturum doğrulanıyor...")
            try:
                page.goto(settings.base_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"Giriş sayfası yüklenemedi, yine de login denenecek: {e}")

            # Oturum belirtileri kontrolü
            authenticated = False
            for selector in [".el-aside", ".sidebar", ".plant-list", ".user-avatar"]:
                try:
                    if page.locator(selector).first.is_visible(timeout=2000):
                        authenticated = True
                        break
                except Exception:
                    pass

            if authenticated or "plant" in page.url.lower():
                logger.info("Mevcut oturum aktif. Giriş aşaması atlanıyor.")
            else:
                logger.info("Oturum doğrulanamadı. Yeniden giriş yapılıyor...")
                extractor.login_and_verify()

            # 3. get_plant_statuses() - durumları çek
            results = extractor.get_plant_statuses()
        except Exception as e:
            error_msg = f"iSolar santral durumlarını çekerken hata oluştu: {e}"
            logger.error(error_msg)
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

        if not results:
            return {
                "status": "FAILED",
                "results": {},
                "error": error_msg or "Santrallerden veri okunamadı."
            }

        # 4. DB'den önceki durumları al
        previous_statuses = self.repo.get_latest_statuses()
        logger.info(f"Önceki santral durumları: {previous_statuses}")

        # 5 & 7. Karşılaştır ve bildirim gönder
        notified_statuses = {}
        detected_at_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        dashboard_url = os.environ.get("DASHBOARD_URL", "http://localhost:8081")

        def get_other_plants_summary(current_plant: str, current_results: dict) -> str:
            others = []
            for name, status in current_results.items():
                if name == current_plant:
                    continue
                others.append(f"{name}: {status}")
            return ", ".join(others) if others else "Diğer santral bulunamadı."

        for plant_name, status in results.items():
            prev_status = previous_statuses.get(plant_name)
            notified_statuses[plant_name] = False

            # Durum Değişikliği: Normal -> Anormal (Abnormal / Offline)
            if (prev_status == "Normal" or prev_status is None) and status in ["Abnormal", "Offline"]:
                subject = f"⚠️ GES Durum Uyarısı — {plant_name}"
                
                alert_template_path = Path("templates/plant_alert.html")
                if alert_template_path.exists():
                    html_content = alert_template_path.read_text(encoding="utf-8")
                else:
                    html_content = "Plant $PLANT_NAME went from $STATUS_FROM to $STATUS_TO"

                other_summary = get_other_plants_summary(plant_name, results)
                html_content = html_content.replace("$PLANT_NAME", plant_name)\
                                            .replace("$STATUS_FROM", prev_status or "Bilinmiyor")\
                                            .replace("$STATUS_TO", status)\
                                            .replace("$DETECTED_AT", detected_at_str)\
                                            .replace("$DURATION_HTML", "")\
                                            .replace("$OTHER_PLANTS", other_summary)\
                                            .replace("$DASHBOARD_URL", dashboard_url)

                send_status_email(subject, html_content)
                notified_statuses[plant_name] = True

            # Durum Değişikliği: Anormal -> Normal (Çözüldü)
            elif prev_status in ["Abnormal", "Offline"] and status == "Normal":
                anomaly_start = None
                latest_notified = self.repo.get_latest_notified_record(plant_name)
                if latest_notified:
                    anomaly_start = latest_notified.timestamp

                duration_str = "Bilinmiyor"
                if anomaly_start:
                    duration = datetime.utcnow() - anomaly_start
                    minutes = int(duration.total_seconds() / 60)
                    duration_str = f"{minutes} dakika"

                subject = f"✅ GES Normale Döndü — {plant_name}"
                resolved_template_path = Path("templates/plant_resolved.html")
                if resolved_template_path.exists():
                    html_content = resolved_template_path.read_text(encoding="utf-8")
                else:
                    html_content = "Plant $PLANT_NAME returned to Normal. Duration: $DURATION"

                html_content = html_content.replace("$PLANT_NAME", plant_name)\
                                            .replace("$DURATION", duration_str)\
                                            .replace("$DASHBOARD_URL", dashboard_url)

                send_status_email(subject, html_content)
                notified_statuses[plant_name] = True

            # Durum Devamı: Anormal -> Anormal (Uyarının devam etmesi)
            elif prev_status in ["Abnormal", "Offline"] and status in ["Abnormal", "Offline"]:
                latest_notified = self.repo.get_latest_notified_record(plant_name)
                if latest_notified:
                    time_passed = datetime.utcnow() - latest_notified.timestamp
                    if time_passed >= timedelta(minutes=30):
                        subject = "⚠️ GES Durum Uyarısı — Devam Ediyor"

                        alert_template_path = Path("templates/plant_alert.html")
                        if alert_template_path.exists():
                            html_content = alert_template_path.read_text(encoding="utf-8")
                        else:
                            html_content = "Plant $PLANT_NAME is still $STATUS_TO"

                        # İlk bildirim zamanını bul
                        history = self.repo.get_status_history(plant_name=plant_name, hours=48)
                        first_notified_ts = latest_notified.timestamp
                        for h in reversed(history):
                            if h.status == "Normal":
                                first_notified_ts = None
                            elif h.notified and first_notified_ts is None:
                                first_notified_ts = h.timestamp

                        if not first_notified_ts:
                            first_notified_ts = latest_notified.timestamp

                        total_duration = datetime.utcnow() - first_notified_ts
                        duration_mins = int(total_duration.total_seconds() / 60)
                        duration_str = f"{duration_mins} dakika"

                        duration_html = f"<tr><td class='label'>Süre</td><td class='value'><strong>{duration_str}</strong></td></tr>"
                        other_summary = get_other_plants_summary(plant_name, results)

                        html_content = html_content.replace("$PLANT_NAME", plant_name)\
                                                    .replace("$STATUS_FROM", prev_status)\
                                                    .replace("$STATUS_TO", status)\
                                                    .replace("$DETECTED_AT", first_notified_ts.strftime("%d.%m.%Y %H:%M"))\
                                                    .replace("$DURATION_HTML", duration_html)\
                                                    .replace("$OTHER_PLANTS", other_summary)\
                                                    .replace("$DASHBOARD_URL", dashboard_url)

                        send_status_email(subject, html_content)
                        notified_statuses[plant_name] = True
                else:
                    # Daha önce hiç bildirim gitmemişse ilk tespittir
                    subject = f"⚠️ GES Durum Uyarısı — {plant_name}"
                    alert_template_path = Path("templates/plant_alert.html")
                    if alert_template_path.exists():
                        html_content = alert_template_path.read_text(encoding="utf-8")
                    else:
                        html_content = "Plant $PLANT_NAME went from $STATUS_FROM to $STATUS_TO"

                    other_summary = get_other_plants_summary(plant_name, results)
                    html_content = html_content.replace("$PLANT_NAME", plant_name)\
                                                .replace("$STATUS_FROM", prev_status or "Bilinmiyor")\
                                                .replace("$STATUS_TO", status)\
                                                .replace("$DETECTED_AT", detected_at_str)\
                                                .replace("$DURATION_HTML", "")\
                                                .replace("$OTHER_PLANTS", other_summary)\
                                                .replace("$DASHBOARD_URL", dashboard_url)

                    send_status_email(subject, html_content)
                    notified_statuses[plant_name] = True

        # 6. DB'ye kaydet
        self.repo.save_statuses(results, previous_statuses, notified_statuses)

        return {
            "status": "SUCCESS",
            "results": results,
            "error": None
        }
