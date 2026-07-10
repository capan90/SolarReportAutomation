import os
import re
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings, BASE_DIR
from app.core.logger import setup_logger
from app.dashboard.service import DashboardService
from app.analytics.service import AnalyticsService

logger = setup_logger("DashboardWebServer")

REPORTS_DIR = Path("outputs/reports")
# Neden: Günlük rapor 'mahsup_YYYYMMDD.xlsx', aylık rapor 'mahsup_YYYYMM_aylik.xlsx'
# adlandırmasını kullanır; en güncel dosya isimdeki rakamlara göre seçilir.
DAILY_REPORT_RE = re.compile(r"^mahsup_(\d{8})\.xlsx$")
MONTHLY_REPORT_RE = re.compile(r"^mahsup_(\d{6})_aylik\.xlsx$")

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


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    Neden: Dashboard API endpoint'lerini ve statik dosyaları (HTML/CSS/JS)
    sıfır dış bağımlılıkla sunmak. Veri kaynağı settlement DB tablolarıdır.
    """
    service = DashboardService()
    analytics_service = AnalyticsService()
    static_dir = Path(__file__).resolve().parent / "static"

    # ------------------------------------------------------------------
    # HTTP metod yönlendirmeleri
    # ------------------------------------------------------------------
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # Neden: Binary (Excel) indirme endpoint'leri JSON sözleşmesinden ÖNCE ele
        # alınmalı; aksi halde çift başlık gönderimi dosyayı bozar (eski hata buydu).
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


        if path.startswith("/api/"):
            self._handle_api(path, query)
        else:
            self._handle_static(path)

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        if path in ("/api/settlement/trigger", "/api/settlement/trigger/daily"):
            self._handle_settlement_trigger(mode="daily")
        elif path == "/api/settlement/trigger/monthly":
            self._handle_settlement_trigger(mode="monthly")
        elif path == "/api/settlement/trigger/daily-date":
            self._handle_settlement_trigger_daily_date()
        elif path == "/api/settlement/trigger/monthly-date":
            self._handle_settlement_trigger_monthly_date()

        elif path == "/api/settings/smtp":
            self._handle_smtp_settings()
        elif path == "/api/gaosb/captcha-resolved":
            self._handle_captcha_resolved()
        else:
            self._send_method_not_allowed()

    def do_PUT(self):
        self._send_method_not_allowed()

    def do_DELETE(self):
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
        response_data = None
        error_message = None
        not_found = False

        try:
            if path == "/api/kpis":
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
            "smtp_username": settings.smtp_username,
            "smtp_password_masked": "********" if settings.smtp_password else "",
            "smtp_to": settings.alert_email,
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
                result = MonthlySettlementJob().run(target_month=None)
                result["download_url"] = "/api/settlement/download/latest/monthly"
            else:
                from app.jobs.daily_settlement_job import DailySettlementJob
                result = DailySettlementJob().run(target_date=None)
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
                result = DailySettlementJob().run(target_date=date_str)
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
                result = MonthlySettlementJob().run(target_month=month_str)
                if result.get("status") == "SUCCESS":
                    result["download_url"] = f"/api/settlement/download/monthly/{month_str}"
                response_data = result
        except Exception as e:
            logger.error(f"Geçmiş aylık mahsuplaşma tetikleme hatası ({month_str}): {e}")
            error_message = "Mahsuplaşma işlemi tamamlanamadı. Lütfen daha sonra tekrar deneyin."

        self._send_json_contract(response_data, error_message)


    def _handle_captcha_resolved(self) -> None:
        """
        Neden: Kullanıcı GAOSB doğrulamasını tamamladığını bildirdiğinde flag dosyası
        silinir ve duraklatılan job (flag'deki job_type/target'e göre) yeniden çalıştırılır.
        Doğrulama hâlâ geçmemişse extractor flag'i yeniden yazar ve kullanıcıya bildirilir.
        """
        flag_info = {}
        if CAPTCHA_FLAG_PATH.exists():
            try:
                # Neden: utf-8-sig — elle/PowerShell ile yazılmış BOM'lu dosyayı da okur.
                flag_info = json.loads(CAPTCHA_FLAG_PATH.read_text(encoding="utf-8-sig"))
            except Exception:
                pass
            try:
                CAPTCHA_FLAG_PATH.unlink()
            except Exception as e:
                logger.error(f"Captcha flag dosyası silinemedi: {e}")

        job_type = flag_info.get("job_type", "daily")
        target = flag_info.get("target")
        logger.warning(f"Captcha doğrulaması tamamlandı bildirimi alındı; {job_type} job yeniden çalıştırılıyor (target={target}).")

        error_message = None
        response_data = None
        try:
            if job_type == "monthly":
                from app.jobs.monthly_settlement_job import MonthlySettlementJob
                result = MonthlySettlementJob().run(target_month=target)
                result["download_url"] = "/api/settlement/download/latest/monthly"
            else:
                from app.jobs.daily_settlement_job import DailySettlementJob
                result = DailySettlementJob().run(target_date=target)
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

        # Neden: Yalnızca bilinen anahtarlar, dolu gönderilmişse güncellenir.
        env_key_map = {
            "smtp_host": "SMTP_HOST",
            "smtp_port": "SMTP_PORT",
            "smtp_username": "SMTP_USERNAME",
            "smtp_password": "SMTP_PASSWORD",
            "smtp_to": "SMTP_TO",
        }
        updates = {}
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

            # Neden: Çalışan süreçte de yeni değerler görünür olsun (settings nesnesi
            # başlangıçta donduğu için tam etki uygulama yeniden başlatılınca oluşur).
            for key, value in updates.items():
                os.environ[key] = value

            logger.info(f"SMTP ayarları güncellendi: {sorted(updates.keys())}")
            self._send_json_contract({
                "updated_keys": sorted(updates.keys()),
                "note": "Ayarlar kaydedildi. Değişikliklerin tam olarak etkinleşmesi için uygulamanın yeniden başlatılması gerekebilir.",
            }, None)
        except Exception as e:
            logger.error(f"SMTP ayarları .env dosyasına yazılamadı: {e}")
            self._send_json_contract(None, "Ayarlar kaydedilemedi. Lütfen sistem yöneticinizle iletişime geçin.")

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
