@echo off
echo ===== SolarReportAutomation Servisleri Durduruluyor =====

:: Dashboard sunucusunu pencere basligina gore sonlandir
taskkill /fi "windowtitle eq SolarDashboardServer*" /f /t >nul 2>&1

:: Alternatif olarak komut satiri icerigine gore sonlandir (Penceresiz calisma durumlari icin)
wmic process where "CommandLine like '%%web_server%%'" call terminate >nul 2>&1

echo Servisler basariyla durduruldu.
exit /b 0
