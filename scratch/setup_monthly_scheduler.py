"""
Aylık settlement job'unu Windows Task Scheduler'a kaydeder.
Her ayın 1'i saat 08:30'da çalışır (geçen ayı raporlar). Bir kez çalıştırılır.

Not: scratch/setup_scheduler.py artık günlük + aylık görevlerin ikisini de
kaydeder; bu script yalnızca aylık görevi tek başına kurmak için kalmıştır.

Çalıştırma: .venv/Scripts/python.exe scratch/setup_monthly_scheduler.py
"""
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

project_dir = Path(__file__).parent.parent.resolve()
python_exe = project_dir / ".venv" / "Scripts" / "python.exe"
main_py = project_dir / "main.py"

JOB_NAME = "SolarReportAutomation_MonthlySettlement"
# Neden: Ayın 1'inde koşan job, --settlement-month verilmediğinde geçen ayı
# hedefler; böylece tamamlanmış ayın raporu üretilir.
command = f'"{python_exe}" "{main_py}" --settlement-monthly'

def run_schtasks(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, errors="ignore"
    )

# Önce varsa sil (yoksa hata vermez, bilgi yazar)
delete = run_schtasks(["schtasks", "/Delete", "/TN", JOB_NAME, "/F"])
if delete.returncode == 0:
    print(f"Eski görev silindi: {JOB_NAME}")
else:
    print(f"Eski görev temizleme bilgisi: {(delete.stderr or delete.stdout).strip()}")

# Her ayın 1'i 08:30 — schtasks MONTHLY + /D 1 + /M * (tüm aylar)
create = run_schtasks([
    "schtasks", "/Create", "/F",
    "/TN", JOB_NAME,
    "/TR", command,
    "/SC", "MONTHLY",
    "/D", "1",
    "/M", "*",
    "/ST", "08:30",
])

if create.returncode == 0:
    print(f"Görev kaydedildi: {JOB_NAME}")
    print("Zamanlama: her ayın 1'i 08:30")
    print(f"Komut: {command}")
else:
    print(f"HATA: Görev kaydedilemedi: {(create.stderr or create.stdout).strip()}")
    sys.exit(1)

# Doğrulama: görevi listele
query = run_schtasks(["schtasks", "/Query", "/TN", JOB_NAME, "/V", "/FO", "LIST"])
print("\nGörev detayı:")
for line in (query.stdout or "").splitlines():
    if any(k in line for k in ("TaskName", "Schedule", "Start Time", "Months", "Days", "Task To Run", "Next Run Time")):
        print("  " + line.strip())
