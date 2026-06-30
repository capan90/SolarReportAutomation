@echo off
:: Neden: Dizin tespit edip projenin kök dizinine geçmek
cd /d "%~dp0.."

echo ===== ETL Pipeline baslatiliyor =====
echo Tarih: %date% %time%

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi! Lutfen once kurulumu tamamlayin.
    exit /b 1
)

:: Sanal ortami aktive et
call .venv\Scripts\activate.bat

:: logs klasörünün varlığından emin ol
if not exist logs (
    mkdir logs
)

:: ETL Pipeline calistir
python main.py %* > logs\etl_scheduler.log 2>&1
set EXIT_CODE=%errorlevel%

echo ETL Pipeline tamamlandi. Cikis Kodu: %EXIT_CODE%
echo Detayli loglar logs\etl_scheduler.log dosyasina kaydedildi.

exit /b %EXIT_CODE%
