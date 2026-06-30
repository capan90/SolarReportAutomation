from app.monitoring.metrics.interface import Metric, MetricType, IMetricExporter
from app.monitoring.metrics.metrics_registry import MetricsRegistry
from app.monitoring.metrics.metrics_collector import MetricsCollector
from app.monitoring.metrics.exporters import ConsoleMetricExporter, DatabaseMetricExporter, JsonMetricExporter

def get_default_registry() -> MetricsRegistry:
    """
    Neden: Gözlemlenebilirlik için varsayılan Console, JSON ve 
    Database metrik ihracatçılarıyla (exporters) yapılandırılmış bir registry oluşturmak.
    """
    registry = MetricsRegistry()
    registry.register_exporter(ConsoleMetricExporter())
    registry.register_exporter(DatabaseMetricExporter())
    registry.register_exporter(JsonMetricExporter())
    return registry

__all__ = [
    "Metric",
    "MetricType",
    "IMetricExporter",
    "MetricsRegistry",
    "MetricsCollector",
    "ConsoleMetricExporter",
    "DatabaseMetricExporter",
    "JsonMetricExporter",
    "get_default_registry"
]
