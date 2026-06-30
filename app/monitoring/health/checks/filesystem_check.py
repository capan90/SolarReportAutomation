import time
import shutil
import os
from pathlib import Path
from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.core.config import settings, BASE_DIR

class FilesystemCheck(IHealthCheck):
    """
    Neden: Gerekli çıktı dizinlerinin yazılabilirliğini doğrulamak 
    ve disk doluluğunu izleyerek disk alanı yetersizliği risklerini önceden belirlemek.
    """
    @property
    def name(self) -> str:
        return "Filesystem & Disk Space"

    @property
    def timeout_seconds(self) -> float:
        return 2.0

    @property
    def severity(self) -> str:
        return "CRITICAL"

    def run(self) -> HealthCheckResult:
        start_time = time.time()
        
        # Test edilecek dizinler
        target_dirs = {
            "raw_exports": settings.download_directory,
            "pdf": settings.report_directory,
            "charts": settings.chart_directory,
            "runtime": BASE_DIR / "outputs" / "runtime"
        }
        
        dir_status = {}
        all_dirs_ok = True
        
        # 1. Dizinlerin oluşturulması ve yazma izinlerinin test edilmesi
        for key, path in target_dirs.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
                # Yazma testi: geçici dosya yazıp sil
                test_file = path / f".health_write_test_{key}"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
                dir_status[str(path.relative_to(BASE_DIR) if path.is_relative_to(BASE_DIR) else path)] = "WRITABLE"
            except Exception as e:
                dir_status[str(path)] = f"ERROR: {str(e)}"
                all_dirs_ok = False
        
        # 2. Disk alanı kontrolü
        try:
            total, used, free = shutil.disk_usage(BASE_DIR)
            bytes_in_gb = 1024 ** 3
            total_gb = round(total / bytes_in_gb, 2)
            used_gb = round(used / bytes_in_gb, 2)
            free_gb = round(free / bytes_in_gb, 2)
            usage_percentage = round((used / total) * 100, 2)
        except Exception as e:
            total_gb = used_gb = free_gb = usage_percentage = 0.0
            dir_status["disk_error"] = str(e)
            all_dirs_ok = False

        duration_ms = int((time.time() - start_time) * 1000)
        
        details = {
            "total_space_gb": total_gb,
            "used_space_gb": used_gb,
            "free_space_gb": free_gb,
            "usage_percentage": usage_percentage,
            "directory_status": dir_status
        }

        # %90 üzeri doluluk uyarı (WARNING) üretir
        if not all_dirs_ok:
            return HealthCheckResult(
                name=self.name,
                status="FAILED",
                duration_ms=duration_ms,
                message="Bazı dizinlere yazma testi başarısız oldu veya disk metrikleri alınamadı.",
                details=details
            )
        elif usage_percentage >= 90.0:
            return HealthCheckResult(
                name=self.name,
                status="WARNING",
                duration_ms=duration_ms,
                message=f"Disk alanı kritik sınırda (Dolu: %{usage_percentage}).",
                details=details
            )
        else:
            return HealthCheckResult(
                name=self.name,
                status="SUCCESS",
                duration_ms=duration_ms,
                message="Tüm çıktı dizinleri yazılabilir ve disk alanı yeterli.",
                details=details
            )
