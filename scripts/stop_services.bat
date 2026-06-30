@echo off
echo ===== SolarReportAutomation Servisleri Durduruluyor =====

:: Dashboard sunucusunu pencere basligina gore sonlandir
taskkill /fi "windowtitle eq SolarDashboardServer*" /f /t >nul 2>&1

echo Servisler basariyla durduruldu.
exit /b 0
