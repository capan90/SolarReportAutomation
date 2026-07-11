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

    # ------------------------------------------------------------------
    # Settlement (mahsuplaşma) servisleri
    # ------------------------------------------------------------------
    @staticmethod
    def _settlement_row_to_dict(row) -> dict:
        """Neden: Settlement ORM satırlarını API sözleşmesindeki Türkçe alan adlarına çevirmek."""
        return {
            "uretim": round(row.production_kwh or 0.0, 1),
            "tuketim": round(row.consumption_kwh or 0.0, 1),
            "mahsup": round(row.settled_kwh or 0.0, 1),
            "cekis": round(row.grid_import_kwh or 0.0, 1),
            "satis": round(row.grid_export_kwh or 0.0, 1),
        }

    def get_settlement_daily_list(self, limit: int = 7) -> List[dict]:
        rows = self.repository.get_settlement_daily(limit)
        return [
            {"tarih": row.date.isoformat(), **self._settlement_row_to_dict(row)}
            for row in rows
        ]

    def get_settlement_monthly_list(self, limit: int = 3) -> List[dict]:
        rows = self.repository.get_settlement_monthly(limit)
        return [
            {"yil": row.year, "ay": row.month, "donem": f"{row.year}-{row.month:02d}",
             **self._settlement_row_to_dict(row)}
            for row in rows
        ]

    def get_settlement_hourly(self, date_str: str) -> List[dict]:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        rows = self.repository.get_settlement_hourly_by_date(target)
        return [
            {"saat": row.hour, "saat_araligi": f"{row.hour:02d}:00-{(row.hour + 1) % 24:02d}:00",
             **self._settlement_row_to_dict(row)}
            for row in rows
        ]

    def get_settlement_summary(self) -> dict:
        """
        Neden: Ana sayfa KPI kartlarını beslemek. 'bugun' için bugünün kaydı,
        yoksa DB'deki en güncel gün gösterilir (günlük job dünü hesapladığından
        gün içinde bugünün kaydı henüz oluşmamış olur).
        """
        today = datetime.now().date()

        today_row = self.repository.get_settlement_daily_by_date(today)
        if today_row is not None:
            bugun = {"tarih": today.isoformat(), **self._settlement_row_to_dict(today_row)}
        else:
            latest = self.repository.get_settlement_daily(limit=1)
            if latest:
                bugun = {"tarih": latest[0].date.isoformat(), **self._settlement_row_to_dict(latest[0])}
            else:
                bugun = {"tarih": None, "uretim": 0, "tuketim": 0, "mahsup": 0, "cekis": 0, "satis": 0}

        month_row = self.repository.get_settlement_month(today.year, today.month)
        if month_row is None:
            # Neden: İçinde bulunulan ayın agregatı henüz yazılmamışsa en güncel ay gösterilir.
            latest_months = self.repository.get_settlement_monthly(limit=1)
            month_row = latest_months[0] if latest_months else None

        if month_row is not None:
            bu_ay = {"donem": f"{month_row.year}-{month_row.month:02d}",
                     **self._settlement_row_to_dict(month_row)}
        else:
            bu_ay = {"donem": None, "uretim": 0, "tuketim": 0, "mahsup": 0, "cekis": 0, "satis": 0}

        last_update = self.repository.get_settlement_last_update()
        return {
            "bugun": bugun,
            "bu_ay": bu_ay,
            "son_guncelleme": last_update.isoformat() if last_update else None,
        }

    def get_plant_distribution(self, days: int = 30) -> List[dict]:
        return self.repository.get_plant_distribution(days)

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
