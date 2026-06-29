from typing import Generator
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger("BrowserInfrastructure")

class PlaywrightClient:
    """
    Neden: Playwright tarayıcı motorunun açılması, yapılandırılması ve kapatılması
    yaşam döngüsünü (lifecycle) yöneterek kaynak sızıntılarını (resource leaks) engellemek.
    """
    def __init__(self, headless: bool = None):
        self.headless = settings.headless if headless is None else headless

        self._playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None

    def __enter__(self) -> "PlaywrightClient":
        """
        Neden: 'with' bloğu başlatıldığında tarayıcı motorunu ayağa kaldırmak.
        """
        logger.info("Playwright tarayıcı motoru başlatılıyor...")
        self._playwright = sync_playwright().start()
        
        # Neden: Enterprise altyapılarda proxy veya yavaş ağlar için timeout ve yavaşlatma (slow_mo) opsiyonları eklenebilir.
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        # Neden: İndirme işlemlerinin otomatik tamamlanması ve pencere boyutunun sabitlenmesi için context ayarlanır.
        self.context = self.browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800}
        )
        logger.info("Tarayıcı ve Context başarıyla oluşturuldu.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Neden: 'with' bloğu bittiğinde veya beklenmedik bir hata oluştuğunda tarayıcı
        ve Playwright süreçlerini temiz bir şekilde sonlandırmak (Orphan process engelleme).
        """
        logger.info("Tarayıcı kapatılıyor ve kaynaklar temizleniyor...")
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("Playwright oturumu sonlandırıldı.")

    def create_page(self) -> Page:
        """
        Neden: Her extraction iş akışı için izole bir sayfa (tab) üretmek.
        """
        if not self.context:
            raise RuntimeError("Browser context henüz başlatılmadı. Lütfen client'ı context manager (with) içinde kullanın.")
        logger.info("Yeni tarayıcı sayfası oluşturuluyor...")
        return self.context.new_page()
