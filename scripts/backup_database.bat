@echo off
:: Neden: Dizin tespit edip projenin kök dizinine geçmek
cd /d "%~dp0.."

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi! Lutfen once kurulumu tamamlayin.
    exit /b 1
)

:: Sanal ortami aktive et
call .venv\Scripts\activate.bat

:: Yedekleme scriptini çalıştır
python scripts/db_backup.py
exit /b %errorlevel%
