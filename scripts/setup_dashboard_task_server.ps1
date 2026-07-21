# SolarReportAutomation - Dashboard kalici calisma kurulumu (PROD sunucu)
# Kullanim: Sunucuda (APPS) YONETICI PowerShell'de bir kez calistirilir:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_dashboard_task_server.ps1
# Yaptiklari:
#   1. .venv ve .env on kontrolleri (port/erisim modu uyarilari)
#   2. SolarReportAutomation_Dashboard gorevini kurar:
#      - Tetikleyici: sistem acilisinda (AtStartup), SYSTEM hesabi (oturum acilmasi gerekmez)
#      - Cokme durumunda 3 deneme / 1 dk arayla otomatik restart
#      - Sure limiti kapali (varsayilan 72 saat limiti sunucuyu oldururdu)
#   3. 8081 icin gelen (inbound) firewall kurali acar
#   4. Gorevi baslatir ve dogrular (port + HTTP)

$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
$taskName = 'SolarReportAutomation_Dashboard'

Write-Host "Proje koku: $proj"

# --- 1. On kontroller ---
if (-not (Test-Path "$proj\.venv\Scripts\python.exe")) {
    Write-Host "HATA: .venv bulunamadi. Once sanal ortami kurun:" -ForegroundColor Red
    Write-Host "  python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path "$proj\.env")) {
    Write-Host "HATA: .env bulunamadi. Prod .env dosyasini olusturun." -ForegroundColor Red
    exit 1
}
$envLines = Get-Content "$proj\.env"
$port = ($envLines | Where-Object { $_ -match '^DASHBOARD_PORT=' }) -replace '^DASHBOARD_PORT=', ''
$mode = ($envLines | Where-Object { $_ -match '^DASHBOARD_ACCESS_MODE=' }) -replace '^DASHBOARD_ACCESS_MODE=', ''
if ($port -ne '8081') { Write-Host "UYARI: DASHBOARD_PORT=$port (beklenen: 8081)" -ForegroundColor Yellow }
if ($mode -ne 'network') { Write-Host "UYARI: DASHBOARD_ACCESS_MODE=$mode (beklenen: network, yoksa LAN erisimi olmaz!)" -ForegroundColor Yellow }

# --- 2. Zamanlanmis gorev ---
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Host "Mevcut gorev kaldiriliyor (yeniden kurulacak)..."
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
# Gorev durdurulsa da python cocuk process'i portu tutmaya devam edebiliyor - temizle
$leftover = netstat -ano | Select-String ':8081.*LISTENING'
foreach ($line in $leftover) {
    $procId = ($line.ToString().Trim() -split '\s+')[-1]
    Write-Host "8081'i tutan eski process sonlandiriliyor (PID $procId)..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
$action   = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$proj\scripts\run_dashboard_hidden.vbs`"" -WorkingDirectory $proj
$trigger  = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Host "Gorev kuruldu: $taskName (AtStartup, SYSTEM)" -ForegroundColor Green

# --- 3. Firewall ---
$fwName = 'SolarReportAutomation Dashboard 8081'
if (-not (Get-NetFirewallRule -DisplayName $fwName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $fwName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8081 | Out-Null
    Write-Host "Firewall kurali eklendi: $fwName" -ForegroundColor Green
} else {
    Write-Host "Firewall kurali zaten var: $fwName"
}

# --- 4. Baslat ve dogrula ---
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5
$listening = netstat -ano | Select-String ':8081.*LISTENING'
if ($listening) {
    Write-Host "Port 8081 dinleniyor:" -ForegroundColor Green
    $listening | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "HATA: 8081 dinlenmiyor! logs\app.log kontrol edin." -ForegroundColor Red
    exit 1
}
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:8081' -UseBasicParsing -TimeoutSec 10
    Write-Host "HTTP testi: $($r.StatusCode) OK" -ForegroundColor Green
} catch {
    Write-Host "HTTP testi BASARISIZ: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "Kurulum tamam. Kullanicilar ayni agdan http://10.0.0.169:8081 adresine erisebilir." -ForegroundColor Green
Write-Host "Not: .env icindeki DASHBOARD_URL=http://10.0.0.169:8081 olmali (e-posta linkleri bunu kullanir)."
