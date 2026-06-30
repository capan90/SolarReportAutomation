import json
from pathlib import Path
from datetime import datetime
from typing import List

from app.monitoring.metrics.interface import IMetricExporter, Metric
from app.database.metric_repository import MetricRepository
from app.core.config import BASE_DIR
from app.core.logger import setup_logger

logger = setup_logger("MetricExporters")

class ConsoleMetricExporter(IMetricExporter):
    """
    Neden: Metrikleri stdout/logs konsoluna Prometheus standart formatında 
    (metric_name{labels} value timestamp) basarak dış gözlem araçlarının (Pull) çekmesini sağlamak.
    """
    def export(self, metrics: List[Metric]) -> None:
        lines = ["\n===== PROMETHEUS METRIC TELEMETRY ====="]
        for m in metrics:
            # Boyutları (labels) formatla
            label_parts = []
            
            # Ek boyutları birleştir
            for k, v in m.dimensions.items():
                label_parts.append(f'{k}="{v}"')
                
            if m.stage_name:
                label_parts.append(f'stage_name="{m.stage_name}"')
                
            label_str = ",".join(label_parts)
            label_suffix = f"{{{label_str}}}" if label_parts else ""
            
            # Prometheus biçimi: metric.name{tag="val"} value timestamp_ms
            ts_ms = int(m.timestamp.timestamp() * 1000)
            lines.append(f"{m.name}{label_suffix} {m.value} {ts_ms}")
        lines.append("=======================================\n")
        logger.info("\n".join(lines))


class DatabaseMetricExporter(IMetricExporter):
    """
    Neden: Toplanan metrikleri database deposuna (Repository abstraction üzerinden) 
    kalıcı olarak kaydetmek (best-effort).
    """
    def __init__(self, repository: MetricRepository = None):
        self.repository = repository or MetricRepository()

    def export(self, metrics: List[Metric]) -> None:
        for m in metrics:
            run_id = m.dimensions.get("run_id", "unknown-run-id")
            self.repository.save_metric(
                run_id=run_id,
                metric_name=m.name,
                metric_category=m.category,
                metric_value=m.value,
                stage_name=m.stage_name,
                dimensions=m.dimensions
            )


class JsonMetricExporter(IMetricExporter):
    """
    Neden: Metrikleri outputs/metrics/ dizini altına JSON formatında arşivleyerek
    statik analize uygun hale getirmek.
    """
    def export(self, metrics: List[Metric]) -> None:
        metrics_dir = BASE_DIR / "outputs" / "metrics"
        try:
            metrics_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = metrics_dir / f"metrics_{timestamp}.json"
            
            # JSON formatında serileştir
            data_list = []
            for m in metrics:
                data_list.append({
                    "name": m.name,
                    "value": m.value,
                    "type": m.metric_type.value,
                    "category": m.category,
                    "stage_name": m.stage_name,
                    "dimensions": m.dimensions,
                    "timestamp": m.timestamp.isoformat()
                })
                
            report_file.write_text(json.dumps(data_list, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Metrik verileri JSON olarak arşivlendi: {report_file}")
        except Exception as e:
            logger.error(f"Metrikler JSON dosyasına kaydedilemedi: {e}")
