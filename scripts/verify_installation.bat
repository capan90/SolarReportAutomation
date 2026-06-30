@echo off
:: Neden: Dizin tespit edip projenin kök dizinine geçmek
cd /d "%~dp0.."

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi! Lutfen once kurulumu tamamlayin.
    exit /b 1
)

:: Sanal ortami aktive et
call .venv\Scripts\activate.bat

:: Doğrulama scriptini çalıştır
python scripts/verify_installation.py
exit /b %errorlevel%
