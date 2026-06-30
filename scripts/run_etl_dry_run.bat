@echo off
cd /d "%~dp0.."

echo ===== TEST ETL PIPELINE (DRY-RUN / SKIP DOWNLOAD) =====
echo Tarih: %date% %time%

if not exist .venv (
    echo Hata: .venv sanal ortam klasoru bulunamadi! Lutfen once kurulumu tamamlayin.
    exit /b 1
)

:: Sanal ortamı aktive et
call .venv\Scripts\activate.bat

:: ETL Pipeline'ı test modu (dry-run ve skip-download) ile çalıştır
python main.py --mode dry-run --skip-download true %*

set EXIT_CODE=%errorlevel%
echo.
echo Test ETL Pipeline tamamlandi. Cikis Kodu: %EXIT_CODE%
exit /b %EXIT_CODE%
