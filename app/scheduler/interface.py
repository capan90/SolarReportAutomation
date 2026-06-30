from abc import ABC, abstractmethod
from typing import List, Dict, Any

class IScheduler(ABC):
    """
    Neden: ETL Pipeline tetikleme işlerinin işletim sistemi veya cloud sağlayıcı 
    zamanlayıcılarına kayıt edilmesi, sorgulanması ve silinmesi süreçlerini soyutlamak (SOLID - DIP).
    """
    @abstractmethod
    def register_job(self, job_name: str, schedule_time: str, command: str) -> bool:
        """İşi (job) zamanlayıcıya kaydeder. schedule_time: HH:MM formatında veya cron ifadesi."""
        pass

    @abstractmethod
    def remove_job(self, job_name: str) -> bool:
        """İşi zamanlayıcıdan siler."""
        pass

    @abstractmethod
    def list_jobs(self) -> List[Dict[str, Any]]:
        """Zamanlanmış tüm işleri listeler."""
        pass
