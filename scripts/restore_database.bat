@echo off
:: Neden: Dizin tespit edip projenin kök dizinine geçmek
cd /d "%~dp0.."

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi! Lutfen once kurulumu tamamlayin.
    exit /b 1
)

:: Sanal ortami aktive et
call .venv\Scripts\activate.bat

:: Geri yükleme scriptini çalıştır (Parametreleri ilet)
python scripts/db_restore.py %*
exit /b %errorlevel%
