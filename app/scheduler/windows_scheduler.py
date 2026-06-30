import subprocess
import csv
from typing import List, Dict, Any
from app.scheduler.interface import IScheduler
from app.core.logger import setup_logger

logger = setup_logger("WindowsTaskScheduler")

class WindowsTaskScheduler(IScheduler):
    """
    Neden: Windows Task Scheduler (Görev Zamanlayıcı) servisini 
    'schtasks' komut satırı aracı üzerinden yönetmek.
    """
    def register_job(self, job_name: str, schedule_time: str, command: str) -> bool:
        """
        Neden: Belirli bir saatte (HH:MM formatında) çalışacak şekilde görevi sisteme eklemek.
        """
        try:
            # Örnek: schtasks /create /tn "SolarETLJob" /tr "C:\...\python.exe main.py" /sc daily /st 08:30 /f
            cmd = [
                "schtasks", "/create",
                "/tn", job_name,
                "/tr", command,
                "/sc", "daily",
                "/st", schedule_time,
                "/f"
            ]
            logger.info(f"Windows Görev Zamanlayıcısına görev ekleniyor: {job_name} ({schedule_time})")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Görev başarıyla eklendi: {result.stdout.strip()}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Windows görevi eklenirken hata: {e.stderr.strip()}")
            return False
        except Exception as e:
            logger.error(f"Beklenmeyen hata: {e}")
            return False

    def remove_job(self, job_name: str) -> bool:
        """
        Neden: Tanımlanmış bir görevi sistemden silmek.
        """
        try:
            cmd = ["schtasks", "/delete", "/tn", job_name, "/f"]
            logger.info(f"Windows Görev Zamanlayıcısından görev siliniyor: {job_name}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Görev başarıyla silindi: {result.stdout.strip()}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Windows görevi silinirken hata: {e.stderr.strip()}")
            return False
        except Exception as e:
            logger.error(f"Beklenmeyen hata: {e}")
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Neden: Sistemdeki görevleri sorgulayıp listelemek.
        """
        jobs = []
        try:
            cmd = ["schtasks", "/query", "/fo", "csv", "/v"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # CSV formatını parse et
            reader = csv.reader(result.stdout.strip().splitlines())
            header = next(reader, None)
            if header:
                for row in reader:
                    if len(row) >= len(header):
                        job_dict = dict(zip(header, row))
                        # Sadece bizim projeye ait olan veya isminde eşleşenleri filtreleyebiliriz
                        jobs.append({
                            "name": job_dict.get("TaskName", ""),
                            "next_run": job_dict.get("Next Run Time", ""),
                            "status": job_dict.get("Status", ""),
                            "command": job_dict.get("Task To Run", "")
                        })
        except Exception as e:
            logger.error(f"Görevler sorgulanırken hata: {e}")
        return jobs
