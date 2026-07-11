from datetime import datetime, timedelta
from typing import Optional, List, Dict
from app.database.db_session import SessionLocal
from app.database.models import PlantStatus
from app.core.logger import setup_logger

logger = setup_logger("PlantStatusRepository")

class PlantStatusRepository:
    """
    Neden: GES durumlarını (plant_status) veritabanına kaydetmek, 
    son durumları çekmek ve bildirim takibini gerçekleştirmek için kullanılan depo sınıfı.
    """

    def save_statuses(self, statuses: Dict[str, str], 
                      previous: Dict[str, str],
                      notified_statuses: Optional[Dict[str, bool]] = None) -> None:
        """Her GES için PlantStatus kaydı oluştur"""
        session = SessionLocal()
        try:
            now = datetime.utcnow()
            for plant_name, status in statuses.items():
                prev = previous.get(plant_name)
                notified = False
                if notified_statuses and plant_name in notified_statuses:
                    notified = notified_statuses[plant_name]
                
                ps = PlantStatus(
                    timestamp=now,
                    plant_name=plant_name,
                    status=status,
                    previous_status=prev,
                    notified=notified,
                    created_at=now
                )
                session.add(ps)
            session.commit()
            logger.info("Santral durumları başarıyla kaydedildi.")
        except Exception as e:
            session.rollback()
            logger.error(f"Santral durumları kaydedilirken hata: {e}")
            raise
        finally:
            session.close()

    def get_latest_statuses(self) -> Dict[str, str]:
        """Her GES için en son durum kaydını döndür
        → {"GES-2": "Normal", "GES-4": "Abnormal"}"""
        session = SessionLocal()
        try:
            from sqlalchemy import func
            subquery = session.query(
                PlantStatus.plant_name,
                func.max(PlantStatus.id).label("max_id")
            ).group_by(PlantStatus.plant_name).subquery()

            results = session.query(PlantStatus).join(
                subquery,
                PlantStatus.id == subquery.c.max_id
            ).all()

            # Detach records from session so we can read them safely after close
            session.expunge_all()
            return {r.plant_name: r.status for r in results}
        except Exception as e:
            logger.error(f"En son durum kayıtları çekilirken hata: {e}")
            return {}
        finally:
            session.close()

    def get_latest_status_records(self) -> List[PlantStatus]:
        """Her GES için en son durum kaydı nesnelerini döndür"""
        session = SessionLocal()
        try:
            from sqlalchemy import func
            subquery = session.query(
                PlantStatus.plant_name,
                func.max(PlantStatus.id).label("max_id")
            ).group_by(PlantStatus.plant_name).subquery()

            results = session.query(PlantStatus).join(
                subquery,
                PlantStatus.id == subquery.c.max_id
            ).all()

            session.expunge_all()
            return results
        except Exception as e:
            logger.error(f"En son durum nesneleri çekilirken hata: {e}")
            return []
        finally:
            session.close()

    def get_status_history(self, 
                           plant_name: Optional[str] = None,
                           hours: int = 24) -> List[PlantStatus]:
        """Son N saatin durum geçmişi"""
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            query = session.query(PlantStatus).filter(PlantStatus.timestamp >= cutoff)
            if plant_name:
                query = query.filter(PlantStatus.plant_name == plant_name)
            
            results = query.order_by(PlantStatus.timestamp.desc()).all()
            session.expunge_all()
            return results
        except Exception as e:
            logger.error(f"Durum geçmişi çekilirken hata: {e}")
            return []
        finally:
            session.close()

    def get_active_anomalies(self) -> List[PlantStatus]:
        """Şu an Normal olmayan GES'leri döndür"""
        session = SessionLocal()
        try:
            from sqlalchemy import func
            subquery = session.query(
                PlantStatus.plant_name,
                func.max(PlantStatus.id).label("max_id")
            ).group_by(PlantStatus.plant_name).subquery()

            results = session.query(PlantStatus).join(
                subquery,
                PlantStatus.id == subquery.c.max_id
            ).filter(PlantStatus.status != "Normal").all()

            session.expunge_all()
            return results
        except Exception as e:
            logger.error(f"Aktif anomaliler çekilirken hata: {e}")
            return []
        finally:
            session.close()

    def get_latest_notified_record(self, plant_name: str) -> Optional[PlantStatus]:
        """Belirli bir plant için en son bildirim gönderilmiş (notified=True) kaydı döndür"""
        session = SessionLocal()
        try:
            record = session.query(PlantStatus)\
                .filter(PlantStatus.plant_name == plant_name, PlantStatus.notified == True)\
                .order_by(PlantStatus.timestamp.desc())\
                .first()
            if record:
                session.expunge(record)
            return record
        except Exception as e:
            logger.error(f"{plant_name} için en son bildirim kaydı çekilirken hata: {e}")
            return None
        finally:
            session.close()
