import os
import re
import json
import uuid
import asyncio
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings, BASE_DIR
from app.core.logger import setup_logger
from app.dashboard.service import DashboardService
from app.analytics.service import AnalyticsService
from app.dashboard.auth import DashboardAuth
from app.database.db_session import SessionLocal
from app.database.models import DashboardUser, AuditLog

logger = setup_logger("DashboardWebServer")

REPORTS_DIR = Path("outputs/reports")
# Neden: Günlük rapor 'mahsup_YYYYMMDD.xlsx', aylık rapor 'mahsup_YYYYMM_aylik.xlsx'
# adlandırmasını kullanır; en güncel dosya isimdeki rakamlara göre seçilir.
DAILY_REPORT_RE = re.compile(r"^mahsup_(\d{8})\.xlsx$")
MONTHLY_REPORT_RE = re.compile(r"^mahsup_(\d{6})_aylik\.xlsx$")

# Neden: "Kaydet ve Yeniden Başlat" akışı — frozen settings nesnesi yalnızca process
# başlangıcında kurulduğu için .env değişiklikleri restart gerektirir. Process bu
# kodla sonlanır; gizli VBS başlatıcısındaki döngü (run_dashboard_hidden.vbs) process'i
# taze konfigürasyonla hemen yeniden başlatır. Task Scheduler'ın restart-on-failure
# ayarına GÜVENİLMEZ: nonzero exit kodunu failure saymadığı deneyle doğrulandı
# (2026-07-21). os._exit kullanılır çünkü serve_forever başka thread'den temiz kapatma
# beklemeden sonlanmalı; HTTP yanıtı gönderildikten sonra tetiklendiği için güvenlidir.
RESTART_EXIT_CODE = 10


class _ExclusiveHTTPServer(HTTPServer):
    # Neden: HTTPServer varsayılanı SO_REUSEADDR açar; Windows'ta bu, ikinci bir
    # instance'ın aynı porta sessizce bağlanıp istekleri rastgele paylaşmasına izin
    # verir (2026-07-21 çift dinleyici olayı). Kapalıyken ikinci bind WinError 10048
    # ile anında reddedilir ve start() net bir logla fail eder.
    allow_reuse_address = False

def _schedule_restart(delay_seconds: float = 1.0) -> threading.Timer:
    timer = threading.Timer(delay_seconds, os._exit, args=(RESTART_EXIT_CODE,))
    timer.daemon = True
    timer.start()
    return timer

# Neden: GAOSB captcha bekleme işareti — extractor yazar, dashboard okur/siler.
CAPTCHA_FLAG_PATH = BASE_DIR / "config" / "gaosb_captcha_flag.txt"


def _find_latest_report(pattern: re.Pattern) -> Optional[Path]:
    if not REPORTS_DIR.exists():
        return None
    matches = [(pattern.match(p.name).group(1), p)
               for p in REPORTS_DIR.rglob("mahsup_*.xlsx") if pattern.match(p.name)]
    if not matches:
        return None
    matches.sort(key=lambda t: t[0])
    return matches[-1][1]


def _report_info(path: Optional[Path], kind: str) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    digits = re.sub(r"\D", "", path.stem)
    if kind == "daily" and len(digits) >= 8:
        formatted_date = f"{digits[6:8]}.{digits[4:6]}.{digits[:4]}"
    elif kind == "monthly" and len(digits) >= 6:
        formatted_date = f"{digits[4:6]}.{digits[:4]}"
    else:
        formatted_date = "-"
    return {
        "filename": path.name,
        "date": formatted_date,
        "size_kb": round(path.stat().st_size / 1024, 2),
        "download_url": f"/api/settlement/download/latest/{kind}",
    }


# In-memory store for developer session tokens {token: issued_at_datetime}
_DEV_TOKENS: Dict[str, datetime] = {}
_DEV_TOKEN_TTL_HOURS = 8


