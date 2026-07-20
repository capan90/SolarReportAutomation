@echo off
REM ------------------------------------------------------------------
REM SolarReportAutomation - Gunluk mahsuplasma job'u (Windows Task Scheduler girisi)
REM Neden: Task Scheduler varsayilan olarak System32'den calisir; goreli yollarin
REM (outputs/, config/gaosb_browser_profile/) bozulmamasi icin cwd'yi bu .bat
REM dosyasinin bulundugu proje kokune sabitliyoruz.
REM ------------------------------------------------------------------
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py --settlement
