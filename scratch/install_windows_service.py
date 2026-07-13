"""
SolarReportAutomation Dashboard - Windows Servis Kurulumu
Çalıştırma (Admin PowerShell): 
  python scratch/install_windows_service.py install
  python scratch/install_windows_service.py start
"""

import sys
import os

SERVICE_NAME = "SolarDashboard"
SERVICE_DISPLAY = "Solar Report Automation Dashboard"
SERVICE_DESC = "GES Enerji Yönetim Sistemi Dashboard"

def install_service():
    project_dir = r"C:\Projects\SolarReportAutomation"
    python_exe = r"C:\Projects\SolarReportAutomation\.venv\Scripts\python.exe"
    
    # NSSM ile servis kur (Non-Sucking Service Manager)
    # Önce NSSM indir
    nssm_url = "https://nssm.cc/release/nssm-2.24.zip"
    nssm_dir = r"C:\nssm"
    nssm_exe = r"C:\nssm\nssm-2.24\win64\nssm.exe"
    
    print("NSSM indiriliyor...")
    import urllib.request
    import zipfile
    
    os.makedirs(nssm_dir, exist_ok=True)
    zip_path = r"C:\nssm\nssm.zip"
    urllib.request.urlretrieve(nssm_url, zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(nssm_dir)
    
    print("Servis kuruluyor...")
    os.system(f'"{nssm_exe}" install {SERVICE_NAME} "{python_exe}"')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} AppParameters "-c \\"from app.dashboard.web_server import start_dashboard_server; start_dashboard_server(port=8081)\\""')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} AppDirectory "{project_dir}"')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} DisplayName "{SERVICE_DISPLAY}"')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} Description "{SERVICE_DESC}"')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} Start SERVICE_AUTO_START')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} AppStdout "{project_dir}\\logs\\dashboard.log"')
    os.system(f'"{nssm_exe}" set {SERVICE_NAME} AppStderr "{project_dir}\\logs\\dashboard_error.log"')
    
    print(f"Servis kuruldu: {SERVICE_NAME}")
    print("Başlatmak için: python scratch/install_windows_service.py start")

def start_service():
    nssm_exe = r"C:\nssm\nssm-2.24\win64\nssm.exe"
    os.system(f'"{nssm_exe}" start {SERVICE_NAME}')
    print(f"Servis başlatıldı: {SERVICE_NAME}")

def stop_service():
    nssm_exe = r"C:\nssm\nssm-2.24\win64\nssm.exe"
    os.system(f'"{nssm_exe}" stop {SERVICE_NAME}')
    print(f"Servis durduruldu: {SERVICE_NAME}")

def remove_service():
    nssm_exe = r"C:\nssm\nssm-2.24\win64\nssm.exe"
    os.system(f'"{nssm_exe}" remove {SERVICE_NAME} confirm')
    print(f"Servis kaldırıldı: {SERVICE_NAME}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python install_windows_service.py [install|start|stop|remove]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "install":
        install_service()
    elif cmd == "start":
        start_service()
    elif cmd == "stop":
        stop_service()
    elif cmd == "remove":
        remove_service()
    else:
        print(f"Bilinmeyen komut: {cmd}")
