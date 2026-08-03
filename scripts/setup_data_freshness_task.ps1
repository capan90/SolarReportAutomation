# SolarReportAutomation - Veri-eksik kontrolu zamanlanmis gorev kurulumu (PROD sunucu)
# Kullanim: Sunucuda (APPS) YONETICI PowerShell'de bir kez calistirilir:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_data_freshness_task.ps1
#
# Neden: 2026-08-03 09:00 kosusu tarayici kapanisinda asildi. Surec YASADIGI icin istisna
# olusmadi, mevcut alarm yollarinin hicbiri tetiklenmedi ve 2 Agustos verisi sessizce eksik
# kaldi. Bu gorev ETL'den BAGIMSIZ kosar ve yalnizca sonuca bakar: dunun verisi var mi, tam mi.
#
# Kurulum kararlari:
#   - Saat 09:30: gunluk is 09:00'da basliyor, gozlenen en uzun kosu ~104 sn -> 30 dk pay.
#   - SYSTEM hesabi: ETL gorevleri InteractiveToken ile kosuyor; kontrol de oyle olsaydi
#     kullanici oturum acmadiginda ETL ile BIRLIKTE sessiz kalirdi. Izleyicinin izlenenle
#     ayni kirilganligi paylasmamasi sart. Tarayici kullanmadigi icin SYSTEM'de risk yok.
#   - ExecutionTimeLimit PT10M: salt-okunur DB sorgusu saniyeler surer; asilirsa ertesi
#     gunun kontrolu IgnoreNew yuzunden atlanmasin.
#   - Exit kodu 6 = veri eksik (mail gitti), 0 = tamam, 1 = kontrolun kendisi kosamadi.

$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
$taskName = 'SolarReportAutomation_DataFreshness'

Write-Host "Proje koku: $proj"

# --- 1. On kontroller ---
if (-not (Test-Path "$proj\.venv\Scripts\python.exe")) {
    Write-Host "HATA: .venv bulunamadi. Once sanal ortami kurun." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "$proj\.env")) {
    Write-Host "HATA: .env bulunamadi. Prod .env dosyasini olusturun." -ForegroundColor Red
    exit 1
}
# Neden: Kontrolun tek cikti kanali mail; alici tanimli degilse gorev sessizce ise yaramaz
# hale gelir. Kurulumda yakalanmali (SMTP_TO_SYSTEM yoksa SMTP_TO'ya dusuluyor).
$envLines = Get-Content "$proj\.env"
$toSystem = ($envLines | Where-Object { $_ -match '^SMTP_TO_SYSTEM=' }) -replace '^SMTP_TO_SYSTEM=', ''
$toFallback = ($envLines | Where-Object { $_ -match '^SMTP_TO=' }) -replace '^SMTP_TO=', ''
if (-not "$toSystem".Trim() -and -not "$toFallback".Trim()) {
    Write-Host "HATA: .env icinde SMTP_TO_SYSTEM veya SMTP_TO yok - uyari maili gonderilemez." -ForegroundColor Red
    exit 1
}

# --- 2. Zamanlanmis gorev ---
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Host "Mevcut gorev kaldiriliyor (yeniden kurulacak)..."
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$action = New-ScheduledTaskAction -Execute "$proj\.venv\Scripts\python.exe" `
    -Argument "`"$proj\main.py`" --check-data" -WorkingDirectory $proj
$trigger = New-ScheduledTaskTrigger -Daily -At '09:30'
$principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings | Out-Null
Write-Host "Gorev kuruldu: $taskName (her gun 09:30, SYSTEM)" -ForegroundColor Green

# --- 3. Dogrulama: bilinen bir gun uzerinde simdi kosturulur ---
# Neden: Gorevin kurulmus olmasi calistigini kanitlamaz. Dun icin kontrol burada bir kez
# elle kosturulur; boylece DB erisimi, .env okumasi ve exit kodu kurulum aninda sinanir.
$yesterday = (Get-Date).AddDays(-1).ToString('yyyy-MM-dd')
Write-Host ""
Write-Host "Dogrulama kosusu ($yesterday):" -ForegroundColor Cyan
& "$proj\.venv\Scripts\python.exe" "$proj\main.py" --check-data --check-date $yesterday
$code = $LASTEXITCODE
switch ($code) {
    0 { Write-Host "Sonuc: veri tam (exit 0). Kurulum dogrulandi." -ForegroundColor Green }
    6 { Write-Host "Sonuc: VERI EKSIK (exit 6) - uyari maili gonderildi. Kontrol calisiyor." -ForegroundColor Yellow }
    default {
        Write-Host "HATA: kontrol kosamadi (exit $code). Gorev kuruldu ama dogrulanamadi." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Kurulum tamam." -ForegroundColor Green
Write-Host "Elle kosturmak icin:  .venv\Scripts\python.exe main.py --check-data --check-date YYYY-MM-DD"
