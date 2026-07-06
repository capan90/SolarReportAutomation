import os
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings, BASE_DIR
from app.core.logger import setup_logger
from app.dashboard.service import DashboardService
from app.analytics.service import AnalyticsService

logger = setup_logger("DashboardWebServer")

class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    Neden: Dashboard API endpoint'lerini ve statik dosyaları (HTML/CSS/JS) 
    sıfır dış bağımlılıkla ve salt-okunur (GET) kurallarına göre sunmak.
    """
    service = DashboardService()
    analytics_service = AnalyticsService()
    static_dir = Path(__file__).resolve().parent / "static"

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        if path == "/api/settlement/trigger":
            self._handle_settlement_trigger()
        else:
            self._send_method_not_allowed()

    def do_PUT(self):
        self._send_method_not_allowed()

    def do_DELETE(self):
        self._send_method_not_allowed()

    def do_GET(self):
        """
        Neden: Yönlendirme (Routing) mantığını işletmek.
        """
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. API Endpoint Yönlendirmeleri
        if path.startswith("/api/"):
            self._handle_api(path)
        # 2. Statik Dosya Sunumu
        else:
            self._handle_static(path)

    def _handle_api(self, path: str) -> None:
        """
        Neden: REST API taleplerini karşılayarak standart JSON sözleşmesini dönmek.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        response_data = None
        error_message = None
        
        try:
            if path == "/api/kpis":
                summary = self.service.get_executive_summary()
                response_data = summary.to_dict()
            elif path == "/api/runs":
                runs = self.service.get_pipeline_history(limit=15)
                response_data = [r.to_dict() for r in runs]
            elif path == "/api/health":
                health = self.service.get_health_status()
                response_data = health.to_dict()
            elif path == "/api/notifications":
                notifs = self.service.get_notification_history(limit=15)
                response_data = [n.to_dict() for n in notifs]
            elif path == "/api/analytics/overview":
                overview = self.analytics_service.get_overview()
                response_data = overview.to_dict()
            elif path == "/api/analytics/daily":
                daily = self.analytics_service.get_daily_summary()
                response_data = [d.to_dict() for d in daily]
            elif path == "/api/analytics/weekly":
                weekly = self.analytics_service.get_weekly_summary()
                response_data = [w.to_dict() for w in weekly]
            elif path == "/api/analytics/monthly":
                monthly = self.analytics_service.get_monthly_summary()
                response_data = [m.to_dict() for m in monthly]
            elif path == "/api/analytics/missing-days":
                missing = self.analytics_service.get_missing_days()
                response_data = [m.to_dict() for m in missing]
            elif path == "/api/analytics/trend":
                trend = self.analytics_service.get_trend()
                response_data = trend.to_dict()
            elif path == "/api/settlement/latest":
                reports_dir = Path("outputs/reports")
                files = list(reports_dir.rglob("mahsup_*.xlsx"))
                if files:
                    files.sort(key=lambda p: p.name)
                    latest_file = files[-1]
                    date_str = latest_file.name.replace("mahsup_", "").replace(".xlsx", "")
                    formatted_date = f"{date_str[6:8]}.{date_str[4:6]}.{date_str[:4]}"
                    size_kb = round(latest_file.stat().st_size / 1024, 2)
                    response_data = {
                        "filename": latest_file.name,
                        "date": formatted_date,
                        "size_kb": size_kb,
                        "download_url": "/api/settlement/download"
                    }
                else:
                    response_data = None
            elif path == "/api/settlement/download":
                reports_dir = Path("outputs/reports")
                files = list(reports_dir.rglob("mahsup_*.xlsx"))
                if files:
                    files.sort(key=lambda p: p.name)
                    latest_file = files[-1]
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    self.send_header("Content-Disposition", f"attachment; filename={latest_file.name}")
                    self.send_header("Content-Length", str(latest_file.stat().st_size))
                    self.end_headers()
                    with open(latest_file, "rb") as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_error(404, "Rapor dosyası bulunamadı.")
                    return
            elif path == "/api/settings":
                from app.sources import SourceRegistry
                from app.database.db_session import SessionLocal
                from app.database.models import NotificationHistory
                
                registry = SourceRegistry()
                
                if not settings.smtp_enabled:
                    smtp_status = "pasif"
                elif not (settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.alert_email):
                    smtp_status = "eksik"
                else:
                    smtp_status = "aktif"
                    
                last_mail_status = "GÖNDERİLMEDİ"
                last_mail_error = None
                db_session = SessionLocal()
                try:
                    last_notif = db_session.query(NotificationHistory).order_by(NotificationHistory.id.desc()).first()
                    if last_notif:
                        last_mail_status = last_notif.status
                        last_mail_error = last_notif.error_message
                except Exception:
                    pass
                finally:
                    db_session.close()
                    
                response_data = {
                    "dashboard_port": settings.dashboard_port,
                    "dashboard_access_mode": settings.dashboard_access_mode,
                    "active_source": registry.default_source(),
                    "registered_sources": registry.list_sources(),
                    "app_env": settings.app_env,
                    "log_level": settings.log_level,
                    "smtp_status": smtp_status,
                    "smtp_host": settings.smtp_host,
                    "smtp_username": settings.smtp_username,
                    "smtp_password_masked": "********" if settings.smtp_password else "",
                    "smtp_to": settings.alert_email,
                    "smtp_last_status": last_mail_status,
                    "smtp_last_error": last_mail_error,
                    "backup_retention_days": 14
                }
            elif path.startswith("/api/metrics/"):
                # URL parametresinden metrik adını al
                metric_name = path.replace("/api/metrics/", "").strip()
                if metric_name:
                    series = self.service.get_metric_history(metric_name, limit=30)
                    response_data = series.to_dict()
                else:
                    error_message = "Metrik adı belirtilmedi."
            else:
                self.send_error(404, "API endpoint bulunamadı.")
                return
                
        except Exception as e:
            logger.error(f"API hatası ({path}): {e}")
            error_message = "Sistem kaynağına şu anda erişilemiyor. Lütfen sistem yöneticinizle iletişime geçin."

        # Standart Response Sözleşmesi
        contract = {
            "success": error_message is None,
            "data": response_data,
            "error": error_message,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": settings.app_env,
                "version": "v1.0.0-GA"
            }
        }
        self.wfile.write(json.dumps(contract, ensure_ascii=False).encode("utf-8"))

    def _handle_static(self, path: str) -> None:
        """
        Neden: HTML/CSS/JS ve grafik dosyalarını güvenli şekilde sunmak (Path Traversal engelleme).
        """
        # URL path /static/ ile başlıyorsa, bunu klasör eşleştirmesi için kaldır
        rel_path = path
        if rel_path.startswith("/static/"):
            rel_path = rel_path.replace("/static/", "", 1)

        # Varsayılan dosya index.html
        if rel_path == "/" or rel_path == "":
            rel_path = "/index.html"

        # Dosya yolunu oluştur ve çöz (Dizin dışına çıkışı önlemek için resolve() kullan)
        requested_file = (self.static_dir / rel_path.lstrip("/")).resolve()
        
        # Güvenlik Kontrolü: İstenen dosya kesinlikle static_dir altında mı?
        if not requested_file.is_relative_to(self.static_dir) or not requested_file.is_file():
            self._send_not_found()
            return

        # Content-Type belirle
        suffix = requested_file.suffix.lower()
        content_type = "text/plain"
        if suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif suffix == ".css":
            content_type = "text/css"
        elif suffix == ".js":
            content_type = "application/javascript"
        elif suffix == ".png":
            content_type = "image/png"
        elif suffix == ".json":
            content_type = "application/json"

        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(requested_file.stat().st_size))
            self.end_headers()
            
            with open(requested_file, "rb") as f:
                self.wfile.write(f.read())
        except Exception as e:
            logger.error(f"Statik dosya sunum hatası: {e}")
            self.send_error(500, "Dosya okuma hatası.")

    def _send_method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        contract = {
            "success": False,
            "data": None,
            "error": "HTTP Method Not Allowed. Bu sunucu salt-okunurdur.",
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": settings.app_env,
                "version": "v1.0.0-GA"
            }
        }
        self.wfile.write(json.dumps(contract).encode("utf-8"))

    def _send_not_found(self) -> None:
        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        contract = {
            "success": False,
            "data": None,
            "error": "İstenen kaynak bulunamadı.",
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": settings.app_env,
                "version": "v1.0.0-GA"
            }
        }
        self.wfile.write(json.dumps(contract).encode("utf-8"))

    def _handle_settlement_trigger(self) -> None:
        """
        Neden: Salt-okunur (read-only) web sunucu kurallarına özel bir istisna 
        tanımlayarak, manuel mahsuplaşma tetikleme isteğini (POST) karşılamak.
        """
        logger.warning("ÖZEL İSTİSNA: Salt-okunur (read-only) kuralı esnetilerek manuel mahsuplaşma tetiklendi.")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        error_message = None
        response_data = None
        
        try:
            from app.jobs.daily_settlement_job import DailySettlementJob
            job = DailySettlementJob()
            result = job.run(target_date=None)
            response_data = result
        except Exception as e:
            logger.error(f"Manuel mahsuplaşma tetikleme hatası: {e}")
            error_message = str(e)

        contract = {
            "success": error_message is None,
            "data": response_data,
            "error": error_message,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": settings.app_env,
                "version": "v1.0.0-GA"
            }
        }
        self.wfile.write(json.dumps(contract, ensure_ascii=False).encode("utf-8"))

    # Log çıktılarının kirlenmesini önlemek için standard log metodunu ez
    def log_message(self, format, *args):
        logger.debug(f"{self.address_string()} - {format%args}")


def start_dashboard_server(port: int = None) -> None:
    """
    Neden: Dashboard web sunucusunu yapılandırmaya göre localhost veya LAN binding ile ayağa kaldırmak.
    """
    if port is None:
        port = settings.dashboard_port
        
    access_mode = settings.dashboard_access_mode
    host = "0.0.0.0" if access_mode == "lan" else "127.0.0.1"
    
    server_address = (host, port)
    httpd = HTTPServer(server_address, DashboardRequestHandler)
    
    logger.info(f"Dashboard Web Server BAŞLATILDI: http://{host if host != '0.0.0.0' else 'localhost'}:{port} (Mod: {access_mode})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Dashboard Web Server durduruluyor...")
    finally:
        httpd.server_close()
        logger.info("Dashboard Web Server kapatıldı.")

if __name__ == "__main__":
    start_dashboard_server()
