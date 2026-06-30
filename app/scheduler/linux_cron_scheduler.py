import subprocess
import re
from typing import List, Dict, Any
from app.scheduler.interface import IScheduler
from app.core.logger import setup_logger

logger = setup_logger("LinuxCronScheduler")

class LinuxCronScheduler(IScheduler):
    """
    Neden: Linux/Unix işletim sistemlerindeki 'crontab' mekanizmasını yönetmek.
    """
    def register_job(self, job_name: str, schedule_time: str, command: str) -> bool:
        """
        Neden: crontab dosyasına yeni cron satırı eklemek.
        schedule_time: '30 8 * * *' gibi standart bir cron ifadesi olmalıdır.
        """
        try:
            # Mevcut crontab'ı oku
            current_cron = self._get_crontab()
            
            # Eski aynı isimli iş varsa kaldır
            lines = [line for line in current_cron.splitlines() if f"# {job_name}" not in line]
            
            # Yeni iş ekle
            lines.append(f"{schedule_time} {command} # {job_name}")
            new_cron = "\n".join(lines) + "\n"
            
            # Yeni crontab'ı kaydet
            self._write_crontab(new_cron)
            logger.info(f"Linux cron görevi başarıyla kaydedildi: {job_name}")
            return True
        except Exception as e:
            logger.error(f"Linux cron görevi kaydedilirken hata: {e}")
            return False

    def remove_job(self, job_name: str) -> bool:
        """
        Neden: crontab dosyasından ilgili görevi satır bazlı silmek.
        """
        try:
            current_cron = self._get_crontab()
            lines = [line for line in current_cron.splitlines() if f"# {job_name}" not in line]
            new_cron = "\n".join(lines) + "\n"
            
            self._write_crontab(new_cron)
            logger.info(f"Linux cron görevi silindi: {job_name}")
            return True
        except Exception as e:
            logger.error(f"Linux cron görevi silinirken hata: {e}")
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Neden: crontab içindeki zamanlanmış işleri listelemek.
        """
        jobs = []
        try:
            cron_content = self._get_crontab()
            for line in cron_content.splitlines():
                if "#" in line:
                    parts = line.split("#", 1)
                    cron_part = parts[0].strip()
                    comment_part = parts[1].strip()
                    
                    jobs.append({
                        "name": comment_part,
                        "schedule": cron_part,
                        "command": cron_part.split(None, 5)[-1] if len(cron_part.split()) >= 6 else cron_part
                    })
        except Exception as e:
            logger.error(f"Cron listesi alınırken hata: {e}")
        return jobs

    def _get_crontab(self) -> str:
        try:
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            return res.stdout if res.returncode == 0 else ""
        except Exception:
            return ""

    def _write_crontab(self, content: str) -> None:
        subprocess.run(["crontab", "-"], input=content, text=True, check=True)
