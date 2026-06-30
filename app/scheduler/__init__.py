import sys
from app.scheduler.interface import IScheduler
from app.scheduler.windows_scheduler import WindowsTaskScheduler
from app.scheduler.linux_cron_scheduler import LinuxCronScheduler

def get_scheduler() -> IScheduler:
    """
    Neden: Çalışma zamanındaki işletim sistemine uygun scheduler
    implementasyonunu döndürmek (Simple Factory).
    """
    if sys.platform.startswith("win"):
        return WindowsTaskScheduler()
    else:
        return LinuxCronScheduler()

__all__ = [
    "IScheduler",
    "get_scheduler"
]
