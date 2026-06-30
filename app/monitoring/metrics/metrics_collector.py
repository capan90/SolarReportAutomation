import time
import shutil
import os
from typing import Dict, Optional, Any
from app.monitoring.metrics.metrics_registry import MetricsRegistry
from app.core.config import settings, BASE_DIR
from app.core.logger import setup_logger

logger = setup_logger("MetricsCollector")

class MetricsCollector:
    """
    Neden: Sistem durumlarını (CPU, RAM, Disk), pipeline performans sürelerini (Timers)
    ve iş/operasyon sayaçlarını (Counters) toplayıp MetricsRegistry'ye iletmek.
    """
    def __init__(self, registry: MetricsRegistry):
        self.registry = registry

    def collect_system_metrics(self, run_id: str, stage_name: Optional[str] = None) -> None:
        """
        Neden: CPU, RAM ve disk doluluğunu toplamak. 
        Performans bütçesini (<%2) korumak için hafif sorgular tercih edilir.
        """
        dimensions = {
            "run_id": run_id,
            "environment": settings.app_env,
            "metric_type": "system"
        }
        
        # 1. Disk doluluğu (Built-in shutil ile sıfır harici yük)
        try:
            total, used, free = shutil.disk_usage(BASE_DIR)
            usage_percentage = (used / total) * 100
            self.registry.set_gauge("system.disk.percent", usage_percentage, "system", stage_name, dimensions)
        except Exception:
            pass

        # 2. Bellek ve CPU metrikleri (psutil kütüphanesi varsa okunur, yoksa fallback)
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            mem_percent = mem.percent
            
            self.registry.set_gauge("system.cpu.percent", cpu_percent, "system", stage_name, dimensions)
            self.registry.set_gauge("system.memory.percent", mem_percent, "system", stage_name, dimensions)
        except ImportError:
            # psutil yüklü değilse CPU ve RAM metrikleri toplanmaz (YAGNI & Zero dependency)
            pass

    def record_stage_duration(self, run_id: str, stage_name: str, duration_ms: float) -> None:
        """
        Neden: Her ETL aşamasının süresini zamanlayıcı olarak kaydetmek.
        """
        dimensions = {
            "run_id": run_id,
            "environment": settings.app_env,
            "metric_type": "application"
        }
        self.registry.record_timer(
            "pipeline.stage.duration",
            duration_ms,
            "application",
            stage_name,
            dimensions
        )

    def record_pipeline_duration(self, run_id: str, duration_ms: float) -> None:
        """
        Neden: Toplam pipeline çalışma süresini kaydetmek.
        """
        dimensions = {
            "run_id": run_id,
            "environment": settings.app_env,
            "metric_type": "application"
        }
        self.registry.record_timer(
            "pipeline.duration",
            duration_ms,
            "application",
            None,
            dimensions
        )

    def record_retry_attempt(self, run_id: str, operation: str) -> None:
        """
        Neden: Tekrar deneme (retry) sayaçlarını artırmak.
        """
        dimensions = {
            "run_id": run_id,
            "operation": operation,
            "environment": settings.app_env,
            "metric_type": "operational"
        }
        self.registry.increment_counter(
            "retry.count",
            1.0,
            "operational",
            None,
            dimensions
        )

    def record_business_metrics(
        self,
        run_id: str,
        plant_count: int,
        imported_rows: int,
        validation_errors: int,
        duplicate_records: int = 0
    ) -> None:
        """
        Neden: ETL veri doğruluğunu ve yüklenen santral bilgilerini raporlamak.
        """
        dimensions = {
            "run_id": run_id,
            "environment": settings.app_env,
            "metric_type": "business"
        }
        self.registry.set_gauge("business.plant.count", plant_count, "business", None, dimensions)
        self.registry.set_gauge("business.imported.rows", imported_rows, "business", None, dimensions)
        self.registry.set_gauge("business.validation.errors", validation_errors, "business", None, dimensions)
        self.registry.set_gauge("business.duplicate.records", duplicate_records, "business", None, dimensions)

    def record_operational_metrics(
        self,
        run_id: str,
        is_failed: bool,
        is_startup_failure: bool = False
    ) -> None:
        """
        Neden: Çalışma anı operasyonel hata ve başarı sayaçlarını artırmak.
        """
        dimensions = {
            "run_id": run_id,
            "environment": settings.app_env,
            "metric_type": "operational"
        }
        
        # Scheduler / Pipeline tetiklenme metriği
        self.registry.increment_counter("scheduler.run", 1.0, "operational", None, dimensions)
        
        if is_failed:
            self.registry.increment_counter("pipeline.failed.runs", 1.0, "operational", None, dimensions)
        if is_startup_failure:
            self.registry.increment_counter("startup.validation.failed", 1.0, "operational", None, dimensions)
            
        # Başarı durumunu gauge olarak işaretle (1.0 = Success, 0.0 = Failed)
        success_score = 0.0 if (is_failed or is_startup_failure) else 100.0
        self.registry.set_gauge("health.score", success_score, "operational", None, dimensions)
