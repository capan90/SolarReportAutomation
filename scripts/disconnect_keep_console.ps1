# SolarReportAutomation - RDP oturumunu masaustunu oldurmeden kapatma (PROD sunucu)
#
# Sorun: RDP penceresi X ile kapatilinca oturum "disconnected" durumuna duser;
# aktif masaustu kalmadigi icin zamanlanmis islerin acmasi gereken GORUNUR tarayici
# (GAOSB headed fallback / captcha yenileme) baslatilamaz ve launch timeout olur
# (2026-07-23 olayi).
#
# Cozum: RDP'den cikarken pencereyi X ile KAPATMAK YERINE bu script calistirilir.
# Oturum fiziksel konsola devredilir (tscon); masaustu aktif kalir, RDP baglantisi
# otomatik kapanir. Parola ve kilit politikasina DOKUNMAZ.
#
# Kullanim (sunucuda, apps kullanicisiyla):
#   Masaustune kisayol olarak koyun; cikarken cift tiklayin.
#   Yonetici yetkisi gerekir - script kendini otomatik yukseltir (UAC onayi cikar).
#
# Not: Devir sonrasi konsol ekrani (Hyper-V/VMware konsolundan bakan icin) acik
# kalir; hipervizör erisimi zaten yonetici kontrolunde oldugundan kabul edilen risk.

$ErrorActionPreference = 'Stop'

# Yonetici degilse kendini yukselterek yeniden baslat
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    )
    exit
}

# RDP oturumunda degilsek (zaten konsoldaysak) yapacak is yok
$sessionName = $env:SESSIONNAME
if (-not $sessionName -or $sessionName -notmatch '^rdp-tcp') {
    Write-Host "Bu oturum RDP degil ($sessionName); devir gerekmiyor." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    exit
}

$sessionId = (Get-Process -Id $PID).SessionId
Write-Host "RDP oturumu ($sessionName, ID=$sessionId) konsola devrediliyor..."
tscon $sessionId /dest:console
# Basarili olursa RDP baglantisi bu satirdan sonra otomatik kopar.
if ($LASTEXITCODE -ne 0) {
    Write-Host "tscon basarisiz oldu (cikis kodu: $LASTEXITCODE)." -ForegroundColor Red
    Start-Sleep -Seconds 10
    exit 1
}
