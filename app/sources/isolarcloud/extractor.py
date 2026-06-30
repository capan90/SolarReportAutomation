from pathlib import Path
from typing import Optional

from app.sources.interface import ISourceExtractor
from app.sources.models import SourceMetadata
from app.sources.exceptions import SourceAuthenticationError
from app.sources.context import get_source_context
from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.extractors.isolar.extractor import IsolarExtractor
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger("IsolarCloudExtractor")

class IsolarCloudExtractor(ISourceExtractor):
    """
    Neden: Mevcut IsolarExtractor (Playwright Scraper) bileşenini 
    yeni çoklu kaynak (Multi Source) arayüzüne uyarlamak (Adapter Pattern).
    """
    
    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_name="isolarcloud",
            vendor="Sungrow",
            version="1.0.0",
            supported_report_types=["daily_generation"],
            authentication_type="credentials",
            capabilities={
                "supports_excel_export": True,
                "supports_api": False,
                "supports_scheduler": True,
                "supports_health_check": True
            }
        )

    def download_report(self, output_dir: Path, **kwargs) -> Path:
        """
        Neden: Playwright tarayıcısını başlatıp IsolarExtractor üzerinden
        raporu indirmek.
        """
        run_id = kwargs.get("run_id")
        if not run_id:
            context = get_source_context()
            run_id = context.source_name if context else "unknown-run-id"
            
        headless = kwargs.get("headless", settings.app_env in ["production", "staging", "ci"])

        logger.info("iSolarCloud veri toplama akışı başlatılıyor...")
        try:
            with PlaywrightClient(headless=headless) as client:
                page = client.create_page()
                extractor = IsolarExtractor(page, run_id=run_id)
                
                settings.validate()
                extractor.login_and_verify()
                extractor.navigate_to_report_page()
                return extractor.download_report(output_dir)
        except Exception as e:
            logger.error(f"iSolarCloud veri toplama hatası: {e}")
            raise SourceAuthenticationError("isolarcloud") from e
