@echo off
cd /d "%~dp0.."

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi!
    exit /b 1
)

call .venv\Scripts\activate.bat
python scripts/test_smtp.py
exit /b %errorlevel%
