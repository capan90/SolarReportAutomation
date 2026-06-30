import logging
import sys
from pathlib import Path
from app.core.config import settings

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

        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
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
