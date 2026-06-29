import sys
from app.core.config import settings
from app.core.logger import setup_logger
from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.infrastructure.storage.archive_manager import ArchiveManager
from app.extractors.isolar.extractor import IsolarExtractor


logger = setup_logger("MainOrchestrator")

def run():
    """
    Neden: Sprint 3 kapsamında Login, oturum doğrulama, Rapor sayfasına navigasyon,
    indirme ve arşivleme adımlarını koordine etmek, hata yönetimini gerçekleştirmek ve tarayıcıyı güvenli sonlandırmak.
    """
    logger.info("===== SolarReportAutomation Sprint 3 Başlatıldı =====")
    
    # 1. Konfigürasyonu doğrula
    try:
        settings.validate()
        logger.info("Ortam değişkenleri doğrulandı.")
    except ValueError as e:
        logger.error(f"Başlatma Hatası: {e}")
        sys.exit(1)

    # 2. İşlemleri yürüt
    try:
        # Neden: Tarayıcı oturumunun (Playwright) temiz kapanmasını garanti altına almak
        with PlaywrightClient() as client:
            page = client.create_page()
            
            # Login ve Doğrulama Adımı
            extractor = IsolarExtractor(page)
            extractor.login_and_verify()
            
            # Rapor Sayfasına Navigasyon Adımı
            extractor.navigate_to_daily_report()
            
            # Günlük Rapor İndirme Adımı
            temp_file_path = extractor.download_daily_report()
            
            # Arşivleme Adımı
            archive_manager = ArchiveManager()
            final_file_path = archive_manager.archive_raw_file(temp_file_path)
            
            logger.info(f"Giriş, navigasyon, indirme ve arşivleme işlemi başarıyla tamamlandı. Arşivlenen dosya: {final_file_path}")
            
    except Exception as e:
        logger.error(f"Uygulama çalıştırılırken kritik hata oluştu: {e}", exc_info=True)
        sys.exit(1)

    logger.info("===== SolarReportAutomation Sprint 3 Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    run()

