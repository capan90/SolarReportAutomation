"""
Santral durum izleme (plant status) job'unu Windows Task Scheduler'a kaydeder.
Çalıştırma: .venv/Scripts/python.exe scratch/setup_plant_status_scheduler.py
"""
import sys
import subprocess
from pathlib import Path

# Proje kök dizini ve python yolu
project_dir = Path(__file__).parent.parent.resolve()
python_exe = project_dir / ".venv" / "Scripts" / "python.exe"
main_py = project_dir / "main.py"

status_command = f'"{python_exe}" "{main_py}" --plant-status'
status_job_name = "SolarReportAutomation_PlantStatus"

def run_schtasks(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, errors="ignore")

# Önce eskiyi temizle
delete = run_schtasks(["schtasks", "/Delete", "/TN", status_job_name, "/F"])
if delete.returncode == 0:
    print(f"Eski görev silindi: {status_job_name}")
else:
    print(f"Eski görev temizleme bilgisi: {(delete.stderr or delete.stdout).strip()}")

# Yeniyi kaydet (her 15 dakikada bir çalışacak)
create = run_schtasks([
    "schtasks", "/Create", "/F",
    "/TN", status_job_name,
    "/TR", status_command,
    "/SC", "MINUTE",
    "/MO", "15",
])

if create.returncode == 0:
    print(f"Görev başarıyla kaydedildi: {status_job_name}")
    print("Zamanlama: Her 15 dakikada bir")
    print(f"Komut: {status_command}")
else:
    print(f"HATA: Görev kaydedilemedi: {(create.stderr or create.stdout).strip()}")
    sys.exit(1)
