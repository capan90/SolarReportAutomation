import time
import urllib.request
import urllib.error
from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.core.config import settings

class PortalCheck(IHealthCheck):
    """
    Neden: İsOlar Portal login sayfasının veya ana adresinin 
    erişilebilir olup olmadığını kontrol etmek.
    """
    @property
    def name(self) -> str:
        return "Portal Reachability"

    @property
    def timeout_seconds(self) -> float:
        return 10.0

    @property
    def severity(self) -> str:
        return "CRITICAL"

    def run(self) -> HealthCheckResult:
        start_time = time.time()
        url = settings.base_url
        
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            )
        }
        
        try:
            # HEAD isteği gönder (daha az veri tüketimi için), başarısız olursa GET dene
            req = urllib.request.Request(url, headers=headers, method="HEAD")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    status_code = response.getcode()
            except urllib.error.HTTPError as he:
                # Bazı sunucular HEAD isteğine 405 veya 403 verebilir, bu durumda adrese erişilebiliyordur
                status_code = he.code
                if status_code in [403, 405]:
                    # GET isteği ile fallback dene
                    req_get = urllib.request.Request(url, headers=headers, method="GET")
                    with urllib.request.urlopen(req_get, timeout=self.timeout_seconds) as response_get:
                        status_code = response_get.getcode()
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return HealthCheckResult(
                name=self.name,
                status="SUCCESS",
                duration_ms=duration_ms,
                message=f"Portal başarıyla yanıt verdi (HTTP Status: {status_code}).",
                details={"portal_url": url, "http_status": status_code}
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return HealthCheckResult(
                name=self.name,
                status="FAILED",
                duration_ms=duration_ms,
                message=f"Portala erişilemedi: {str(e)}",
                details={"portal_url": url}
            )
