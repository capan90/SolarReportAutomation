import time
import threading
from datetime import datetime
from typing import List
from pathlib import Path

from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.monitoring.health.health_models import HealthReport
from app.monitoring.health.checks.database_check import DatabaseCheck
from app.monitoring.health.checks.browser_check import BrowserCheck
from app.monitoring.health.checks.filesystem_check import FilesystemCheck
from app.monitoring.health.checks.smtp_check import SMTPCheck
from app.monitoring.health.checks.portal_check import PortalCheck
from app.core.config import BASE_DIR
from app.core.logger import setup_logger

logger = setup_logger("HealthChecker")

class HealthChecker:
    """
    Neden: Tanımlı tüm sağlık kontrollerini (IHealthCheck) koordine etmek,
    zaman aşımlarını (timeout) yönetmek, konsola rapor yazdırmak ve 
    çıktıları JSON olarak arşivlemek.
    """
    def __init__(self, checks: List[IHealthCheck] = None):
        if checks is None:
            self.checks = [
                DatabaseCheck(),
                BrowserCheck(),
                FilesystemCheck(),
                SMTPCheck(),
                PortalCheck()
            ]
        else:
            self.checks = checks

    def run_check_with_timeout(self, check: IHealthCheck) -> HealthCheckResult:
        """
        Neden: Herhangi bir kontrolün sonsuza kadar bloklanmasını veya 
        belirlenen timeout limitini aşmasını engellemek için thread tabanlı koruma sağlamak.
        """
        result_holder = []
        
        def worker():
            try:
                res = check.run()
                result_holder.append(res)
            except Exception as e:
                result_holder.append(HealthCheckResult(
                    name=check.name,
                    status="FAILED",
                    duration_ms=0,
                    message=f"Beklenmedik kontrol hatası: {str(e)}",
                    details={}
                ))

        start_time = time.time()
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        thread.join(timeout=check.timeout_seconds)

        if thread.is_alive():
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Sağlık kontrolü zaman aşımına uğradı ({check.timeout_seconds} sn): {check.name}")
            return HealthCheckResult(
                name=check.name,
                status="TIMEOUT",
                duration_ms=duration_ms,
                message=f"Kontrol zaman aşımı limitine ({check.timeout_seconds} sn) ulaştı.",
                details={}
            )
        
        return result_holder[0]

    def run_all(self) -> HealthReport:
        """
        Neden: Tüm kontrolleri sırayla koşturmak, durum istatistiklerini hesaplamak
        ve raporu konsolide etmek.
        """
        logger.info("Sistem sağlık kontrolleri başlatılıyor...")
        report = HealthReport()
        start_time = datetime.now()
        report.started_at = start_time.isoformat()
        
        overall_status = "SUCCESS"
        warnings_count = 0
        errors_count = 0
        
        for check in self.checks:
            logger.info(f"Koşulan Kontrol: {check.name}...")
            result = self.run_check_with_timeout(check)
            report.checks.append(result)
            
            if result.status in ["FAILED", "TIMEOUT"]:
                if check.severity == "CRITICAL":
                    overall_status = "FAILED"
                elif overall_status != "FAILED" and check.severity == "WARNING":
                    overall_status = "WARNING"
                errors_count += 1
            elif result.status == "WARNING":
                if overall_status != "FAILED":
                    overall_status = "WARNING"
                warnings_count += 1
                
            logger.info(f"Sonuç: [{result.status}] - {result.message} ({result.duration_ms} ms)")
            
        finished_time = datetime.now()
        report.finished_at = finished_time.isoformat()
        report.duration_ms = int((finished_time - start_time).total_seconds() * 1000)
        report.overall_status = overall_status
        report.warnings = warnings_count
        report.errors = errors_count
        
        # Raporu kaydet
        self._save_report(report)
        
        return report

    def _save_report(self, report: HealthReport) -> None:
        """
        Neden: Sağlık raporunu JSON dosyası olarak outputs/health/ dizini altına
        zaman damgasıyla kaydetmek.
        """
        health_dir = BASE_DIR / "outputs" / "health"
        try:
            health_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = health_dir / f"health_{timestamp}.json"
            
            report_file.write_text(report.to_json(), encoding="utf-8")
            logger.info(f"Sağlık kontrolü raporu başarıyla kaydedildi: {report_file}")
        except Exception as e:
            logger.error(f"Sağlık raporu diske yazılamadı: {e}")

    def print_summary(self, report: HealthReport) -> None:
        """
        Neden: Konsol çıktısı olarak kullanıcıya okunabilir bir özet sunmak.
        """
        print("\n" + "=" * 50)
        print("           SİSTEM SAĞLIK RAPORU (HEALTH CHECK)       ")
        print("=" * 50)
        print(f"Genel Durum     : {report.overall_status}")
        print(f"Schema Sürümü   : {report.schema_version}")
        print(f"Başlangıç Zamanı: {report.started_at}")
        print(f"Bitiş Zamanı    : {report.finished_at}")
        print(f"Toplam Süre     : {report.duration_ms} ms")
        print(f"Hata / Uyarı    : Hata={report.errors}, Uyarı={report.warnings}")
        print("-" * 50)
        for check in report.checks:
            print(f"[{check.status:<7}] {check.name:<30} | {check.duration_ms:>5} ms | {check.message}")
        print("=" * 50 + "\n")
