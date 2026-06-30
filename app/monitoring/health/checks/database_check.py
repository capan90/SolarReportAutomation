import time
from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.database.db_session import engine
from sqlalchemy import text

class DatabaseCheck(IHealthCheck):
    """
    Neden: Veritabanı bağlantısının kurulabildiğini ve sorgu kabul ettiğini test etmek.
    """
    @property
    def name(self) -> str:
        return "Database Connection"

    @property
    def timeout_seconds(self) -> float:
        return 5.0

    @property
    def severity(self) -> str:
        return "CRITICAL"

    def run(self) -> HealthCheckResult:
        start_time = time.time()
        try:
            # pool_pre_ping veya doğrudan SELECT 1 ile veritabanı testi
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            duration_ms = int((time.time() - start_time) * 1000)
            return HealthCheckResult(
                name=self.name,
                status="SUCCESS",
                duration_ms=duration_ms,
                message="Veritabanı bağlantısı başarıyla kuruldu.",
                details={"database_url_type": engine.name}
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return HealthCheckResult(
                name=self.name,
                status="FAILED",
                duration_ms=duration_ms,
                message=f"Veritabanına bağlanılamadı: {str(e)}",
                details={}
            )
