"""
Neden: İş watchdog'u `os._exit` ile çıkar — `atexit`, `finally` ve context manager
`__exit__` çalışmaz. Açık kalan Chromium ve Playwright driver süreçleri o anda ORPHAN
kalır; sunucuda birikerek profil kilidi ve bellek sorunu üretirler. Bu yüzden watchdog
çıkmadan ÖNCE kendi tarayıcı süreçlerini toplamak zorunda.

KRİTİK KISIT — yalnızca BU sürecin torunları:
Ada göre geniş bir temizlik ("tüm chromium'ları öldür") prod'da dashboard'ın SYSTEM
hesabında eşzamanlı koşan GAOSB oturumunu vururdu (dashboard 27-28 Temmuz'da tam GAOSB
akışını başarıyla koşturuyor). Bu yüzden süreç ağacı `os.getpid()`'den aşağı yürünür ve
YALNIZCA torun olan tarayıcı süreçleri hedeflenir. Aynı makinedeki başka bir koşunun
tarayıcısı bu kümeye asla giremez.

Not: `GaosbExtractor._kill_stale_profile_processes` bilinçli olarak BURAYA TAŞINMADI.
O fonksiyonun işi ÖNCEKİ koşudan kalan süreçleri öldürmek; onlar tanımı gereği bizim
torunumuz değildir, ağaç daraltması eklenseydi hiçbir şey bulamaz hale gelirdi.
"""
import os
import subprocess
import sys
from typing import Callable, List, Optional

from app.core.logger import setup_logger

logger = setup_logger("BrowserCleanup")

# Neden: Playwright ağacı iki katmandır — node.exe (driver) ve altında chromium süreçleri.
# Ölçülen gerçek isimler: 'node.exe' + 'chrome-headless-shell.exe' (headless) / 'chrome.exe'.
BROWSER_NAME_PATTERN = "^(chrome|chromium|headless_shell|msedge|node)"

# Neden: Süreç ağacını PID→PPID haritasıyla yukarıdan aşağı yürür. Kuyruk + görülenler
# kümesi, PPID döngüsü (nadir ama mümkün) durumunda sonsuz döngüyü engeller.
# Ada göre filtre EN SONDA uygulanır: powershell.exe da bizim çocuğumuzdur ama isim
# desenine uymadığı için hedeflenmez (aksi halde komut kendini öldürürdü).
_TREE_KILL_PS = """
$target = __TARGET_PID__
$procs = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name
$children = @{}
foreach ($p in $procs) {
  $key = [string]$p.ParentProcessId
  if (-not $children.ContainsKey($key)) { $children[$key] = New-Object System.Collections.ArrayList }
  [void]$children[$key].Add($p)
}
$queue = New-Object System.Collections.Queue
$queue.Enqueue([string]$target)
$seen = @{}
$hits = New-Object System.Collections.ArrayList
while ($queue.Count -gt 0) {
  $cur = $queue.Dequeue()
  if ($seen.ContainsKey($cur)) { continue }
  $seen[$cur] = $true
  if ($children.ContainsKey($cur)) {
    foreach ($c in $children[$cur]) {
      $queue.Enqueue([string]$c.ProcessId)
      if ($c.Name -match '__NAME_PATTERN__') { [void]$hits.Add($c.ProcessId) }
    }
  }
}
foreach ($procId in $hits) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
$hits -join ' '
"""


def build_tree_kill_command(target_pid: int) -> str:
    """Neden: Testlerin komutun gerçekten ağaç-daraltmalı olduğunu doğrulayabilmesi için ayrı."""
    return (
        _TREE_KILL_PS
        .replace("__TARGET_PID__", str(target_pid))
        .replace("__NAME_PATTERN__", BROWSER_NAME_PATTERN)
    )


def kill_browser_descendants(
    runner: Optional[Callable] = None,
    timeout_seconds: int = 30,
    target_pid: Optional[int] = None,
) -> List[int]:
    """
    Bu sürecin torunu olan tarayıcı/driver süreçlerini sonlandırır.

    Dönüş: sonlandırılan PID listesi. Best-effort — hiçbir durumda istisna fırlatmaz;
    watchdog'un çıkış yolunu bir temizlik hatası bloklayamaz.
    """
    if sys.platform != "win32":
        return []
    runner = runner or subprocess.run
    pid = os.getpid() if target_pid is None else target_pid
    try:
        out = runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             build_tree_kill_command(pid)],
            capture_output=True, text=True, timeout=timeout_seconds,
        )
        pids = [int(p) for p in (out.stdout or "").split() if p.strip().isdigit()]
        if pids:
            logger.warning(
                "Watchdog temizliği: bu sürecin %d tarayıcı torunu sonlandırıldı (PID: %s)",
                len(pids), ", ".join(str(p) for p in pids),
            )
        else:
            logger.info("Watchdog temizliği: sonlandırılacak tarayıcı torunu yok.")
        return pids
    except Exception as e:
        logger.error("Tarayıcı torunları temizlenemedi (%s): %s", type(e).__name__, e)
        return []
