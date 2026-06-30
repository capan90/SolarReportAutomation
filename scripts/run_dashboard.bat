@echo off
:: Neden: Dizin tespit edip projenin kök dizinine geçmek
cd /d "%~dp0.."

echo ===== Dashboard Web Sunucusu baslatiliyor =====

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi!
    exit /b 1
)

:: Sanal ortami aktive et
call .venv\Scripts\activate.bat

:: logs klasörünün varlığından emin ol
if not exist logs (
    mkdir logs
)

:: Dashboard sunucusunu baslat (Arka planda minimize edilmis pencere olarak)
start "SolarDashboardServer" /min python app/dashboard/web_server.py

echo Dashboard Web Sunucusu arka planda baslatildi.
echo Durdurmak veya yeniden baslatmak icin stop_services.bat betigini kullanabilirsiniz.
exit /b 0
