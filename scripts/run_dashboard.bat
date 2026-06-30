@echo off
:: Neden: Dizin tespit edip projenin kök dizinine geçmek
cd /d "%~dp0.."

:: Varsayılan Değerler
set DASHBOARD_PORT=8080
set DASHBOARD_ACCESS_MODE=localhost

:: .env dosyasından parametreleri oku
if exist .env (
    for /f "usebackq tokens=1,2 delims==" %%i in (".env") do (
        if "%%i"=="DASHBOARD_PORT" set DASHBOARD_PORT=%%j
        if "%%i"=="DASHBOARD_ACCESS_MODE" set DASHBOARD_ACCESS_MODE=%%j
    )
)

:: Boşlukları temizle
set DASHBOARD_PORT=%DASHBOARD_PORT: =%
set DASHBOARD_ACCESS_MODE=%DASHBOARD_ACCESS_MODE: =%

echo ===== Dashboard Web Sunucusu baslatiliyor =====
if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi!
    exit /b 1
)

:: Sanal ortamı aktive et
call .venv\Scripts\activate.bat

:: Logs dizinini oluştur
if not exist logs (
    mkdir logs
)

:: Sunucuyu arka planda başlat
start "SolarDashboardServer" /min python -m app.dashboard.web_server

:: Sunucunun ayağa kalkması için 2 saniye bekle ve tarayıcıda aç
timeout /t 2 /nobreak >nul
echo Tarayici otomatik olarak aciliyor...
start http://127.0.0.1:%DASHBOARD_PORT%

echo Dashboard basariyla baslatildi.
exit /b 0
