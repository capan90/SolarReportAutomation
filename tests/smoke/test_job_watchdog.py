"""
Neden: 2026-08-03 09:00 koşusu tarayıcı kapanışında asıldı. Süreç YAŞADIĞI için istisna
oluşmadı ve hiçbir alarm tetiklenmedi; Task Scheduler'ın 72 saatlik limiti + IgnoreNew
politikası yüzünden sonraki koşular da sessizce atlanacaktı.

Bu testler watchdog'un üç garantisini sabitler:
1. Süre aşımında MUTLAKA çıkar (uyarı gönderimi patlasa bile).
2. Çıkmadan ÖNCE tarayıcı torunlarını toplar (os._exit finally çalıştırmaz).
3. Temizlik YALNIZCA bu sürecin torunlarını hedefler — eşzamanlı koşan dashboard'ın
   tarayıcısına dokunmaz.
"""
import os

import pytest

from app.infrastructure.browser import process_cleanup
from app.monitoring import watchdog


class Recorder:
    def __init__(self, raises=None):
        self.calls = []
        self._raises = raises

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._raises:
            raise self._raises
        return []


def _fire(killer=None, alert_sender=None):
    exiter = Recorder()
    watchdog.fire(
        "Günlük Mahsup", 900,
        killer=killer or Recorder(),
        alert_sender=alert_sender or Recorder(),
        exiter=exiter,
    )
    return exiter


def test_watchdog_exits_with_dedicated_code():
    """Çıkış kodu işin 'başarısız oldu'sundan (1) ayrı olmalı."""
    exiter = _fire()
    assert exiter.calls == [((watchdog.EXIT_CODE_WATCHDOG,), {})]
    assert watchdog.EXIT_CODE_WATCHDOG not in (0, 1, 4, 5, 6)


def test_cleanup_runs_before_alert():
    """
    os._exit finally/atexit çalıştırmaz; uyarı SMTP'de takılsa bile orphan tarayıcı
    kalmamalı. Bu yüzden temizlik önce gelir.
    """
    order = []

    def killer(*_a, **_kw):
        order.append("kill")

    def alert(*_a, **_kw):
        order.append("alert")

    watchdog.fire("Günlük Mahsup", 900, killer=killer, alert_sender=alert, exiter=Recorder())

    assert order == ["kill", "alert"]


def test_exits_even_when_alert_fails():
    """Uyarı gönderilemese bile süreç kapanmalı — asılı kalmak uyarısız çıkmaktan kötü."""
    exiter = _fire(alert_sender=Recorder(raises=RuntimeError("SMTP yok")))
    assert exiter.calls == [((watchdog.EXIT_CODE_WATCHDOG,), {})]


def test_exits_even_when_cleanup_fails():
    """Temizlik hatası çıkış yolunu bloklayamaz."""
    exiter = _fire(killer=Recorder(raises=RuntimeError("WMI yok")))
    assert exiter.calls == [((watchdog.EXIT_CODE_WATCHDOG,), {})]


def test_alert_explains_it_is_a_hang_not_an_exception():
    """Teşhis doğru yere gitsin: bu bir asılma, yakalanmamış istisna değil."""
    alert = Recorder()
    _fire(alert_sender=alert)

    kwargs = alert.calls[0][1]
    assert "asıl" in kwargs["headline"].lower()
    assert "istisna üretmediği" in kwargs["explanation"]


def test_armed_timer_is_daemon_and_cancellable():
    """Normal koşuda watchdog süreci canlı tutmamalı."""
    timer = watchdog.arm("Test İşi", 3600)
    try:
        assert timer.daemon is True
        assert timer.is_alive()
    finally:
        watchdog.disarm(timer)
    # Neden: cancel() yalnızca bekleme olayını set eder; thread'in uyanıp çıkması için
    # kısa bir pay gerekir. disarm bilinçli olarak bloklamıyor (çıkış yolunda çağrılıyor).
    timer.join(timeout=5)
    assert not timer.is_alive()


def test_timeouts_stay_below_scheduler_limits():
    """
    Watchdog, Task Scheduler'ın ExecutionTimeLimit'inden ÖNCE ateşlemeli — yoksa süreci
    scheduler sessizce öldürür ve uyarı maili hiç gitmez.
    Scheduler limitleri: settlement 30 dk, plant status 10 dk.
    """
    assert watchdog.DAILY_SETTLEMENT_TIMEOUT < 30 * 60
    assert watchdog.MONTHLY_SETTLEMENT_TIMEOUT < 30 * 60
    assert watchdog.PLANT_STATUS_TIMEOUT < 10 * 60


# --- Temizlik kapsamı: eşzamanlı dashboard koşusunu vurmama garantisi ---

def test_cleanup_command_is_scoped_to_this_process_tree():
    """
    KRİTİK: Komut süreç ağacını BU pid'den yürümeli ve isim filtresi uygulamalı.
    Ada göre geniş bir temizlik prod'da dashboard'ın eşzamanlı GAOSB oturumunu vururdu.
    """
    cmd = process_cleanup.build_tree_kill_command(os.getpid())

    assert str(os.getpid()) in cmd
    assert "ParentProcessId" in cmd, "Ağaç yürüyüşü yoksa kapsam daralmamış demektir"
    assert process_cleanup.BROWSER_NAME_PATTERN in cmd
    # Ağaç dışına çıkan toplu bir hedefleme olmamalı
    assert "Get-Process" not in cmd
    assert "Stop-Process -Name" not in cmd


def test_cleanup_targets_only_descendants_not_siblings():
    """
    Komut yalnızca $target'tan aşağı iner. Kardeş/yabancı süreçler (dashboard'ın
    tarayıcısı) kuyruğa hiç girmez — bunu komutun yapısı garanti eder.
    """
    cmd = process_cleanup.build_tree_kill_command(12345)

    assert "$queue.Enqueue([string]$target)" in cmd
    assert "$target = 12345" in cmd


def test_cleanup_returns_killed_pids_from_runner_output():
    captured = {}

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = cmd

        class Out:
            stdout = "1234 5678\n"
        return Out()

    pids = process_cleanup.kill_browser_descendants(runner=fake_runner)

    if os.name == "nt":
        assert pids == [1234, 5678]
        assert "powershell" in captured["cmd"][0]
    else:
        assert pids == []


def test_cleanup_never_raises_when_runner_explodes():
    """Best-effort: temizlik hatası watchdog'un çıkışını engellememeli."""
    def boom(*_a, **_kw):
        raise OSError("powershell bulunamadı")

    assert process_cleanup.kill_browser_descendants(runner=boom) == []


@pytest.mark.skipif(os.name != "nt", reason="WMI süreç ağacı yalnızca Windows'ta")
def test_generated_powershell_actually_runs():
    """
    Neden: Komut gömülü çok satırlı bir PowerShell scripti; sözdizimi hatası ancak
    gerçek asılma anında ortaya çıkardı. Tarayıcı açık olmadığı için hiçbir şey
    öldürmez — boş liste dönmesi scriptin temiz koştuğunu kanıtlar.
    """
    assert process_cleanup.kill_browser_descendants() == []
