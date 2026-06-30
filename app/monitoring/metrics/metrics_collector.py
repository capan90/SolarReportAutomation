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

    def _get_dimensions(self, run_id: str, metric_type: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Neden: Tüm metrik boyutlarına (tag/labels) aktif kaynak (source_name) bilgisini 
        dinamik olarak enjekte etmek (best-effort).
        """
        source_name = "isolarcloud"
        try:
            from app.sources.context import get_source_context
            context = get_source_context()
            if context and context.source_name:
                source_name = context.source_name
        except Exception:
            pass

        dims = {
            "run_id": run_id,
            "environment": settings.app_env,
            "metric_type": metric_type,
            "source_name": source_name
        }
        if extra:
            dims.update(extra)
        return dims

    def collect_system_metrics(self, run_id: str, stage_name: Optional[str] = None) -> None:
        """
        Neden: CPU, RAM ve disk doluluğunu toplamak. 
        Performans bütçesini (<%2) korumak için hafif sorgular tercih edilir.
        """
        dimensions = self._get_dimensions(run_id, "system")
        
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
            pass

    def record_stage_duration(self, run_id: str, stage_name: str, duration_ms: float) -> None:
        """
        Neden: Her ETL aşamasının süresini zamanlayıcı olarak kaydetmek.
        """
        dimensions = self._get_dimensions(run_id, "application")
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
        dimensions = self._get_dimensions(run_id, "application")
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
        dimensions = self._get_dimensions(run_id, "operational", {"operation": operation})
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
        dimensions = self._get_dimensions(run_id, "business")
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
        dimensions = self._get_dimensions(run_id, "operational")
        
        self.registry.increment_counter("scheduler.run", 1.0, "operational", None, dimensions)
        
        if is_failed:
            self.registry.increment_counter("pipeline.failed.runs", 1.0, "operational", None, dimensions)
        if is_startup_failure:
            self.registry.increment_counter("startup.validation.failed", 1.0, "operational", None, dimensions)
            
        success_score = 0.0 if (is_failed or is_startup_failure) else 100.0
        self.registry.set_gauge("health.score", success_score, "operational", None, dimensions)
