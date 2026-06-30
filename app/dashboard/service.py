import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from app.dashboard.repository import DashboardRepository
from app.dashboard.dto import (
    ExecutiveSummaryDto,
    PipelineRunDto,
    HealthStatusDto,
    MetricSeriesDto,
    NotificationDto
)
from app.core.config import BASE_DIR
from app.core.logger import setup_logger

logger = setup_logger("DashboardService")

class DashboardService:
    """
    Neden: Repository'den gelen ham verileri DTO (Data Transfer Object) formatına 
    dönüştürmek ve iş mantığı (Success Rate vb.) hesaplamalarını yapmak (SOLID - SRP).
    """
    def __init__(self, repository: Optional[DashboardRepository] = None):
        self.repository = repository or DashboardRepository()

    def get_executive_summary(self) -> ExecutiveSummaryDto:
        total = self.repository.get_total_runs_count()
        failed = self.repository.get_failed_runs_count()
        avg_dur = self.repository.get_avg_pipeline_duration()
        retries = self.repository.get_total_retries_count()
        
        success_rate = 100.0
        if total > 0:
            success_rate = round(((total - failed) / total) * 100, 2)
            
        # Son sağlık raporundan genel skoru al (gauge metrik olarak)
        health_score = 100.0
        latest_report = self._get_latest_health_report_data()
        if latest_report:
            status = latest_report.get("overall_status", "SUCCESS")
            if status == "FAILED":
                health_score = 0.0
            elif status == "WARNING":
                health_score = 50.0

        return ExecutiveSummaryDto(
            success_rate=success_rate,
            failed_runs_count=failed,
            avg_duration_ms=round(avg_dur, 2),
            total_retries=retries,
            health_score=health_score
        )

    def get_pipeline_history(self, limit: int = 20) -> List[PipelineRunDto]:
        runs = self.repository.get_recent_runs(limit)
        return [
            PipelineRunDto(
                run_id=r.run_id,
                started_at=r.started_at.isoformat() if isinstance(r.started_at, datetime) else str(r.started_at),
                duration_ms=r.duration_ms,
                status=r.status,
                exit_code=r.exit_code or 0,
                issues_count=r.issues_count or 0
            )
            for r in runs
        ]

    def get_health_status(self) -> HealthStatusDto:
        latest = self._get_latest_health_report_data()
        if latest:
            return HealthStatusDto(
                overall_status=latest.get("overall_status", "UNKNOWN"),
                checks=latest.get("checks", [])
            )
        return HealthStatusDto(
            overall_status="NO_DATA",
            checks=[]
        )

    def get_metric_history(self, metric_name: str, limit: int = 50) -> MetricSeriesDto:
        series = self.repository.get_metric_series(metric_name, limit)
        # Tarihe göre sırala (grafik için soldan sağa akmalı)
        series.reverse()
        
        timestamps = [
            m.timestamp.strftime("%H:%M:%S") if isinstance(m.timestamp, datetime) else str(m.timestamp)
            for m in series
        ]
        values = [float(m.metric_value) for m in series]
        
        return MetricSeriesDto(
            metric_name=metric_name,
            timestamps=timestamps,
            values=values
        )

    def get_notification_history(self, limit: int = 20) -> List[NotificationDto]:
        notifs = self.repository.get_recent_notifications(limit)
        return [
            NotificationDto(
                run_id=n.run_id,
                sent_at=n.sent_at.isoformat() if isinstance(n.sent_at, datetime) else str(n.sent_at),
                status=n.status,
                attempt_count=n.attempt_count,
                recipient=n.recipient,
                error_message=n.error_message
            )
            for n in notifs
        ]

    def _get_latest_health_report_data(self) -> Optional[dict]:
        """
        Neden: outputs/health/ dizinindeki en son sağlık kontrolü raporunu okumak.
        """
        health_dir = BASE_DIR / "outputs" / "health"
        if not health_dir.exists():
            return None
            
        files = list(health_dir.glob("health_*.json"))
        if not files:
            return None
            
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_file = files[0]
        
        try:
            return json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Health raporu JSON okunamadı ({latest_file.name}): {e}")
            return None
