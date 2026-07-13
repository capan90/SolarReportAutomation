@echo off
echo Guncelleme basliyor...
cd C:\Projects\SolarReportAutomation
git pull
.venv\Scripts\pip install -r requirements.txt --quiet
echo Guncelleme tamamlandi!
pause
