from typing import List, Dict, Any, Optional
from sqlalchemy import desc, asc, func
from app.database.db_session import SessionLocal
from app.database.models import DailyGeneration, SolarPlant
from app.core.logger import setup_logger

from sqlalchemy.orm import joinedload

logger = setup_logger("AnalyticsRepository")

class AnalyticsRepository:
    """
    Neden: SQLite/PostgreSQL veritabanındaki günlük üretim kayıtlarını 
    analiz motorunun tüketebileceği şekilde salt-okunur (read-only) olarak çekmek.
    """
    def __init__(self):
        pass

    def get_all_generations_ordered(self) -> List[DailyGeneration]:
        """Tüm günlük üretim verilerini tarihe göre sıralı getirir."""
        session = SessionLocal()
        try:
            # Plant nesnesini eager ( joinedload ) olarak yükle
            return session.query(DailyGeneration).options(joinedload(DailyGeneration.plant)).order_by(asc(DailyGeneration.date)).all()
        except Exception as e:
            logger.error(f"Üretim verileri veritabanından çekilemedi: {e}")
            return []
        finally:
            session.close()

    def get_all_plants(self) -> List[SolarPlant]:
        """Sistemdeki tüm kayıtlı tesisleri getirir."""
        session = SessionLocal()
        try:
            return session.query(SolarPlant).all()
        except Exception as e:
            logger.error(f"Tesis listesi okunamadı: {e}")
            return []
        finally:
            session.close()
