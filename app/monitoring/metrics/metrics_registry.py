from typing import Dict, List, Optional
from datetime import datetime
from app.monitoring.metrics.interface import Metric, MetricType, IMetricExporter
from app.core.logger import setup_logger

logger = setup_logger("MetricsRegistry")

class MetricsRegistry:
    """
    Neden: Uygulama genelinde toplanan metrikleri bellek üzerinde merkezi bir 
    havuzda (registry) toplamak ve kayıtlı exporter'lar aracılığıyla dışa aktarmak.
    """
    def __init__(self):
        self._metrics: Dict[str, Metric] = {}
        self._exporters: List[IMetricExporter] = []

    def register_exporter(self, exporter: IMetricExporter) -> None:
        """Yeni bir metrik ihracatçısı (exporter) ekler."""
        self._exporters.append(exporter)

    def set_gauge(
        self,
        name: str,
        value: float,
        category: str,
        stage_name: Optional[str] = None,
        dimensions: Optional[Dict[str, str]] = None
    ) -> None:
        """Görsel anlık durum (gauge) değeri atar."""
        self._metrics[name] = Metric(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            category=category,
            stage_name=stage_name,
            dimensions=dimensions or {}
        )

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        category: str = "application",
        stage_name: Optional[str] = None,
        dimensions: Optional[Dict[str, str]] = None
    ) -> None:
        """Sayaç değerini belirtilen miktarda artırır."""
        if name in self._metrics:
            old_metric = self._metrics[name]
            new_value = old_metric.value + value
            self._metrics[name] = Metric(
                name=name,
                value=new_value,
                metric_type=MetricType.COUNTER,
                category=category,
                stage_name=stage_name,
                dimensions=dimensions or old_metric.dimensions
            )
        else:
            self._metrics[name] = Metric(
                name=name,
                value=value,
                metric_type=MetricType.COUNTER,
                category=category,
                stage_name=stage_name,
                dimensions=dimensions or {}
            )

    def record_timer(
        self,
        name: str,
        duration_ms: float,
        category: str,
        stage_name: Optional[str] = None,
        dimensions: Optional[Dict[str, str]] = None
    ) -> None:
        """Süre/zaman (timer) kaydeder."""
        self._metrics[name] = Metric(
            name=name,
            value=duration_ms,
            metric_type=MetricType.TIMER,
            category=category,
            stage_name=stage_name,
            dimensions=dimensions or {}
        )

    def get_all(self) -> List[Metric]:
        """Kayıtlı tüm metriklerin kopyasını liste olarak döner."""
        return list(self._metrics.values())

    def flush_and_export(self) -> None:
        """
        Neden: Kayıtlı tüm metrikleri tüm exporter'lara iletmek.
        """
        metrics = self.get_all()
        if not metrics:
            return

        for exporter in self._exporters:
            try:
                exporter.export(metrics)
            except Exception as e:
                logger.error(f"Metrik ihraç edilirken hata oluştu ({exporter.__class__.__name__}): {e}")
