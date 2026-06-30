"""
PortalRunner - tek bir extraction calismasinin orkestratoru.

Neden: Registry'den adapteri cozumleme, SessionContext olusturma, driver'i baglama
ve adapteri calistirma sorumlulugunu tek noktada toplamak. Runner, portal teknolojisini
veya Playwright'i BILMEZ; yalnizca soyut sozlesmeleri kullanir.
"""

from typing import Optional

from app.portal_framework.adapter.base_portal_adapter import BasePortalAdapter
from app.portal_framework.driver.browser_driver import BrowserDriver
from app.portal_framework.exceptions import PortalFrameworkError
from app.portal_framework.models.period import Period
from app.portal_framework.models.results import ExtractionResult
from app.portal_framework.models.session_context import SessionContext
from app.portal_framework.registry.portal_registry import PortalRegistry


class PortalRunner:
    """
    Neden: Extraction calismasinin yasam dongusunu (cozumle -> baglam olustur ->
    calistir) yonetmek. Tek sorumluluk: orkestrasyon.
    """

    def __init__(self, registry: PortalRegistry):
        self.registry = registry

    def execute(
        self,
        portal_id: str,
        run_id: str,
        driver: BrowserDriver,
        period: Optional[Period] = None,
        plant_id: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Neden: Verilen portal icin adapteri cozumleyip, baglami kurup, akisi
        calistirmak ve nihai ExtractionResult'i donmek.
        """
        adapter = self.registry.resolve(portal_id)
        if not isinstance(adapter, BasePortalAdapter):
            raise PortalFrameworkError(
                f"'{portal_id}' icin cozumlenen adapter BasePortalAdapter degil: "
                f"{type(adapter).__name__}"
            )

        ctx = SessionContext(
            run_id=run_id,
            portal_id=portal_id,
            driver=driver,
            period=period,
            plant_id=plant_id,
            report_type=report_type,
        )

        return adapter.run(ctx)
