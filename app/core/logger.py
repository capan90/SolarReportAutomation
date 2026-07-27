import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

# Neden: Dashboard 7/24 çalışır ve log dosyasını sürekli AÇIK tutar. Windows'ta
# os.rename, dosyayı başka bir process açık tuttuğunda WinError 32 ile düşer;
# bu yüzden dashboard ile aynı dosyaya yazan kısa ömürlü ETL process'leri
# app.log'u hiçbir zaman döndüremiyordu (2026-07-27 sessiz kayıt kaybı olayı).
# Çözüm: uzun ömürlü tek yazıcıyı ayrı dosyaya almak. Kendi dosyasını yalnızca
# kendisi tuttuğu için dashboard KENDİ dosyasını sorunsuz döndürebilir
# (doRollover rename'den önce akışı kapatır).
DASHBOARD_LOG_FILE = "dashboard.log"
DEFAULT_LOG_FILE = "app.log"
DASHBOARD_MODULE = "app.dashboard.web_server"
DASHBOARD_ENTRY_FILE = "web_server.py"


def _is_dashboard_process() -> bool:
    """
    Neden: sys.argv[0]'a bakmak YETMEZ. `python -m app.dashboard.web_server`
    çalıştırıldığında runpy, argv[0]'ı ancak modül gövdesini çalıştırmadan hemen
    önce yazar; oysa `app/dashboard/__init__.py` (web_server'ı import ediyor)
    daha ÖNCE yüklenir ve logger tam o sırada kurulur — dashboard süreci
    app.log'a yazmaya başlardı.

    sys.orig_argv yorumlayıcı başlarken sabitlenir ve import sırasından
    etkilenmez; bu yüzden birincil kaynak odur (Python 3.10+).
    """
    candidates = list(getattr(sys, "orig_argv", None) or []) + list(sys.argv or [])
    for arg in candidates:
        if not arg:
            continue
        if arg == DASHBOARD_MODULE:
            return True
        if Path(arg).name.lower() == DASHBOARD_ENTRY_FILE:
            return True
    return False


def resolve_log_file_name() -> str:
    """
    Neden: Hangi dosyaya yazılacağı PROCESS bazında belirlenir, modül bazında
    değil. Dashboard süreci içinde koşan her şey (tetiklenen mahsuplaşma job'ları
    dahil) dashboard.log'a yazmalı; aynı modüller zamanlanmış bir görevde
    koştuğunda app.log'a yazmalı.

    LOG_FILE_NAME ortam değişkeni tanımlıysa her şeyin önüne geçer (test ve özel
    senaryolar için kaçış kapısı).
    """
    override = os.environ.get("LOG_FILE_NAME", "").strip()
    if override:
        return override
    return DASHBOARD_LOG_FILE if _is_dashboard_process() else DEFAULT_LOG_FILE


class ResilientRotatingFileHandler(RotatingFileHandler):
    """
    Neden: Standart RotatingFileHandler, rollover sırasında os.rename patlarsa
    emit() içinde handleError'a düşer ve KAYDI YAZMADAN geçer — sessiz veri
    kaybı. Teşhis altyapımızın tamamı log dosyasına dayandığı için bu kabul
    edilemez (CLAUDE.md: sessiz hata yok).

    Bu sınıf rotasyonu denemeden ÖNCE bir rename denemesi yapar. Rename mümkün
    değilse (dosyayı başka bir process açık tutuyor) rotasyon atlanır, akış
    yeniden açılır ve kayıt normal şekilde YAZILIR.

    Ön kontrol neden şart: RotatingFileHandler.doRollover, asıl rename'den ÖNCE
    yedekleri kaydırır (app.log.1 -> .2 ...) ve app.log.1'i siler. Doğrudan
    deneyip hataya düşmek, her başarısız denemede bir yedeği yok ederdi.

    Bedel: kilit süresince dosya maxBytes'ı aşarak büyür; kilit kalkınca ilk
    rotasyonda normale döner.
    """

    # Neden: Uyarı process başına bir kez yazılır; her kayıtta tekrarlanırsa
    # asıl logu boğar.
    _rotation_warning_logged = False

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None

        if not self._rename_available():
            if not ResilientRotatingFileHandler._rotation_warning_logged:
                ResilientRotatingFileHandler._rotation_warning_logged = True
                print(
                    f"[logger] {self.baseFilename} döndürülemedi (dosyayı başka bir process "
                    f"açık tutuyor). Rotasyon atlandı; kayıtlar yazılmaya devam ediyor, "
                    f"dosya geçici olarak sınırı aşacak.",
                    file=sys.stderr,
                )
            self.stream = self._open()
            return

        super().doRollover()

    def _rename_available(self) -> bool:
        """
        Neden: Dosyanın yeniden adlandırılabilir olup olmadığını yan etkisiz
        sınamak. Başarılıysa hemen eski adına geri alınır.
        """
        probe = f"{self.baseFilename}.rotcheck"
        try:
            os.rename(self.baseFilename, probe)
        except OSError:
            return False
        try:
            os.rename(probe, self.baseFilename)
        except OSError:
            # Neden: Buraya düşmek pratikte imkânsız (hedef ad az önce boşaldı),
            # ama sessiz kalınmaz: veri .rotcheck dosyasında durur, kaybolmaz.
            print(
                f"[logger] {probe} eski adına geri alınamadı; kayıtlar bu dosyada.",
                file=sys.stderr,
            )
            return False
        return True


def setup_logger(name: str = "SolarReportAutomation") -> logging.Logger:
    """
    Neden: Tüm uygulama boyunca tutarlı formatta ve hem konsola hem de log dosyasına
    yazacak şekilde loglama yapısını yapılandırmak.
    """
    logger = logging.getLogger(name)
    log_level_name = getattr(settings, "log_level", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logger.setLevel(log_level)

    # Loggers prevent duplication if setup is called multiple times
    if logger.handlers:
        return logger

    # Log formatı tanımla
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(filename)s:%(lineno)d]: %(message)s"
    )

    # Konsol handler yapılandır
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Log klasörünü oluştur ve dosya handler yapılandır
    log_dir = settings.log_directory
    try:
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = ResilientRotatingFileHandler(
            log_dir / resolve_log_file_name(),
            encoding="utf-8",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # Neden: İzin sorunları veya disk dolu olması gibi dosya yazma hatalarında loglama kesilmesin,
        # konsoldan hata bildirilsin.
        print(f"Log dosyası oluşturulamadı, sadece konsola loglama yapılacak. Hata: {e}", file=sys.stderr)

    return logger
