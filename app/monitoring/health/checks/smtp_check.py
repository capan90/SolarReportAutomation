import time
import smtplib
from app.monitoring.health.interface import IHealthCheck, HealthCheckResult
from app.core.config import settings

class SMTPCheck(IHealthCheck):
    """
    Neden: Bildirim gönderimi öncesinde SMTP sunucu erişimini 
    ve kimlik doğrulama ayarlarını doğrulamak (E-posta göndermeden).
    """
    @property
    def name(self) -> str:
        return "SMTP Connection"

    @property
    def timeout_seconds(self) -> float:
        return 8.0

    @property
    def severity(self) -> str:
        return "WARNING"  # SMTP kritik olmadığı (best-effort) için uyarı derecesindedir

    def run(self) -> HealthCheckResult:
        start_time = time.time()
        
        if not settings.smtp_host:
            duration_ms = int((time.time() - start_time) * 1000)
            return HealthCheckResult(
                name=self.name,
                status="WARNING",
                duration_ms=duration_ms,
                message="SMTP_HOST yapılandırılmamış. E-posta bildirimleri gönderilemeyecek.",
                details={}
            )
            
        server = None
        try:
            # 465 portu SSL gerektirir
            if settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=self.timeout_seconds)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=self.timeout_seconds)
                server.ehlo()
                # STARTTLS desteği varsa başlat
                if server.has_extn("starttls"):
                    server.starttls()
                    server.ehlo()
            
            # Giriş denemesi
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
                auth_status = "Authenticated"
            else:
                auth_status = "No credentials provided (anonymous SMTP)"

            duration_ms = int((time.time() - start_time) * 1000)
            
            details = {
                "smtp_host": settings.smtp_host,
                "smtp_port": settings.smtp_port,
                "auth_status": auth_status
            }
            
            return HealthCheckResult(
                name=self.name,
                status="SUCCESS",
                duration_ms=duration_ms,
                message="SMTP sunucu bağlantısı ve kimlik doğrulama başarılı.",
                details=details
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            # Kritik şifrelerin veya hassas verilerin hata mesajında sızmasını engellemek için filtrele
            err_msg = str(e)
            if settings.smtp_password and settings.smtp_password in err_msg:
                err_msg = err_msg.replace(settings.smtp_password, "********")
                
            return HealthCheckResult(
                name=self.name,
                status="FAILED",
                duration_ms=duration_ms,
                message=f"SMTP sunucusuna bağlanılamadı: {err_msg}",
                details={"smtp_host": settings.smtp_host, "smtp_port": settings.smtp_port}
            )
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
