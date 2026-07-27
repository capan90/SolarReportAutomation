# SolarReportAutomation - Dashboard'i GUVENLI sekilde yeniden baslat
#
# Kullanim (YONETICI PowerShell, proje kokunde):
#   powershell -ExecutionPolicy Bypass -File .\scripts\restart_dashboard.ps1
#
# NEDEN BU SCRIPT VAR:
# Duz "Stop-ScheduledTask + Start-ScheduledTask" GUVENLI DEGILDIR. Gorev
# wscript.exe'yi baslatir, o da python.exe'yi calistirir. Task Scheduler gorevi
# durdurdugunda wscript.exe olur ama python.exe COCUK PROCESS'I HAYATTA KALABILIR
# ve 8081'i tutmaya devam eder. Sonraki baslatma WinError 10048 alir; VBS dongusu
# 4 deneme sonra pes eder ve dashboard TAMAMEN KAPALI kalir (2026-07-27 olayi).
#
# Bu script portun gercekten bosaldigini dogrulayarak bu tuzagi kapatir.
# Kurulum scripti (setup_dashboard_task_server.ps1) da baslatma asamasinda
# BU script'i cagirir - boylece restart yolu her kurulumda sinanmis olur.

param(
    [int]$Port = 8081,
    [string]$TaskName = 'SolarReportAutomation_Dashboard',
    # Neden: Kurulum scripti gorevi zaten yeni kurmustur; tekrar durdurmasi gereksiz.
    [switch]$SkipStop
)

$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot

function Get-PortOwners {
    param([int]$P)
    # Neden: Get-NetTCPConnection her Windows surumunde/SKU'sunda yok; netstat
    # her yerde var. Ikisi de denenir, once modern olan.
    try {
        return @(Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction Stop |
                 Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $lines = netstat -ano | Select-String ":$P.*LISTENING"
        return @($lines | ForEach-Object { ($_.ToString().Trim() -split '\s+')[-1] } |
                 Sort-Object -Unique)
    }
}

Write-Host "Proje koku: $proj"
Write-Host "Gorev: $TaskName | Port: $Port"
Write-Host ""

# --- 1. Gorevi durdur ---
if (-not $SkipStop) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Write-Host "Gorev durduruluyor..."
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    } else {
        Write-Host "UYARI: '$TaskName' gorevi kayitli degil." -ForegroundColor Yellow
        Write-Host "  Kurulum icin: .\scripts\setup_dashboard_task_server.ps1" -ForegroundColor Yellow
        exit 1
    }
}

# --- 2. Portu tutan artik process'leri sonlandir ---
# Neden: Asil mesele bu. Gorev "durduruldu" gorunse de python cocugu portu
# tutuyor olabilir; oldurulmeden yeni instance baglanamaz.
$owners = Get-PortOwners -P $Port
if ($owners.Count -gt 0) {
    foreach ($procId in $owners) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        $desc = if ($p) { "$($p.Name), baslangic $($p.CreationDate)" } else { "bilinmiyor" }
        Write-Host "$Port portunu tutan process sonlandiriliyor (PID $procId - $desc)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "$Port portunu tutan process yok."
}

# --- 3. Port GERCEKTEN bosaldi mi ---
# Neden: Process oldurulunce port aninda serbest kalmayabilir (TIME_WAIT / handle
# kapanma gecikmesi). Beklemeden baslatmak ayni 10048 hatasini uretir.
$freed = $false
for ($i = 1; $i -le 20; $i++) {
    if ((Get-PortOwners -P $Port).Count -eq 0) { $freed = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $freed) {
    Write-Host "HATA: $Port portu 20 saniyede bosalmadi. Portu tutan process:" -ForegroundColor Red
    Get-PortOwners -P $Port | ForEach-Object {
        Get-CimInstance Win32_Process -Filter "ProcessId=$_" -ErrorAction SilentlyContinue |
            Select-Object ProcessId, Name, CreationDate, CommandLine | Format-List
    }
    Write-Host "  Elle sonlandirip script'i tekrar calistirin." -ForegroundColor Yellow
    exit 1
}
Write-Host "Port $Port serbest." -ForegroundColor Green

# --- 4. Baslat ---
Write-Host "Gorev baslatiliyor..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

# --- 5. Dogrula: once port, sonra HTTP ---
$listening = $false
for ($i = 1; $i -le 15; $i++) {
    if ((Get-PortOwners -P $Port).Count -gt 0) { $listening = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $listening) {
    Write-Host "HATA: $Port dinlenmiyor! Son loglar:" -ForegroundColor Red
    # Neden: Dashboard kendi dosyasina yazar; app.log yalnizca zamanlanmis ETL kosulari.
    $dashLog = Join-Path $proj 'logs\dashboard.log'
    if (Test-Path $dashLog) { Get-Content $dashLog -Tail 15 } else { Write-Host "  $dashLog yok." }
    exit 1
}

try {
    $r = Invoke-WebRequest -Uri "http://localhost:$Port" -UseBasicParsing -TimeoutSec 10
    Write-Host "HTTP testi: $($r.StatusCode) OK" -ForegroundColor Green
} catch {
    Write-Host "HTTP testi BASARISIZ: $($_.Exception.Message)" -ForegroundColor Red
    $dashLog = Join-Path $proj 'logs\dashboard.log'
    if (Test-Path $dashLog) { Get-Content $dashLog -Tail 15 }
    exit 1
}

$pids = (Get-PortOwners -P $Port) -join ', '
Write-Host ""
Write-Host "Dashboard ayakta (PID: $pids)." -ForegroundColor Green
Write-Host "Loglar: logs\dashboard.log"
