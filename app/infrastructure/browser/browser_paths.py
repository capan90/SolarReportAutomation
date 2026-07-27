import os
import sys
from pathlib import Path
from typing import Optional

from app.core.logger import setup_logger

logger = setup_logger("BrowserPaths")

# Neden: Playwright tarayıcı binary'lerini PLAYWRIGHT_BROWSERS_PATH yoksa
# %USERPROFILE%\AppData\Local\ms-playwright altında arar. Bu yol HESABA BAĞLIDIR:
# SYSTEM olarak koşan bir süreçte %USERPROFILE% = C:\Windows\system32\config\systemprofile
# olur ve interaktif kullanıcının profiline yapılmış kurulum GÖRÜNMEZ (2026-07-27 olayı:
# dashboard görevi SYSTEM hesabında koştuğu için "chromium_headless_shell... doesn't exist").
# Çözüm .env'deki PLAYWRIGHT_BROWSERS_PATH ile makine geneli bir dizine sabitlemektir.
_DEFAULT_SUBPATH = Path("AppData") / "Local" / "ms-playwright"

# Neden: Kontrol her launch'ta çağrılır ama log her koşuda bir kez yazılmalı;
# aksi halde saatlik job'lar app.log'u aynı satırla doldurur.
_diagnostics_logged = False


def resolve_browsers_root() -> Optional[Path]:
    """
    Neden: Playwright'ın bu süreçte tarayıcıları arayacağı kök dizini, launch
    denemesinden ÖNCE bilinir kılmak. PLAYWRIGHT_BROWSERS_PATH tanımlıysa o,
    değilse platform varsayılanı döner; çözümlenemezse None.
    """
    explicit = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if explicit:
        # Neden: '0' özel bir değerdir (binary'ler paketin yanına kurulur), dizin değil.
        if explicit == "0":
            return None
        return Path(explicit)

    if sys.platform == "win32":
        user_profile = os.environ.get("USERPROFILE", "").strip()
        if not user_profile:
            return None
        return Path(user_profile) / _DEFAULT_SUBPATH

    home = os.environ.get("HOME", "").strip()
    if not home:
        return None
    return Path(home) / ".cache" / "ms-playwright"


def _is_service_account_profile(root: Path) -> bool:
    """Neden: SYSTEM/servis hesabı profilini tanımak; hata mesajını eyleme dönük yapar."""
    return "systemprofile" in str(root).lower() or "serviceprofiles" in str(root).lower()


def log_browser_environment() -> None:
    """
    Neden: Tarayıcı başlatma hatalarının en pahalı kısmı "hangi dizine bakıldı"
    sorusuydu; launch öncesi bunu logla ve eksikse SESSİZ KALMA (proje kuralı).
    Fırlatmaz: yanlış pozitif bir kontrol çalışan kurulumu durdurmasın; asıl hatayı
    Playwright'ın kendisi versin. Sadece teşhisi loga yazar.
    """
    global _diagnostics_logged
    if _diagnostics_logged:
        return
    _diagnostics_logged = True

    root = resolve_browsers_root()
    explicit = bool(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip())

    if root is None:
        logger.info("Playwright tarayıcı kökü çözümlenemedi (paket içi kurulum veya eksik profil değişkeni).")
        return

    source = "PLAYWRIGHT_BROWSERS_PATH" if explicit else "hesap profili varsayılanı"
    logger.info("Playwright tarayıcı kökü: %s (kaynak: %s)", root, source)

    if root.exists():
        installed = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("chromium"))
        if installed:
            logger.info("Kurulu Chromium paketleri: %s", ", ".join(installed))
            return
        logger.error(
            "Playwright tarayıcı kökü (%s) var ama içinde Chromium paketi YOK. "
            "Kurulum komutu: .venv\\Scripts\\playwright install chromium", root
        )
    else:
        logger.error("Playwright tarayıcı kökü BULUNAMADI: %s", root)

    if not explicit and _is_service_account_profile(root):
        logger.error(
            "Bu süreç bir servis hesabında (SYSTEM) koşuyor ve tarayıcıları kendi profilinde arıyor; "
            "interaktif kullanıcının profiline yapılmış kurulum buradan GÖRÜNMEZ. "
            ".env dosyasına PLAYWRIGHT_BROWSERS_PATH=C:\\ProgramData\\ms-playwright ekleyin ve "
            "aynı değişkenle bir kez 'playwright install chromium' çalıştırın."
        )
    elif not explicit:
        logger.error(
            "Tarayıcılar hesaba bağlı profilde aranıyor. Görev Zamanlayıcı farklı bir hesapta "
            "koştuğunda bu kurulum görünmez olur; .env'de PLAYWRIGHT_BROWSERS_PATH ile "
            "makine geneli bir dizine sabitlemeniz önerilir."
        )
