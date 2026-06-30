import time
from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.infrastructure.browser.playwright_client import PlaywrightClient

class BrowserCheck(IHealthCheck):
    """
    Neden: Playwright tarayıcı motorunun sistemde yüklü olduğunu ve 
    başarıyla başlatılabildiğini doğrulamak.
    """
    @property
    def name(self) -> str:
        return "Playwright Browser Availability"

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def severity(self) -> str:
        return "CRITICAL"

    def run(self) -> HealthCheckResult:
        start_time = time.time()
        try:
            # Tarayıcıyı ayağa kaldırıp kapatarak uygunluğunu test et
            with PlaywrightClient(headless=True) as client:
                page = client.create_page()
                page.close()
            
            duration_ms = int((time.time() - start_time) * 1000)
            return HealthCheckResult(
                name=self.name,
                status="SUCCESS",
                duration_ms=duration_ms,
                message="Playwright Chromium tarayıcısı başarıyla başlatıldı.",
                details={"headless": True}
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return HealthCheckResult(
                name=self.name,
                status="FAILED",
                duration_ms=duration_ms,
                message=f"Playwright başlatılamadı: {str(e)}",
                details={}
            )
