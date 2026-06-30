from datetime import datetime
import json
from typing import Dict, Any, Optional
from app.database.db_session import SessionLocal
from app.database.models import PerformanceMetric
from app.core.logger import setup_logger

logger = setup_logger("MetricRepository")

class MetricRepository:
    """
    Neden: Metrik verilerinin veritabanı (sqlite/postgresql) katmanına 
    best-effort olarak kaydedilmesini ve sorgulanmasını sağlamak (Repository Pattern).
    """
    def save_metric(
        self,
        run_id: str,
        metric_name: str,
        metric_category: str,
        metric_value: float,
        stage_name: Optional[str] = None,
        dimensions: Optional[Dict[str, Any]] = None
    ) -> bool:
        session = SessionLocal()
        try:
            # JSON formatındaki boyutları (tag/labels) serialize et
            labels_json = json.dumps(dimensions) if dimensions else None
            
            record = PerformanceMetric(
                run_id=run_id,
                stage_name=stage_name,
                metric_category=metric_category,
                metric_name=metric_name,
                metric_value=metric_value,
                labels=labels_json,
                timestamp=datetime.utcnow()
            )
            session.add(record)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Metrik kaydı veritabanına yazılamadı (Best-effort): {e}")
            return False
        finally:
            session.close()
