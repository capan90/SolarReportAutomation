"""
Settlement job'larını Windows Task Scheduler'a kaydeder. Bir kez çalıştırılır.

- SolarReportAutomation_DailySettlement  : her gün 09:00
- SolarReportAutomation_MonthlySettlement: her ayın 1'i 08:30 (geçen ayı raporlar)

Çalıştırma: .venv/Scripts/python.exe scratch/setup_scheduler.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Neden: Windows Türkçe dil/kod sayfası (CP1254/CP857) nedeniyle subprocess
# çıktılarında oluşan UnicodeDecodeError hatasını gidermek için subprocess.run'ı yamala.
import subprocess
original_run = subprocess.run
def patched_run(*args, **kwargs):
    if kwargs.get('text') or kwargs.get('universal_newlines'):
        kwargs['errors'] = 'ignore'
    return original_run(*args, **kwargs)
subprocess.run = patched_run

from app.scheduler import get_scheduler

# Proje kök dizini ve python yolu
project_dir = Path(__file__).parent.parent.resolve()
python_exe = project_dir / ".venv" / "Scripts" / "python.exe"
main_py = project_dir / "main.py"

# ------------------------------------------------------------------
# 1) Günlük settlement — her gün 09:00
# ------------------------------------------------------------------
daily_command = f'"{python_exe}" "{main_py}" --settlement'
daily_time = "09:00"
daily_job_name = "SolarReportAutomation_DailySettlement"

scheduler = get_scheduler()

try:
    scheduler.remove_job(daily_job_name)
except Exception as e:
    print(f"Eski günlük görev temizleme bilgisi: {e}")

success = scheduler.register_job(
    job_name=daily_job_name,
    schedule_time=daily_time,
    command=daily_command
)

if success:
    print(f"Görev kaydedildi: {daily_job_name}")
    print(f"Çalışma saati: her gün {daily_time}")
    print(f"Komut: {daily_command}")
else:
    print("HATA: Günlük görev kaydedilemedi.")
    sys.exit(1)

# ------------------------------------------------------------------
# 2) Aylık settlement — her ayın 1'i 08:30
# Neden: Ayın 1'inde koşan job, --settlement-month verilmediğinde geçen ayı
# hedefler; böylece tamamlanmış ayın raporu üretilir.
# ------------------------------------------------------------------
monthly_command = f'"{python_exe}" "{main_py}" --settlement-monthly'
monthly_job_name = "SolarReportAutomation_MonthlySettlement"

def run_schtasks(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, errors="ignore")

delete = run_schtasks(["schtasks", "/Delete", "/TN", monthly_job_name, "/F"])
if delete.returncode == 0:
    print(f"\nEski aylık görev silindi: {monthly_job_name}")
else:
    print(f"\nEski aylık görev temizleme bilgisi: {(delete.stderr or delete.stdout).strip()}")

create = run_schtasks([
    "schtasks", "/Create", "/F",
    "/TN", monthly_job_name,
    "/TR", monthly_command,
    "/SC", "MONTHLY",
    "/D", "1",
    "/M", "*",
    "/ST", "08:30",
])

if create.returncode == 0:
    print(f"Görev kaydedildi: {monthly_job_name}")
    print("Zamanlama: her ayın 1'i 08:30")
    print(f"Komut: {monthly_command}")
else:
    print(f"HATA: Aylık görev kaydedilemedi: {(create.stderr or create.stdout).strip()}")
    sys.exit(1)

# ------------------------------------------------------------------
# Doğrulama: kayıtlı Solar görevlerini listele
# ------------------------------------------------------------------
jobs = scheduler.list_jobs()
solar_jobs = [j for j in jobs if "Solar" in j.get("name", "")]
print(f"\nKayıtlı Solar görevler: {len(solar_jobs)}")
for j in solar_jobs:
    print(f"  - {j}")
