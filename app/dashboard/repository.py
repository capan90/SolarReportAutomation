from typing import List, Optional
from sqlalchemy import desc, func
from app.database.db_session import SessionLocal
from app.database.models import EtlRun, RetryHistory, NotificationHistory, PerformanceMetric, Base
from app.core.logger import setup_logger

logger = setup_logger("DashboardRepository")

class DashboardRepository:
    """
    Neden: Dashboard servis katmanının veritabanına erişimini salt-okunur (read-only)
    sorgularla sınırlamak ve veritabanı işlemlerini soyutlamak (Repository Pattern).
    """
    def __init__(self):
        # Database tabloları ve kilit durumunu bozmamak için her sorguda session açılıp kapatılır.
        pass

    def get_recent_runs(self, limit: int = 20) -> List[EtlRun]:
        session = SessionLocal()
        try:
            return session.query(EtlRun).order_by(desc(EtlRun.started_at)).limit(limit).all()
        except Exception as e:
            logger.error(f"Recent runs okunamadı: {e}")
            return []
        finally:
            session.close()

    def get_total_runs_count(self) -> int:
        session = SessionLocal()
        try:
            return session.query(func.count(EtlRun.id)).scalar() or 0
        except Exception as e:
            logger.error(f"Runs count okunamadı: {e}")
            return 0
        finally:
            session.close()

    def get_failed_runs_count(self) -> int:
        session = SessionLocal()
        try:
            return session.query(func.count(EtlRun.id)).filter(EtlRun.status == "FAILED").scalar() or 0
        except Exception as e:
            logger.error(f"Failed runs count okunamadı: {e}")
            return 0
        finally:
            session.close()

    def get_avg_pipeline_duration(self) -> float:
        session = SessionLocal()
        try:
            val = session.query(func.avg(EtlRun.duration_ms)).scalar()
            return float(val) if val is not None else 0.0
        except Exception as e:
            logger.error(f"Avg duration okunamadı: {e}")
            return 0.0
        finally:
            session.close()

    def get_total_retries_count(self) -> int:
        session = SessionLocal()
        try:
            return session.query(func.count(RetryHistory.id)).scalar() or 0
        except Exception as e:
            logger.error(f"Total retries okunamadı: {e}")
            return 0
        finally:
            session.close()

    def get_recent_notifications(self, limit: int = 20) -> List[NotificationHistory]:
        session = SessionLocal()
        try:
            return session.query(NotificationHistory).order_by(desc(NotificationHistory.sent_at)).limit(limit).all()
        except Exception as e:
            logger.error(f"Recent notifications okunamadı: {e}")
            return []
        finally:
            session.close()

    def get_metric_series(self, metric_name: str, limit: int = 50) -> List[PerformanceMetric]:
        session = SessionLocal()
        try:
            return session.query(PerformanceMetric).filter(
                PerformanceMetric.metric_name == metric_name
            ).order_by(desc(PerformanceMetric.timestamp)).limit(limit).all()
        except Exception as e:
            logger.error(f"Metric series okunamadı ({metric_name}): {e}")
            return []
        finally:
            session.close()
