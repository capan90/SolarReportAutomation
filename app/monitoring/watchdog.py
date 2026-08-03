"""
Neden: 2026-08-03 09:00 koşusu iSolar tarayıcısının kapanışında asıldı. Süreç YAŞADIĞI
için istisna oluşmadı; ne `main.py`'nin except dalları, ne `system_alert`, ne de graceful
FAILED yolu devreye girdi. Task Scheduler'ın süre limiti 72 saatti ve görev politikası
`IgnoreNew` — yani asılı süreç sonlandırılmasaydı 4 ve 5 Ağustos koşuları da sessizce
atlanacaktı. Toplam sinyal: sıfır.

Bu modül işin TAMAMINA bir üst sınır koyar. Süre aşılırsa süreç kendi ölümünü haber verip
çıkar; asılmanın nerede olduğu (tarayıcı kapanışı, portal, DB, ağ) fark etmez — mekanizmaya
değil süreye bakar.

Neden ayrı bir thread + `os._exit`:
- Asılma çoğunlukla ana thread'i C seviyesinde bloklar; oradan bir bayrak okumak mümkün
  değildir. Daemon timer bağımsız çalışır ve normal koşuda süreci canlı tutmaz.
- `sys.exit()` yalnızca istisna fırlatır — bloklanmış ana thread onu asla görmez.
  `os._exit` çekirdek seviyesinde çıkar. Bedeli: `finally`/`atexit` çalışmaz, bu yüzden
  tarayıcı torunları çıkmadan ÖNCE elle toplanır (bkz. process_cleanup).

Süre ilişkisi (bilinçli): watchdog < Task Scheduler ExecutionTimeLimit.
Günlük/aylık 15 dk (limit 30 dk), PlantStatus 5 dk (limit 10 dk). Böylece süreç önce
KENDİ uyarısını gönderir; scheduler'ın sessiz sonlandırması yalnızca watchdog da
patlarsa devreye girer.
"""
import os
import threading
from typing import Callable, Optional

from app.core.logger import setup_logger

logger = setup_logger("JobWatchdog")

# Neden: Mevcut kodlar 1 (iş hatası), 4 (config), 5 (health), 6 (veri eksik) kullanıyor;
# 7 = watchdog. Ayrı kod, scheduler geçmişinde "asıldı" ile "başarısız oldu"yu ayırır.
EXIT_CODE_WATCHDOG = 7

DAILY_SETTLEMENT_TIMEOUT = 15 * 60
MONTHLY_SETTLEMENT_TIMEOUT = 15 * 60
PLANT_STATUS_TIMEOUT = 5 * 60


def fire(
    job_name: str,
    timeout_seconds: float,
    killer: Optional[Callable] = None,
    alert_sender: Optional[Callable] = None,
    exiter: Optional[Callable] = None,
) -> None:
    """
    Süre aşımında çalışır: temizle → haber ver → çık.

    Sıra bilinçli: temizlik ÖNCE yapılır. Uyarı maili SMTP'de takılırsa bile orphan
    tarayıcı bırakmadan çıkılmış olur. Uyarı gönderimi best-effort; hatası çıkışı
    engelleyemez — asılı süreci hayatta tutmak, uyarısız çıkmaktan daha kötüdür.
    """
    minutes = round(timeout_seconds / 60, 1)
    message = (
        f"{job_name} {minutes} dakikadır ilerlemiyor; watchdog süreci sonlandırıyor. "
        f"İş asılı kaldığında istisna oluşmadığı için başka hiçbir alarm tetiklenmez "
        f"(2026-08-03 olayı). Sonraki koşuların atlanmaması için süreç kapatılıyor."
    )
    logger.error(message)

    if killer is None:
        from app.infrastructure.browser.process_cleanup import kill_browser_descendants
        killer = kill_browser_descendants
    try:
        killer()
    except Exception as e:
        logger.error("Watchdog temizliği başarısız (%s): %s", type(e).__name__, e)

    if alert_sender is None:
        from app.notifications.system_alert import send_job_failure_alert
        alert_sender = send_job_failure_alert
    try:
        alert_sender(
            job_name,
            message,
            headline=f"{job_name} asıldı ve zorla sonlandırıldı.",
            explanation=(
                "İş belirlenen süre içinde bitmedi. Asılan süreç istisna üretmediği için "
                "normal hata bildirimleri devreye giremez; bu mail watchdog tarafından "
                "gönderildi. Süreç kapatıldı ki zamanlanmış sonraki koşular atlanmasın."
            ),
        )
    except Exception as e:
        logger.error("Watchdog uyarısı gönderilemedi (%s): %s", type(e).__name__, e)

    (exiter or os._exit)(EXIT_CODE_WATCHDOG)


def arm(job_name: str, timeout_seconds: float) -> threading.Timer:
    """
    İş için watchdog kurar ve timer'ı döner.

    Timer daemon'dur: iş normal sürede biterse süreç çıkarken timer da ölür, ayrıca
    iptal etmek gerekmez (yine de `disarm` sağlanır).
    """
    timer = threading.Timer(timeout_seconds, fire, args=(job_name, timeout_seconds))
    timer.daemon = True
    timer.name = f"watchdog-{job_name}"
    timer.start()
    logger.info("Watchdog kuruldu: %s (%s dk)", job_name, round(timeout_seconds / 60, 1))
    return timer


def disarm(timer: Optional[threading.Timer]) -> None:
    """Neden: İş erken biterse timer'ı iptal eder; best-effort."""
    if timer is None:
        return
    try:
        timer.cancel()
    except Exception:
        pass
