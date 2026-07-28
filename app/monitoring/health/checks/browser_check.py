import time

from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.infrastructure.browser.playwright_client import PlaywrightClient


class BrowserCheck(IHealthCheck):
    """
    Neden: Playwright tarayıcı motorunun sistemde yüklü olduğunu ve
    başarıyla başlatılabildiğini doğrulamak.

    Ölçülen şey BAŞLATMA'dır, kapanış değil (2026-07-28). Kontrol eskiden
    launch + sayfa + kapanışı tek bir 10 sn'lik pencerede ölçüyordu; dev
    laptopta `browser.close()` geçici olarak 22 sn sürünce (launch aynı anda
    0,22 sn'ydi) kontrol TIMEOUT verdi, genel durum FAILED oldu ve pre-commit
    hook commit'i engelledi. Oysa sorulan soru "tarayıcı kullanılabilir mi" —
    cevabı başlatmadır. Kapanış yavaşlığı ETL sonuçlarını etkilemez; işi biten
    tarayıcının kapanması gecikir sadece.

    Kapanış yine de SENKRON yapılır ve süresi ölçülür: ayrı bir thread'e
    atılsaydı süreç kapanışında orphan chromium ve %TEMP kalıntısı bırakma
    riski doğardı (PlaywrightClient'ın var oluş sebebi tam da bunu önlemek).
    Yavaş kapanış yutulmaz, WARNING olarak raporlanır — görünür olur ama
    commit'i/ETL'i engellemez (main.py yalnızca FAILED'de sıfırdan farklı
    çıkış kodu verir).
    """

    # Neden: Yalnızca GERÇEK takılmaya karşı emniyet supabı. Kontrolün başarı
    # ölçütü artık başlatma; bu pencere kapanışın da sığabileceği kadar geniş
    # tutulur ki yavaş-ama-biten kapanış TIMEOUT üretmesin. 60 sn, GAOSB
    # extractor'daki LAUNCH_TIMEOUT_MS ile aynı büyüklük (bilinçli tercih).
    TIMEOUT_SECONDS = 60.0

    # Neden: Bu eşiğin üstündeki kapanış "normal" sayılmaz; sağlık raporunda
    # iz bırakmalı. Gözlenen sağlıklı değer 0,2-0,6 sn.
    SLOW_TEARDOWN_MS = 5_000

    @property
    def name(self) -> str:
        return "Playwright Browser Availability"

    @property
    def timeout_seconds(self) -> float:
        return self.TIMEOUT_SECONDS

    @property
    def severity(self) -> str:
        return "CRITICAL"

    def run(self) -> HealthCheckResult:
        startup_ms = None
        teardown_ms = None
        teardown_error = None

        start_time = time.perf_counter()
        try:
            with PlaywrightClient(headless=True) as client:
                page = client.create_page()
                page.close()
                # Neden: Ölçüm 'with' bloğunun İÇİNDE alınır — __exit__ (kapanış)
                # henüz çalışmadı. Kontrolün süresi budur.
                startup_ms = int((time.perf_counter() - start_time) * 1000)
                teardown_start = time.perf_counter()
            teardown_ms = int((time.perf_counter() - teardown_start) * 1000)
        except Exception as e:
            if startup_ms is None:
                # Başlatma başarısız: tarayıcı gerçekten kullanılamıyor.
                return HealthCheckResult(
                    name=self.name,
                    status="FAILED",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                    message=f"Playwright başlatılamadı: {str(e)}",
                    details={},
                )
            # Başlatma başarılıydı, kapanışta patladı: tarayıcı KULLANILABİLİR.
            teardown_ms = int((time.perf_counter() - teardown_start) * 1000)
            teardown_error = str(e)

        details = {
            "headless": True,
            "startup_ms": startup_ms,
            "teardown_ms": teardown_ms,
        }

        if teardown_error:
            details["teardown_error"] = teardown_error
            return HealthCheckResult(
                name=self.name,
                status="WARNING",
                duration_ms=startup_ms,
                message=(
                    f"Tarayıcı {startup_ms} ms'de başlatıldı; kapanışta hata: "
                    f"{teardown_error}"
                ),
                details=details,
            )

        if teardown_ms >= self.SLOW_TEARDOWN_MS:
            return HealthCheckResult(
                name=self.name,
                status="WARNING",
                duration_ms=startup_ms,
                message=(
                    f"Tarayıcı {startup_ms} ms'de başlatıldı (normal), ancak kapanış "
                    f"{teardown_ms} ms sürdü — sistem yavaşlığı olabilir."
                ),
                details=details,
            )

        return HealthCheckResult(
            name=self.name,
            status="SUCCESS",
            duration_ms=startup_ms,
            message="Playwright Chromium tarayıcısı başarıyla başlatıldı.",
            details=details,
        )