def _run_in_clean_thread(job_callable):
    """
    Neden: Playwright Sync API, içinde asyncio event loop bulunan/çalışan bir
    thread'de başlatılamaz ("Playwright Sync API inside the asyncio loop").
    Dashboard süreci uzun ömürlü olduğundan, bir tetiklemede Playwright hata ile
    yarıda kalırsa loop/greenlet artığı handler thread'inde kalır ve SONRAKİ
    tetiklemeler bu hatayla patlar (terminalde her koşu taze process olduğu için
    görülmez). Çözüm: her job'u taze bir OS thread'inde çalıştırıp join etmek —
    yeni thread'de event loop yoktur, thread ölünce Playwright'ın loop durumu da
    onunla birlikte temizlenir. HTTP yanıtı job bitene kadar bekler (mevcut
    eşzamanlı davranış korunur).
    """
    result_box: Dict[str, Any] = {}

    def _target():
        # Belt-and-suspenders: bu thread'e yanlışlıkla bir loop policy miras
        # kaldıysa temizle.
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass
        try:
            result_box["result"] = job_callable()
        except BaseException as e:
            result_box["error"] = e

    t = threading.Thread(target=_target, name="playwright-job", daemon=False)
    t.start()
    t.join()

    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("result")


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    Neden: Dashboard API endpoint'lerini ve statik dosyaları (HTML/CSS/JS)
    sıfır dış bağımlılıkla sunmak. Veri kaynağı settlement DB tablolarıdır.
    """
    service = DashboardService()
    analytics_service = AnalyticsService()
    static_dir = Path(__file__).resolve().parent / "static"
    auth = DashboardAuth()

    def _get_client_ip(self) -> str:
        return self.client_address[0]

    def _get_auth_token(self) -> Optional[str]:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "", 1).strip()
        parsed_url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_url.query)
        token_list = query.get("token")
        if token_list:
            return token_list[0].strip()
        return None

    def _authenticate(self) -> Optional[str]:
        token = self._get_auth_token()
        username = self.auth.verify_session(token)
        if not username:
            self._send_json_contract(None, "Yetkisiz erişim. Geçersiz veya eksik session token.", status_code=401)
            return None
        return username

    # ------------------------------------------------------------------
    # HTTP metod yönlendirmeleri
    # ------------------------------------------------------------------
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # Neden: Binary (Excel) indirme endpoint'leri JSON sözleşmesinden ÖNCE ele
        # alınmalı; aksi halde çift başlık gönderimi dosyayı bozar (eski hata buydu).
        if path in (
            "/api/settlement/download",
            "/api/settlement/download/latest/daily",
            "/api/settlement/download/latest/monthly",
        ) or path.startswith("/api/settlement/download/daily/") or path.startswith("/api/settlement/download/monthly/"):
            username = self._authenticate()
            if not username:
                return

            # Log audit log for report download
            self.auth.log_action(username, self._get_client_ip(), "report_download", details=f"Downloaded: {path}")

            if path == "/api/settlement/download" or path == "/api/settlement/download/latest/daily":
                self._serve_excel(_find_latest_report(DAILY_REPORT_RE))
                return
            if path == "/api/settlement/download/latest/monthly":
                self._serve_excel(_find_latest_report(MONTHLY_REPORT_RE))
                return

            if path.startswith("/api/settlement/download/daily/"):
                date_str = path.replace("/api/settlement/download/daily/", "").strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    month_str = dt.strftime("%Y-%m")
                    formatted_date = dt.strftime("%Y%m%d")
                    file_path = Path("outputs/reports") / month_str / f"mahsup_{formatted_date}.xlsx"
                    self._serve_excel(file_path)
                else:
                    self.send_error(400, "Geçersiz tarih formatı.")
                return

            if path.startswith("/api/settlement/download/monthly/"):
                month_str = path.replace("/api/settlement/download/monthly/", "").strip()
                if re.match(r"^\d{4}-\d{2}$", month_str):
                    year = int(month_str[:4])
                    month = int(month_str[5:7])
                    formatted_month = f"{year:04d}{month:02d}"
                    file_path = Path("outputs/reports") / month_str / f"mahsup_{formatted_month}_aylik.xlsx"
                    self._serve_excel(file_path)
                else:
                    self.send_error(400, "Geçersiz ay formatı.")
                return

        if path.startswith("/api/dev/"):
            self._handle_dev_api(path, query)
        elif path.startswith("/api/"):
            self._handle_api(path, query)
        else:
            self._handle_static(path)

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. /api/auth/login is anonymous
        if path == "/api/auth/login":
            self._handle_auth_login()
            return

        # 2. Developer endpoints use developer-specific auth
        if path.startswith("/api/dev/"):
            if path == "/api/dev/login":
                self._handle_dev_login()
            elif path == "/api/dev/logout":
                self._handle_dev_logout()
            elif path == "/api/dev/analyze-log":
                self._handle_dev_analyze_log()
            else:
                self._send_method_not_allowed()
            return

        # 3. All other POST requests require dashboard session token
        if path.startswith("/api/"):
            username = self._authenticate()
            if not username:
                return

            if path == "/api/auth/logout":
                self._handle_auth_logout(username)
            elif path in ("/api/settlement/trigger", "/api/settlement/trigger/daily"):
                self.auth.log_action(username, self._get_client_ip(), "settlement_trigger", details="Daily settlement manual trigger")
                self._handle_settlement_trigger(mode="daily")
            elif path == "/api/settlement/trigger/monthly":
                self.auth.log_action(username, self._get_client_ip(), "settlement_trigger", details="Monthly settlement manual trigger")
                self._handle_settlement_trigger(mode="monthly")
            elif path == "/api/settlement/trigger/daily-date":
                self.auth.log_action(username, self._get_client_ip(), "settlement_trigger", details="Daily settlement by date manual trigger")
                self._handle_settlement_trigger_daily_date()
            elif path == "/api/settlement/trigger/monthly-date":
                self.auth.log_action(username, self._get_client_ip(), "settlement_trigger", details="Monthly settlement by date manual trigger")
                self._handle_settlement_trigger_monthly_date()
            elif path == "/api/settings/smtp":
                self.auth.log_action(username, self._get_client_ip(), "settings_change", details="SMTP settings updated")
                self._handle_smtp_settings()
            elif path == "/api/settings/restart":
                self._handle_restart(username)
            elif path == "/api/gaosb/captcha-resolved":
                self.auth.log_action(username, self._get_client_ip(), "captcha_resolved", details="Captcha resolution submitted")
                self._handle_captcha_resolved()
            elif path == "/api/users":
                self._handle_users_create(username)
            elif path == "/api/users/change-password":
                self._handle_users_change_password(username)
            elif path == "/api/chat":
                self._handle_chat(username)
            else:
                self._send_method_not_allowed()
        else:
            self._send_not_found()

    def do_PUT(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/users/"):
            username = self._authenticate()
            if not username:
                return
            target_username = path.replace("/api/users/", "").strip()
            self._handle_users_update(username, target_username)
        else:
            self._send_method_not_allowed()

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/users/"):
            username = self._authenticate()
            if not username:
                return
            target_username = path.replace("/api/users/", "").strip()
            self._handle_users_delete(username, target_username)
        else:
            self._send_method_not_allowed()

    # ------------------------------------------------------------------
    # Excel (binary) sunumu
    # ------------------------------------------------------------------
    def _serve_excel(self, file_path: Optional[Path]) -> None:
        """
        Neden: Excel raporunu doğru Content-Type ve attachment başlığıyla,
        binary bozulmadan (rb) göndermek.
        """
        if file_path is None or not file_path.is_file():
            # Neden: send_error başlığı latin-1 kodlar; Türkçe karakter kullanılamaz.
            self.send_error(404, "Rapor dosyasi bulunamadi.")
            return
        try:
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            logger.error(f"Excel dosyası sunulamadı ({file_path}): {e}")
            self.send_error(500, "Dosya okuma hatasi.")

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------
    def _handle_api(self, path: str, query: Dict[str, list]) -> None:
        """
        Neden: REST API taleplerini karşılayarak standart JSON sözleşmesini dönmek.
        Yanıt önce hesaplanır, başlıklar sonra gönderilir (binary çakışması olmaz).
        """
        username = self._authenticate()
        if not username:
            return

        response_data = None
        error_message = None
        not_found = False

        try:
            if path == "/api/auth/me":
                db = SessionLocal()
                try:
                    user = db.query(DashboardUser).filter(DashboardUser.username == username).first()
                    if user:
                        response_data = {
                            "username": user.username,
                            "display_name": user.display_name,
                            "is_active": user.is_active,
                            "last_login": user.last_login.isoformat() if user.last_login else None
                        }
                    else:
                        error_message = "Kullanıcı bulunamadı."
                finally:
                    db.close()
            elif path == "/api/audit/logs":
                limit_val = min(int(query.get("limit", ["100"])[0]), 1000)
                user_filter = query.get("username", [""])[0].strip()
                action_filter = query.get("action", [""])[0].strip()
                success_filter = query.get("success", [""])[0].strip()
                
                db = SessionLocal()
                try:
                    q = db.query(AuditLog)
                    if user_filter:
                        q = q.filter(AuditLog.username.like(f"%{user_filter}%"))
                    if action_filter:
                        q = q.filter(AuditLog.action == action_filter)
                    if success_filter:
                        is_success = success_filter.lower() == "true"
                        q = q.filter(AuditLog.success == is_success)
                    
                    logs = q.order_by(AuditLog.timestamp.desc()).limit(limit_val).all()
                    response_data = [
                        {
                            "id": log.id,
                            "timestamp": log.timestamp.isoformat(),
                            "username": log.username,
                            "ip_address": log.ip_address,
                            "action": log.action,
                            "details": log.details,
                            "success": log.success
                        }
                        for log in logs
                    ]
                finally:
                    db.close()
            elif path == "/api/users":
                db = SessionLocal()
                try:
                    users = db.query(DashboardUser).order_by(DashboardUser.username).all()
                    response_data = [
                        {
                            "username": u.username,
                            "display_name": u.display_name,
                            "is_active": u.is_active,
                            "created_at": u.created_at.isoformat() if u.created_at else None,
                            "last_login": u.last_login.isoformat() if u.last_login else None
                        }
                        for u in users
                    ]
                finally:
                    db.close()
            elif path == "/api/kpis":
                response_data = self.service.get_executive_summary().to_dict()
            elif path == "/api/runs":
                response_data = [r.to_dict() for r in self.service.get_pipeline_history(limit=15)]
            elif path == "/api/health":
                response_data = self.service.get_health_status().to_dict()
            elif path == "/api/notifications":
                response_data = [n.to_dict() for n in self.service.get_notification_history(limit=15)]
            elif path == "/api/analytics/overview":
                response_data = self.analytics_service.get_overview().to_dict()
            elif path == "/api/analytics/daily":
                response_data = [d.to_dict() for d in self.analytics_service.get_daily_summary()]
            elif path == "/api/analytics/weekly":
                response_data = [w.to_dict() for w in self.analytics_service.get_weekly_summary()]
            elif path == "/api/analytics/monthly":
                response_data = [m.to_dict() for m in self.analytics_service.get_monthly_summary()]
            elif path == "/api/analytics/missing-days":
                response_data = [m.to_dict() for m in self.analytics_service.get_missing_days()]
            elif path == "/api/analytics/trend":
                response_data = self.analytics_service.get_trend().to_dict()

            # ---- Settlement DB endpoint'leri ----
            elif path == "/api/settlement/daily/latest":
                # Neden: "Son N gün" takvim aralığıdır (bugünden geriye N gün),
                # kayıt sayısı değil. Aralık dışındaki eski kayıtlar dönmez.
                days = min(max(int(query.get("days", ["7"])[0]), 1), 366)
                today = datetime.now().date()
                start_iso = (today - timedelta(days=days)).isoformat()
                end_iso = today.isoformat()
                rows = self.service.get_settlement_daily_list(limit=366)
                response_data = [r for r in rows if start_iso <= str(r.get("tarih", "")) <= end_iso]
            elif path == "/api/settlement/monthly/latest":
                limit = int(query.get("limit", ["3"])[0])
                response_data = self.service.get_settlement_monthly_list(limit=min(limit, 24))
            elif path.startswith("/api/settlement/hourly/"):
                date_str = path.replace("/api/settlement/hourly/", "").strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                    response_data = self.service.get_settlement_hourly(date_str)
                else:
                    error_message = "Geçersiz tarih formatı. Beklenen: YYYY-MM-DD"
            elif path == "/api/settlement/summary":
                response_data = self._summary_payload()
            elif path == "/api/settlement/month-to-date":
                response_data = self._month_to_date_payload()
            elif path == "/api/settlement/weekly":
                weeks = int(query.get("weeks", ["8"])[0])
                response_data = self._weekly_payload(weeks_limit=min(max(weeks, 1), 52))
            elif path == "/api/settlement/ges-distribution":
                days = int(query.get("days", ["30"])[0])
                response_data = self.service.get_plant_distribution(days=min(days, 366))
            elif path == "/api/gaosb/captcha-status":
                if CAPTCHA_FLAG_PATH.exists():
                    flag_info = {}
                    try:
                        # Neden: utf-8-sig — elle/PowerShell ile yazılmış BOM'lu dosyayı da okur.
                        flag_info = json.loads(CAPTCHA_FLAG_PATH.read_text(encoding="utf-8-sig"))
                    except Exception:
                        pass
                    response_data = {
                        "captcha_required": True,
                        "detected_at": flag_info.get("detected_at"),
                        "job_type": flag_info.get("job_type", "daily"),
                    }
                else:
                    response_data = {"captcha_required": False}
            elif path == "/api/settlement/reports/latest":
                response_data = {
                    "daily": _report_info(_find_latest_report(DAILY_REPORT_RE), "daily"),
                    "monthly": _report_info(_find_latest_report(MONTHLY_REPORT_RE), "monthly"),
                }
            elif path == "/api/settlement/latest":
                # Neden: Geriye dönük uyumluluk — eski arayüz sözleşmesi.
                response_data = _report_info(_find_latest_report(DAILY_REPORT_RE), "daily")

            elif path == "/api/plants/status":
                import re
                def clean_name(name):
                    match = re.search(r'ERDEMSOFT[- _]GES[_-](\d+)', name)
                    if match:
                        return f"ERDEMSOFT-GES-{match.group(1)}"
                    return name.strip()

                from app.database.plant_status_repository import PlantStatusRepository
                repo = PlantStatusRepository()
                records = repo.get_latest_status_records()
                
                # Clean and group by cleaned name, keeping the latest by timestamp
                latest_by_cleaned_name = {}
                for r in records:
                    cleaned = clean_name(r.plant_name)
                    existing = latest_by_cleaned_name.get(cleaned)
                    if not existing or (r.timestamp and existing.timestamp and r.timestamp > existing.timestamp):
                        latest_by_cleaned_name[cleaned] = r
                
                plants = []
                anomaly_count = 0
                last_check_dt = None
                
                # Sort plants by name for a consistent UI presentation
                for name in sorted(latest_by_cleaned_name.keys()):
                    r = latest_by_cleaned_name[name]
                    last_checked_str = r.timestamp.strftime("%H:%M") if r.timestamp else "-"
                    
                    status_tr = "Bilinmiyor"
                    if r.status == "Normal":
                        status_tr = "Normal"
                    elif r.status == "Abnormal":
                        status_tr = "HATA"
                    elif r.status == "Offline":
                        status_tr = "BAĞLANTI YOK"

                    plants.append({
                        "name": name,
                        "status": status_tr,
                        "last_checked": last_checked_str
                    })
                    if r.status != "Normal":
                        anomaly_count += 1
                    if r.timestamp:
                        if last_check_dt is None or r.timestamp > last_check_dt:
                            last_check_dt = r.timestamp
                
                last_check_str = last_check_dt.strftime("%d.%m.%Y %H:%M") if last_check_dt else "-"
                response_data = {
                    "plants": plants,
                    "last_check": last_check_str,
                    "anomaly_count": anomaly_count
                }

            elif path == "/api/plants/history":
                from app.database.plant_status_repository import PlantStatusRepository
                repo = PlantStatusRepository()
                plant_name = query.get("plant", [None])[0]
                hours_str = query.get("hours", ["24"])[0]
                try:
                    hours = int(hours_str)
                except ValueError:
                    hours = 24
                records = repo.get_status_history(plant_name=plant_name, hours=hours)
                response_data = [
                    {
                        "id": r.id,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                        "plant_name": r.plant_name,
                        "status": r.status,
                        "previous_status": r.previous_status,
                        "notified": r.notified,
                        "created_at": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in records
                ]

            elif path == "/api/settings":
                response_data = self._build_settings_payload()
            elif path.startswith("/api/metrics/"):
                metric_name = path.replace("/api/metrics/", "").strip()
                if metric_name:
                    response_data = self.service.get_metric_history(metric_name, limit=30).to_dict()
                else:
                    error_message = "Metrik adı belirtilmedi."
            else:
                not_found = True

        except Exception as e:
            logger.error(f"API hatası ({path}): {e}")
            error_message = "Sistem kaynağına şu anda erişilemiyor. Lütfen sistem yöneticinizle iletişime geçin."

        if not_found:
            # Neden: send_error başlığı latin-1 kodlar; Türkçe karakter kullanılamaz.
            self.send_error(404, "API endpoint bulunamadi.")
            return

        self._send_json_contract(response_data, error_message)

    # ------------------------------------------------------------------
    # Developer API
    # ------------------------------------------------------------------
    def _check_dev_token(self) -> bool:
        """Neden: X-Dev-Token header'ını doğrula; süresi geçmiş token'ları temizle."""
        token = self.headers.get("X-Dev-Token", "")
        if not token:
            return False
        issued = _DEV_TOKENS.get(token)
        if not issued:
            return False
        if datetime.utcnow() - issued > timedelta(hours=_DEV_TOKEN_TTL_HOURS):
            _DEV_TOKENS.pop(token, None)
            return False
        return True

    def _handle_dev_api(self, path: str, query: Dict[str, list]) -> None:
        """Neden: Developer log endpoint'lerini tek noktada yönetmek."""
        if path == "/api/dev/logs":
            if not self._check_dev_token():
                self._send_json_contract(None, "Yetkisiz erişim.", status_code=401)
                return
            level_filter = query.get("level", ["ALL"])[0].upper()
            limit = min(int(query.get("limit", ["200"])[0]), 2000)
            search = query.get("search", [""])[0].lower()
            file_name = query.get("file", ["app.log"])[0]
            logs_dir = Path(getattr(settings, "log_directory", Path("logs")))
            log_file = logs_dir / file_name
            entries = []
            pattern = re.compile(
                r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)\]\s+"
                r"\[([A-Z]+)\]\s+"
                r"\[([^:]+):([^:]+):(\d+)\]:\s+(.*)"
            )
            try:
                if log_file.exists():
                    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    for line in reversed(lines):
                        m = pattern.match(line.strip())
                        if m:
                            ts, lvl, module, fname, lineno, msg = m.groups()
                            if level_filter not in ("ALL", "") and lvl != level_filter:
                                continue
                            if search and search not in line.lower():
                                continue
                            entries.append({
                                "timestamp": ts,
                                "level": lvl,
                                "module": module,
                                "file": fname,
                                "line": int(lineno),
                                "message": msg,
                                "raw": line.strip(),
                            })
                            if len(entries) >= limit:
                                break
            except Exception as e:
                logger.error(f"Log dosyası okunamadı: {e}")
            stats = {"total": len(entries),
                     "error_count": sum(1 for e in entries if e["level"] == "ERROR"),
                     "warning_count": sum(1 for e in entries if e["level"] == "WARNING")}
            self._send_json_contract({"entries": entries, "stats": stats}, None)

        elif path == "/api/dev/logs/files":
            if not self._check_dev_token():
                self._send_json_contract(None, "Yetkisiz erişim.", status_code=401)
                return
            logs_dir = Path(getattr(settings, "log_directory", Path("logs")))
            files = []
            if logs_dir.exists():
                for f in sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
                    files.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)})
            self._send_json_contract({"files": files}, None)
        else:
            self.send_error(404, "Dev endpoint bulunamadi.")

    def _handle_dev_login(self) -> None:
        """Neden: Şifre doğrulayıp kısa ömürlü token üret."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send_json_contract(None, "Geçersiz istek gövdesi.", status_code=400)
            return
        from dotenv import load_dotenv
        load_dotenv()
        dev_password = os.environ.get("DEVELOPER_PASSWORD", "")
        if not dev_password or body.get("password") != dev_password:
            self._send_json_contract(None, "Hatalı şifre.", status_code=401)
            return
        token = str(uuid.uuid4())
        _DEV_TOKENS[token] = datetime.utcnow()
        self._send_json_contract({"token": token}, None)

    def _handle_dev_logout(self) -> None:
        """Neden: Token'ı bellekten silerek oturumu kapat."""
        token = self.headers.get("X-Dev-Token", "")
        _DEV_TOKENS.pop(token, None)
        self._send_json_contract({"ok": True}, None)

    def _handle_dev_analyze_log(self) -> None:
        """Neden: Gelen log kaydını LogAnalyzer ile analiz edip sonucu döndür."""
        if not self._check_dev_token():
            self._send_json_contract(None, "Yetkisiz erişim.", status_code=401)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            log_entry = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send_json_contract(None, "Geçersiz istek gövdesi.", status_code=400)
            return
        try:
            from app.ai.log_analyzer import LogAnalyzer
            analyzer = LogAnalyzer()
            result = analyzer.analyze(log_entry)
            if result:
                self._send_json_contract(result, None)
            else:
                self._send_json_contract(
                    {"source": "none", "cause": "Bu seviyede otomatik analiz yapılmıyor.",
                     "solution": "-", "severity": "info"}, None
                )
        except Exception as e:
            logger.error(f"Log analizi hatası: {e}")
            self._send_json_contract(None, "Analiz sırasında hata oluştu.")

    def _summary_payload(self) -> Dict[str, Any]:
        """
        Neden: Ana sayfa KPI kartlarını beslemek.
        - bugun: dünün (today-1) settlement_daily kaydı; günlük job dünü hesaplar.
          Dünün kaydı henüz yoksa en güncel kayıt gösterilir (boş kart yerine).
        - bu_ay: ayın 1'inden bugüne settlement_daily TOPLAMI (ay içi durum).
        - son_guncelleme: en son kayıt tarihi.
        """
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        rows = self.service.get_settlement_daily_list(limit=366)

        empty = {"tarih": None, "uretim": 0, "tuketim": 0, "mahsup": 0, "cekis": 0, "satis": 0}
        bugun = next((r for r in rows if str(r.get("tarih")) == yesterday.isoformat()), None)
        if bugun is None:
            bugun = rows[0] if rows else empty

        mtd = self._month_to_date_payload()
        bu_ay = {key: mtd[key] for key in ("donem", "uretim", "tuketim", "mahsup", "cekis", "satis")}

        last_date = max((str(r["tarih"]) for r in rows), default=None)
        return {"bugun": bugun, "bu_ay": bu_ay, "son_guncelleme": last_date}

    def _month_to_date_payload(self) -> Dict[str, Any]:
        """
        Neden: Ana sayfadaki 'Bu Ay Özeti' kartını beslemek — içinde bulunulan
        ayın 1'inden bugüne kadar olan settlement_daily kayıtlarının toplamı.
        """
        today = datetime.now().date()
        prefix = f"{today.year:04d}-{today.month:02d}"
        # Neden: En güncel 31 gün, içinde bulunulan ayın tamamını kapsar.
        rows = self.service.get_settlement_daily_list(limit=31)
        month_rows = [r for r in rows if str(r.get("tarih", "")).startswith(prefix)]

        totals = {
            key: round(sum(r.get(key) or 0.0 for r in month_rows), 1)
            for key in ("uretim", "tuketim", "mahsup", "cekis", "satis")
        }
        days = sorted(str(r["tarih"]) for r in month_rows)
        return {
            "yil": today.year,
            "ay": today.month,
            "donem": prefix,
            "baslangic": days[0] if days else f"{prefix}-01",
            "bitis": days[-1] if days else None,
            "gun_sayisi": len(month_rows),
            **totals,
        }

    def _weekly_payload(self, weeks_limit: int = 8) -> list:
        """
        Neden: Analitik sayfasındaki haftalık üretim/tüketim grafiğini beslemek.
        settlement_daily kayıtları pazartesi başlangıçlı haftalara gruplanır.
        """
        rows = self.service.get_settlement_daily_list(limit=366)
        buckets: Dict[Any, Dict[str, float]] = {}
        for r in rows:
            try:
                day = datetime.strptime(str(r["tarih"]), "%Y-%m-%d").date()
            except (KeyError, ValueError):
                continue
            monday = day - timedelta(days=day.weekday())
            bucket = buckets.setdefault(
                monday,
                {"uretim": 0.0, "tuketim": 0.0, "mahsup": 0.0, "cekis": 0.0, "satis": 0.0, "gun_sayisi": 0},
            )
            for key in ("uretim", "tuketim", "mahsup", "cekis", "satis"):
                bucket[key] += r.get(key) or 0.0
            bucket["gun_sayisi"] += 1

        result = []
        for monday in sorted(buckets)[-weeks_limit:]:
            bucket = buckets[monday]
            result.append({
                "hafta": monday.isoformat(),
                "hafta_etiketi": f"{monday.strftime('%d.%m')} haftası",
                "gun_sayisi": bucket["gun_sayisi"],
                **{key: round(bucket[key], 1)
                   for key in ("uretim", "tuketim", "mahsup", "cekis", "satis")},
            })
        return result

    def _build_settings_payload(self) -> Dict[str, Any]:
        """Neden: Sistem durumu/ayar bilgilerini tek payload'da toplamak."""
        from app.sources import SourceRegistry
        from app.database.db_session import SessionLocal
        from app.database.models import NotificationHistory, EtlRun

        registry = SourceRegistry()

        if not settings.smtp_enabled:
            smtp_status = "pasif"
        elif not (settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.alert_email):
            smtp_status = "eksik"
        else:
            smtp_status = "aktif"

        last_mail_status = "GÖNDERİLMEDİ"
        last_mail_error = None
        last_run_time = None
        db_session = SessionLocal()
        try:
            last_notif = db_session.query(NotificationHistory).order_by(NotificationHistory.id.desc()).first()
            if last_notif:
                last_mail_status = last_notif.status
                last_mail_error = last_notif.error_message
            last_run = db_session.query(EtlRun).order_by(EtlRun.started_at.desc()).first()
            if last_run and last_run.started_at:
                last_run_time = last_run.started_at.isoformat()
        except Exception:
            pass
        finally:
            db_session.close()

        # Neden: Settlement job'ları EtlRun'a yazmaz; en güncel mahsup kaydı da
        # 'son çalışma' göstergesi olarak kullanılır.
        settlement_update = self.service.repository.get_settlement_last_update()
        if settlement_update:
            if not last_run_time or settlement_update.isoformat() > last_run_time:
                last_run_time = settlement_update.isoformat()

        # GAOSB durumu: config/sources.json'da tanımlıysa veya kimlik bilgileri
        # yapılandırılmışsa (fiilen kullanılıyor) AKTİF kabul edilir.
        gaosb_status = "PASİF"
        try:
            sources_file = BASE_DIR / "config" / "sources.json"
            if sources_file.exists():
                sources_cfg = json.loads(sources_file.read_text(encoding="utf-8"))
                if "gaosb" in sources_cfg.get("sources", {}):
                    gaosb_status = "AKTİF"
        except Exception:
            pass
        if gaosb_status == "PASİF" and os.environ.get("GAOSB_USERNAME"):
            gaosb_status = "AKTİF"

        isolar_status = "AKTİF" if "isolarcloud" in registry.list_sources() else "PASİF"

        git_commit = "-"
        try:
            import subprocess
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode().strip()
        except Exception:
            pass

        return {
            "dashboard_port": settings.dashboard_port,
            "dashboard_access_mode": settings.dashboard_access_mode,
            "active_source": registry.default_source(),
            "registered_sources": registry.list_sources(),
            "app_env": settings.app_env,
            "log_level": settings.log_level,
            "smtp_status": smtp_status,
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "smtp_username": settings.smtp_username,
            "smtp_password_masked": "********" if settings.smtp_password else "",
            "smtp_to": settings.alert_email,
            "smtp_to_daily": settings.smtp_to_daily,
            "smtp_to_monthly": settings.smtp_to_monthly,
            "smtp_to_plant_alert": settings.smtp_to_plant_alert,
            "smtp_to_system": settings.smtp_to_system,
            "smtp_last_status": last_mail_status,
            "smtp_last_error": last_mail_error,
            "backup_retention_days": 14,
            "isolar_status": isolar_status,
            "gaosb_status": gaosb_status,
            "gaosb_url": "elk.gaosb.org",
            "last_run_time": last_run_time,
            "version": "v1.1.0",
            "git_commit": git_commit,
            "schedules": [
                {"name": "Günlük Mahsuplaşma", "zamanlama": "Her gün 09:00"},
                {"name": "Aylık Mahsuplaşma", "zamanlama": "Her ayın 1'i 08:30"},
            ],
        }

    # ------------------------------------------------------------------
    # POST işleyicileri
    # ------------------------------------------------------------------
    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_auth_login(self) -> None:
        body = self._read_json_body()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        ip = self._get_client_ip()
        
        logger.info(f"Login attempt: username='{username}', password_len={len(password)}, ip={ip}")
        
        if not username or not password:
            self.auth.log_action(username or "unknown", ip, "login_failed", details="Missing username or password", success=False)
            self._send_json_contract(None, "Kullanıcı adı ve şifre gereklidir.", status_code=400)
            return
            
        success = self.auth.verify_user(username, password)
        if success:
            token = self.auth.create_session(username, ip)
            display_name = username
            db = SessionLocal()
            try:
                user = db.query(DashboardUser).filter(DashboardUser.username == username).first()
                if user:
                    display_name = user.display_name
            finally:
                db.close()
                
            self.auth.log_action(username, ip, "login_success", details="Successful login")
            self._send_json_contract({
                "token": token,
                "display_name": display_name,
                "expires_in": 28800
            }, None)
        else:
            self.auth.log_action(username, ip, "login_failed", details="Invalid credentials", success=False)
            self._send_json_contract(None, "Hatalı kullanıcı adı veya şifre.", status_code=401)

    def _handle_auth_logout(self, username: str) -> None:
        token = self._get_auth_token()
        if token:
            self.auth.destroy_session(token)
            self.auth.log_action(username, self._get_client_ip(), "logout", details="User logged out")
            self._send_json_contract({"ok": True}, None)
        else:
            self._send_json_contract(None, "Token bulunamadı.", status_code=400)

    def _handle_users_create(self, current_username: str) -> None:
        body = self._read_json_body()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        display_name = body.get("display_name", "").strip()

        if not username or not password or not display_name:
            self._send_json_contract(None, "Tüm alanlar (Kullanıcı adı, Şifre, Ad Soyad) zorunludur.", status_code=400)
            return

        success = self.auth.create_user(username, password, display_name, update_if_exists=False)
        if success:
            self.auth.log_action(current_username, self._get_client_ip(), "user_create", details=f"Yeni kullanıcı oluşturuldu: '{username}'")
            self._send_json_contract({"username": username}, None)
        else:
            self._send_json_contract(None, "Kullanıcı oluşturulamadı. Kullanıcı adı zaten mevcut olabilir.", status_code=400)

    def _handle_users_change_password(self, current_username: str) -> None:
        body = self._read_json_body()
        old_password = body.get("old_password", "")
        new_password = body.get("new_password", "")

        if not old_password or not new_password:
            self._send_json_contract(None, "Mevcut şifre ve yeni şifre alanları zorunludur.", status_code=400)
            return

        success = self.auth.change_password(current_username, old_password, new_password)
        if success:
            self.auth.log_action(current_username, self._get_client_ip(), "password_change", details="Kullanıcı kendi şifresini değiştirdi")
            self._send_json_contract({"ok": True}, None)
        else:
            self._send_json_contract(None, "Mevcut şifre hatalı veya şifre değiştirilemedi.", status_code=400)

    def _handle_users_update(self, current_username: str, target_username: str) -> None:
        body = self._read_json_body()
        display_name = body.get("display_name", "").strip()
        is_active = body.get("is_active", True)
        password = body.get("password", "")  # Optional

        if not display_name:
            self._send_json_contract(None, "Ad Soyad alanı boş bırakılamaz.", status_code=400)
            return

        # Audit kaydı update_user içinde atılır (başarısız denemeler dahil)
        success = self.auth.update_user(target_username, display_name, is_active, password if password else None,
                                        actor=current_username, ip=self._get_client_ip())
        if success:
            self._send_json_contract({"username": target_username}, None)
        else:
            self._send_json_contract(None, "Kullanıcı güncellenemedi.", status_code=400)

    def _handle_users_delete(self, current_username: str, target_username: str) -> None:
        if current_username == target_username:
            self._send_json_contract(None, "Kendi kullanıcınızı silemezsiniz.", status_code=400)
            return

        # Audit kaydı delete_user içinde atılır (başarısız denemeler dahil)
        success = self.auth.delete_user(target_username, actor=current_username, ip=self._get_client_ip())
        if success:
            self._send_json_contract({"ok": True}, None)
        else:
            self._send_json_contract(None, "Kullanıcı silinemedi veya bulunamadı.", status_code=400)

    def _handle_settlement_trigger(self, mode: str) -> None:
        """
        Neden: Manuel mahsuplaşma tetikleme isteğini (günlük/aylık) karşılamak.
        İşlem eşzamanlıdır; tamamlanınca rapor yolu ve indirme adresi döner.
        """
        logger.warning(f"Manuel mahsuplaşma tetiklendi (mode={mode}).")
        # Neden: Dashboard'dan tetiklenen job'larda iSolar tarayıcısı kullanıcıya
        # görünmemeli. Job'lar settings.headless (ISOLAR_HEADLESS) değerini okur;
        # yanlış yapılandırma erken fark edilsin diye burada doğrulanır.
        # Not: GAOSB persistent context'i BotGuard nedeniyle tasarım gereği her
        # zaman görünür (headless=False) çalışır; bu davranış job'a aittir.
        if not settings.headless:
            logger.warning(
                "ISOLAR_HEADLESS=false: iSolar tarayıcısı görünür modda açılacak. "
                "Dashboard tetiklemelerinde arka plan çalışması için .env'de ISOLAR_HEADLESS=true olmalı."
            )
        error_message = None
        response_data = None

        try:
            if mode == "monthly":
                from app.jobs.monthly_settlement_job import MonthlySettlementJob
                result = _run_in_clean_thread(lambda: MonthlySettlementJob().run(target_month=None))
                result["download_url"] = "/api/settlement/download/latest/monthly"
            else:
                from app.jobs.daily_settlement_job import DailySettlementJob
                result = _run_in_clean_thread(lambda: DailySettlementJob().run(target_date=None))
                result["download_url"] = "/api/settlement/download/latest/daily"
            response_data = result
        except Exception as e:
            logger.error(f"Manuel mahsuplaşma tetikleme hatası ({mode}): {e}")
            error_message = "Mahsuplaşma işlemi tamamlanamadı. Lütfen daha sonra tekrar deneyin."

        self._send_json_contract(response_data, error_message)

    def _handle_settlement_trigger_daily_date(self) -> None:
        body = self._read_json_body()
        date_str = body.get("date")
        if not date_str or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            self._send_json_contract(None, "Geçersiz tarih formatı. Beklenen: YYYY-MM-DD")
            return
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            self._send_json_contract(None, "Geçersiz tarih.")
            return

        today = datetime.now().date()
        if target_date >= today:
            self._send_json_contract(None, "Tarih geçmişte olmalıdır.")
            return

        two_years_ago = today - timedelta(days=365*2)
        if target_date < two_years_ago:
            self._send_json_contract(None, "Tarih en fazla 2 yıl geriye ait olabilir.")
            return

        error_message = None
        response_data = None
        try:
            from app.database.settlement_repository import SettlementRepository
            repo = SettlementRepository()
            has_db = repo.has_daily_data(date_str)
            report_path = repo.get_daily_report_path(date_str)

            if has_db and report_path:
                response_data = {
                    "status": "cached",
                    "report_path": report_path,
                    "download_url": f"/api/settlement/download/daily/{date_str}"
                }
            else:
                from app.jobs.daily_settlement_job import DailySettlementJob
                result = _run_in_clean_thread(lambda: DailySettlementJob().run(target_date=date_str))
                if result.get("status") == "SUCCESS":
                    result["download_url"] = f"/api/settlement/download/daily/{date_str}"
                response_data = result
        except Exception as e:
            logger.error(f"Geçmiş günlük mahsuplaşma tetikleme hatası ({date_str}): {e}")
            error_message = "Mahsuplaşma işlemi tamamlanamadı. Lütfen daha sonra tekrar deneyin."

        self._send_json_contract(response_data, error_message)

    def _handle_settlement_trigger_monthly_date(self) -> None:
        body = self._read_json_body()
        month_str = body.get("month")
        if not month_str or not re.match(r"^\d{4}-\d{2}$", month_str):
            self._send_json_contract(None, "Geçersiz ay formatı. Beklenen: YYYY-MM")
            return
        try:
            dt = datetime.strptime(month_str, "%Y-%m")
            year = dt.year
            month = dt.month
        except ValueError:
            self._send_json_contract(None, "Geçersiz ay.")
            return

        today = datetime.now().date()
        first_of_this_month = today.replace(day=1)
        target_first_day = dt.date()

        if target_first_day >= first_of_this_month:
            self._send_json_contract(None, "Ay bu aydan önce olmalıdır.")
            return

        try:
            two_years_ago_first_day = first_of_this_month.replace(year=first_of_this_month.year - 2)
        except ValueError:
            two_years_ago_first_day = first_of_this_month - timedelta(days=365*2)
            two_years_ago_first_day = two_years_ago_first_day.replace(day=1)

        if target_first_day < two_years_ago_first_day:
            self._send_json_contract(None, "Ay en fazla 2 yıl geriye ait olabilir.")
            return

        error_message = None
        response_data = None
        try:
            from app.database.settlement_repository import SettlementRepository
            repo = SettlementRepository()
            has_db = repo.has_monthly_data(year, month)
            report_path = repo.get_monthly_report_path(year, month)

            if has_db and report_path:
                response_data = {
                    "status": "cached",
                    "report_path": report_path,
                    "download_url": f"/api/settlement/download/monthly/{month_str}"
                }
            else:
                from app.jobs.monthly_settlement_job import MonthlySettlementJob
                result = _run_in_clean_thread(lambda: MonthlySettlementJob().run(target_month=month_str))
                if result.get("status") == "SUCCESS":
                    result["download_url"] = f"/api/settlement/download/monthly/{month_str}"
                response_data = result
        except Exception as e:
            logger.error(f"Geçmiş aylık mahsuplaşma tetikleme hatası ({month_str}): {e}")
            error_message = "Mahsuplaşma işlemi tamamlanamadı. Lütfen daha sonra tekrar deneyin."

        self._send_json_contract(response_data, error_message)


    def _handle_captcha_resolved(self) -> None:
        """
        Neden: Kullanıcı GAOSB doğrulamasını tamamladığını bildirdiğinde flag durumunu 
        'resolving' yapar, GaosbExtractor.renew_session() ile Playwright oturumunu yeniler.
        Başarılı olursa flag silinir ve duraklatılan job çalıştırılıp sonucu döner.
        Başarısız olursa flag silinmez ve hata dönülür.
        """
        flag_info = {}
        if CAPTCHA_FLAG_PATH.exists():
            try:
                flag_info = json.loads(CAPTCHA_FLAG_PATH.read_text(encoding="utf-8-sig"))
            except Exception:
                pass

        flag_info["status"] = "resolving"
        try:
            CAPTCHA_FLAG_PATH.write_text(json.dumps(flag_info), encoding="utf-8")
        except Exception as e:
            logger.error(f"Captcha flag resolving olarak güncellenemedi: {e}")

        # 2. GaosbExtractor().renew_session() çalıştır
        from app.sources.gaosb.extractor import GaosbExtractor
        success = _run_in_clean_thread(lambda: GaosbExtractor().renew_session())

        if not success:
            # Revert flag status to pending so banner remains
            flag_info["status"] = "pending"
            try:
                CAPTCHA_FLAG_PATH.write_text(json.dumps(flag_info), encoding="utf-8")
            except Exception:
                pass
            self._send_json_contract(None, "Session yenilenemedi, lütfen tekrar deneyin.")
            return

        # 3. Session başarılıysa flag'i sil
        try:
            if CAPTCHA_FLAG_PATH.exists():
                CAPTCHA_FLAG_PATH.unlink()
        except Exception as e:
            logger.error(f"Captcha flag dosyası silinemedi: {e}")

        # 4. DailySettlementJob veya MonthlySettlementJob çalıştır
        job_type = flag_info.get("job_type", "daily")
        target = flag_info.get("target")
        logger.warning(f"Captcha doğrulaması tamamlandı bildirimi alındı; {job_type} job yeniden çalıştırılıyor (target={target}).")

        error_message = None
        response_data = None
        try:
            if job_type == "monthly":
                from app.jobs.monthly_settlement_job import MonthlySettlementJob
                result = _run_in_clean_thread(lambda: MonthlySettlementJob().run(target_month=target))
                if target:
                    result["download_url"] = f"/api/settlement/download/monthly/{target}"
                else:
                    result["download_url"] = "/api/settlement/download/latest/monthly"
            else:
                from app.jobs.daily_settlement_job import DailySettlementJob
                result = _run_in_clean_thread(lambda: DailySettlementJob().run(target_date=target))
                if target:
                    result["download_url"] = f"/api/settlement/download/daily/{target}"
                else:
                    result["download_url"] = "/api/settlement/download/latest/daily"

            if result.get("status") == "CAPTCHA_REQUIRED":
                error_message = ("GAOSB doğrulaması henüz tamamlanmamış görünüyor. "
                                 "Lütfen portalda doğrulamayı bitirip tekrar deneyin.")
            else:
                response_data = result
        except Exception as e:
            logger.error(f"Captcha sonrası job yeniden çalıştırma hatası ({job_type}): {e}")
            error_message = "Rapor yeniden hazırlanamadı. Lütfen daha sonra tekrar deneyin."

        self._send_json_contract(response_data, error_message)

    def _handle_chat(self, username: str) -> None:
        body = self._read_json_body()
        message = body.get("message", "").strip()
        
        # Denetim günlüğüne kaydet (audit logs)
        self.auth.log_action(username, self._get_client_ip(), "chat_query", details=message[:100])
        
        if not message:
            self._send_json_contract({"response": "Lütfen bir mesaj yazın.", "data": {}}, None)
            return
            
        try:
            from app.chatbot import DateParser, MetricParser, QueryEngine, ResponseBuilder, IntentParser

            date_parser = DateParser()
            metric_parser = MetricParser()
            query_engine = QueryEngine()
            response_builder = ResponseBuilder()

            # 1. Niyet sınıflandırması: veri sorgusu olmayan durumlarda yönlendir.
            intent = IntentParser().classify(message)
            kind = intent["kind"]
            if kind == "greeting":
                self._send_json_contract({"response": response_builder.greeting(), "data": {}}, None)
                return
            if kind == "help":
                self._send_json_contract({"response": response_builder.help_menu(), "data": {}}, None)
                return
            if kind == "comparison_diff":
                self._send_json_contract({"response": response_builder.comparison_guidance(), "data": {}}, None)
                return

            # 2. Veri sorgusu akışı
            try:
                date_info = date_parser.parse(message)
            except ValueError:
                response_text = "⚠️ Gelecek tarihli veriler hakkında bilgi veremiyorum. Lütfen geçmiş veya bugüne dair bir soru sorun."
                self._send_json_contract({"response": response_text, "data": {}}, None)
                return

            metric_info = metric_parser.parse(message)

            # Tarih anlaşılmadı: metrik/santral belirtilmişse makul varsayılan (dün) + ipucu,
            # hiçbir sinyal yoksa yönlendir.
            hint = ""
            if date_info is None:
                if metric_info["explicit"] or intent["has_plant"]:
                    date_info = date_parser.yesterday()
                    # İpucu yalnızca dönem-bazlı düz metrik sorgusunda anlamlı;
                    # santral durumu ve en çok/en az sorgularında gösterilmez.
                    if "plant_status" not in metric_info["metrics"] and not metric_info["comparison"]:
                        hint = "\n\n💡 Belirli bir dönem için 'bu ay ...' veya 'geçen ay ...' diyebilirsiniz."
                else:
                    self._send_json_contract({"response": response_builder._unrecognized_response(), "data": {}}, None)
                    return

            query_result = query_engine.query(date_info, metric_info)
            response_text = response_builder.build(message, date_info, metric_info, query_result.get("data", {})) + hint

            self._send_json_contract({
                "response": response_text,
                "data": query_result.get("data", {})
            }, None)
        except Exception as e:
            logger.error(f"Chatbot endpoint hatası: {e}")
            self._send_json_contract({"response": "Sistem şu anda yanıt veremiyor.", "data": {}}, None)

    def _handle_smtp_settings(self) -> None:
        """
        Neden: Mail ayarlarını dashboard üzerinden, yönetici şifresi doğrulamasıyla
        güncellemek. Şifre DASHBOARD_ADMIN_PASSWORD ortam değişkeniyle karşılaştırılır
        ve değerler .env dosyasına yazılır.
        """
        body = self._read_json_body()
        admin_password = str(body.get("admin_password", ""))
        expected = os.environ.get("DASHBOARD_ADMIN_PASSWORD", "")

        if not expected or admin_password != expected:
            logger.warning("SMTP ayar güncellemesi reddedildi: yönetici şifresi hatalı.")
            self._send_json_contract(None, "Yönetici şifresi hatalı.")
            return

        updates = {}

        # 1. Profil Alıcıları
        profile_map = {
            "daily": "SMTP_TO_DAILY",
            "monthly": "SMTP_TO_MONTHLY",
            "plant_alert": "SMTP_TO_PLANT_ALERT",
            "system": "SMTP_TO_SYSTEM"
        }
        for prof_key, env_key in profile_map.items():
            prof_data = body.get(prof_key)
            if isinstance(prof_data, dict):
                to_val = prof_data.get("to")
                if to_val is not None:
                    updates[env_key] = str(to_val).strip()

        # 2. Genel SMTP Ayarları — port zorunlu ve sayısal; diğer boş alanlar "değiştirme" demektir.
        # Boş string .env'e yazılırsa config.py restart sonrası varsayılana düşemez (get()
        # varsayılanı yalnızca anahtar yokken kullanır), bu yüzden boş değer asla yazılmaz.
        smtp_data = body.get("smtp")
        if isinstance(smtp_data, dict):
            port_raw = smtp_data.get("port")
            if port_raw is not None:
                port_str = str(port_raw).strip()
                if port_str == "":
                    self._send_json_contract(None, "Port boş olamaz.")
                    return
                if not port_str.isdigit() or not (1 <= int(port_str) <= 65535):
                    self._send_json_contract(None, "Port 1-65535 arasında bir sayı olmalıdır.")
                    return
                updates["SMTP_PORT"] = port_str
            smtp_key_map = {
                "host": "SMTP_HOST",
                "username": "SMTP_USERNAME",
                "password": "SMTP_PASSWORD",
            }
            for smtp_key, env_key in smtp_key_map.items():
                val = smtp_data.get(smtp_key)
                if val is not None and str(val).strip() != "":
                    updates[env_key] = str(val).strip()

        # 3. Geriye Dönük Düz JSON Desteği
        env_key_map = {
            "smtp_host": "SMTP_HOST",
            "smtp_port": "SMTP_PORT",
            "smtp_username": "SMTP_USERNAME",
            "smtp_password": "SMTP_PASSWORD",
            "smtp_to": "SMTP_TO",
        }
        for body_key, env_key in env_key_map.items():
            value = body.get(body_key)
            if value is not None and str(value).strip() != "":
                updates[env_key] = str(value).strip()

        if not updates:
            self._send_json_contract(None, "Güncellenecek geçerli bir alan gönderilmedi.")
            return

        try:
            env_path = BASE_DIR / ".env"
            lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
            remaining = dict(updates)
            new_lines = []
            for line in lines:
                stripped = line.strip()
                key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else None
                if key in remaining:
                    new_lines.append(f"{key}={remaining.pop(key)}")
                else:
                    new_lines.append(line)
            for key, value in remaining.items():
                new_lines.append(f"{key}={value}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

            # Çalışan süreç ortamını güncelle
            for key, value in updates.items():
                os.environ[key] = value

            logger.info(f"SMTP ayarları güncellendi: {sorted(updates.keys())}")
            self._send_json_contract({
                "updated_keys": sorted(updates.keys()),
                "note": "Ayarlar kaydedildi. Bu ayarların etkili olması için dashboard'ın yeniden başlatılması gerekir — uygulama yapılandırmayı yalnızca başlangıçta yükler.",
            }, None)
        except Exception as e:
            logger.error(f"SMTP ayarları .env dosyasına yazılamadı: {e}")
            self._send_json_contract(None, "Ayarlar kaydedilemedi. Lütfen sistem yöneticinizle iletişime geçin.")

    def _handle_restart(self, username: str) -> None:
        """
        Neden: .env tabanlı ayarlar frozen settings nesnesine yalnızca process
        başlangıcında yüklenir; bu endpoint dashboard'ı kontrollü olarak yeniden
        başlatır. Yanıt gönderildikten sonra process RESTART_EXIT_CODE ile sonlanır,
        gizli VBS başlatıcısındaki döngü taze konfigürasyonla hemen geri getirir.
        Yönetici şifresi zorunludur; kabul ve ret audit_log'a yazılır.
        """
        body = self._read_json_body()
        admin_password = str(body.get("admin_password", ""))
        expected = os.environ.get("DASHBOARD_ADMIN_PASSWORD", "")

        if not expected or admin_password != expected:
            self.auth.log_action(username, self._get_client_ip(), "dashboard_restart_denied", details="Yönetici şifresi hatalı")
            logger.warning("Dashboard yeniden başlatma isteği reddedildi: yönetici şifresi hatalı.")
            self._send_json_contract(None, "Yönetici şifresi hatalı.")
            return

        self.auth.log_action(username, self._get_client_ip(), "dashboard_restart", details="Ayarların etkinleşmesi için kontrollü yeniden başlatma")
        logger.info(f"Dashboard kontrollü yeniden başlatılıyor (istek: {username}); VBS başlatıcı taze config ile geri getirecek.")
        self._send_json_contract({
            "restarting": True,
            "note": "Dashboard yeniden başlatılıyor; birkaç saniye içinde tekrar erişilebilir olacak.",
        }, None)
        _schedule_restart()

    # ------------------------------------------------------------------
    # Ortak yanıt yardımcıları
    # ------------------------------------------------------------------
    def _send_json_contract(self, response_data, error_message, status_code: int = 200) -> None:
        contract = {
            "success": error_message is None,
            "data": response_data,
            "error": error_message,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": settings.app_env,
                "version": "v1.1.0",
            },
        }
        payload = json.dumps(contract, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _handle_static(self, path: str) -> None:
        """
        Neden: HTML/CSS/JS ve grafik dosyalarını güvenli şekilde sunmak (Path Traversal engelleme).
        """
        rel_path = path
        if rel_path.startswith("/static/"):
            rel_path = rel_path.replace("/static/", "", 1)

        if rel_path == "/" or rel_path == "":
            rel_path = "/index.html"

        requested_file = (self.static_dir / rel_path.lstrip("/")).resolve()

        if not requested_file.is_relative_to(self.static_dir) or not requested_file.is_file():
            self._send_not_found()
            return

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
            self.send_error(500, "Dosya okuma hatasi.")

    def _send_method_not_allowed(self) -> None:
        self._send_json_contract(None, "HTTP metodu desteklenmiyor.", status_code=405)

    def _send_not_found(self) -> None:
        self._send_json_contract(None, "İstenen kaynak bulunamadı.", status_code=404)

    # Log çıktılarının kirlenmesini önlemek için standard log metodunu ez
    def log_message(self, format, *args):
        logger.debug(f"{self.address_string()} - {format%args}")


class SolarDashboardServer:
    """
    Neden: Dashboard web sunucusunu nesne yönelimli olarak temsil etmek ve yönetmek.
    """
    def __init__(self, port: int = None):
        self.port = port
        self.httpd = None

    def start(self) -> None:
        """
        Neden: Dashboard web sunucusunu başlatmak ve serve_forever ile açık tutmak.
        """
        if self.port is None:
            self.port = settings.dashboard_port

        access_mode = settings.dashboard_access_mode
        host = "0.0.0.0" if access_mode == "network" else "127.0.0.1"

        server_address = (host, self.port)
        try:
            self.httpd = _ExclusiveHTTPServer(server_address, DashboardRequestHandler)
        except OSError as e:
            logger.error(
                f"Port {self.port} bağlanamadı — büyük olasılıkla başka bir dashboard "
                f"instance'ı zaten çalışıyor (elle başlatılmış olabilir): {e}"
            )
            raise

        logger.info(f"Dashboard Web Server BAŞLATILDI: http://{host if host != '0.0.0.0' else 'localhost'}:{self.port} (Mod: {access_mode})")
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Dashboard Web Server durduruluyor...")
        finally:
            self.httpd.server_close()
            logger.info("Dashboard Web Server kapatıldı.")


def start_dashboard_server(port: int = None) -> None:
    """
    Neden: Dashboard web sunucusunu yapılandırmaya göre localhost veya network binding ile ayağa kaldırmak.
    """
    server = SolarDashboardServer(port=port)
    server.start()

if __name__ == "__main__":
    start_dashboard_server()

