from datetime import date as date_type, datetime, timedelta
from typing import List, Optional, Dict

from sqlalchemy import desc, func
from app.database.db_session import SessionLocal
from app.database.models import (
    EtlRun, RetryHistory, NotificationHistory, PerformanceMetric, Base,
    SettlementHourly, SettlementDaily, SettlementMonthly,
    DailyGeneration, SolarPlant,
)
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

    # ------------------------------------------------------------------
    # Settlement (mahsuplaşma) sorguları
    # ------------------------------------------------------------------
    def get_settlement_daily(self, limit: int = 7) -> List[SettlementDaily]:
        """Neden: settlement_daily'den en güncel N günü (tarihe göre azalan) getirmek."""
        session = SessionLocal()
        try:
            return (
                session.query(SettlementDaily)
                .order_by(desc(SettlementDaily.date))
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error(f"Settlement daily okunamadı: {e}")
            return []
        finally:
            session.close()

    def get_settlement_monthly(self, limit: int = 3) -> List[SettlementMonthly]:
        """Neden: settlement_monthly'den en güncel N ayı getirmek."""
        session = SessionLocal()
        try:
            return (
                session.query(SettlementMonthly)
                .order_by(desc(SettlementMonthly.year), desc(SettlementMonthly.month))
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error(f"Settlement monthly okunamadı: {e}")
            return []
        finally:
            session.close()

    def get_settlement_hourly_by_date(self, target_date: date_type) -> List[SettlementHourly]:
        """Neden: Bir günün 24 saatlik mahsup kırılımını saat sırasıyla getirmek."""
        session = SessionLocal()
        try:
            return (
                session.query(SettlementHourly)
                .filter(SettlementHourly.date == target_date)
                .order_by(SettlementHourly.hour)
                .all()
            )
        except Exception as e:
            logger.error(f"Settlement hourly okunamadı ({target_date}): {e}")
            return []
        finally:
            session.close()

    def get_settlement_daily_by_date(self, target_date: date_type) -> Optional[SettlementDaily]:
        session = SessionLocal()
        try:
            return (
                session.query(SettlementDaily)
                .filter(SettlementDaily.date == target_date)
                .first()
            )
        except Exception as e:
            logger.error(f"Settlement daily (tek gün) okunamadı ({target_date}): {e}")
            return None
        finally:
            session.close()

    def get_settlement_month(self, year: int, month: int) -> Optional[SettlementMonthly]:
        session = SessionLocal()
        try:
            return (
                session.query(SettlementMonthly)
                .filter(SettlementMonthly.year == year, SettlementMonthly.month == month)
                .first()
            )
        except Exception as e:
            logger.error(f"Settlement monthly (tek ay) okunamadı ({year}-{month}): {e}")
            return None
        finally:
            session.close()

    def get_settlement_last_update(self) -> Optional[datetime]:
        """Neden: Dashboard'da 'son güncelleme' bilgisini göstermek."""
        session = SessionLocal()
        try:
            candidates = [
                session.query(func.max(SettlementHourly.created_at)).scalar(),
                session.query(func.max(SettlementDaily.created_at)).scalar(),
                session.query(func.max(SettlementMonthly.created_at)).scalar(),
            ]
            candidates = [c for c in candidates if c is not None]
            return max(candidates) if candidates else None
        except Exception as e:
            logger.error(f"Settlement son güncelleme okunamadı: {e}")
            return None
        finally:
            session.close()

    def get_plant_distribution(self, days: int = 30) -> List[Dict]:
        """
        Neden: Analitik sayfasındaki 'GES bazlı üretim dağılımı' grafiğini beslemek.
        Santral bazlı veri settlement tablolarında tutulmadığından daily_generations
        tablosundan (ETL verisi) son N günün üretim toplamı alınır.
        """
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow().date() - timedelta(days=days)
            rows = (
                session.query(
                    SolarPlant.name,
                    func.sum(DailyGeneration.yield_today_kwh).label("total_kwh"),
                )
                .join(DailyGeneration, DailyGeneration.plant_id == SolarPlant.id)
                .filter(DailyGeneration.date >= cutoff)
                .group_by(SolarPlant.name)
                .order_by(desc("total_kwh"))
                .all()
            )
            return [{"plant": r[0], "total_kwh": float(r[1] or 0)} for r in rows]
        except Exception as e:
            logger.error(f"GES dağılımı okunamadı: {e}")
            return []
        finally:
            session.close()
