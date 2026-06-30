import time
import functools
from typing import Callable, Type, List, Tuple, Any, Optional
from app.core.logger import setup_logger

logger = setup_logger("RetryPolicyFramework")

class RetryPolicy:
    """
    Neden: HTTP, SMTP, Veritabanı ve Playwright/Browser işlemlerinde
    yeniden kullanılabilir, esnek ve özelleştirilebilir bir tekrar deneme (retry) altyapısı sağlamak.
    """
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
        non_retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
        on_retry_callback: Optional[Callable[[int, Exception, float], None]] = None
    ):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retryable_exceptions = retryable_exceptions or (Exception,)
        self.non_retryable_exceptions = non_retryable_exceptions or ()
        self.on_retry_callback = on_retry_callback

    def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Neden: Verilen fonksiyonu retry limitleri ve exponential backoff dahilinde çalıştırmak.
        """
        last_exception = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                # Non-retryable kontrolü (Eğer hata kesinlikle denetim dışı ise anında fırlat - Fail-Fast)
                if isinstance(e, self.non_retryable_exceptions):
                    logger.error(f"Tekrar denenemez hata oluştu ({e.__class__.__name__}). İşlem durduruluyor.")
                    raise e
                
                # Retryable kontrolü
                if not isinstance(e, self.retryable_exceptions):
                    logger.error(f"Yeniden deneme kapsamında olmayan hata türü ({e.__class__.__name__}). İşlem durduruluyor.")
                    raise e

                # Son deneme de başarısız olduysa tekrar bekleme yapma
                if attempt == self.max_retries:
                    break

                # Exponential backoff hesabı: backoff_factor * (2 ** (attempt - 1))
                delay = self.backoff_factor * (2 ** (attempt - 1))
                
                logger.warning(
                    f"İşlem başarısız (Deneme {attempt}/{self.max_retries}): {str(e)}. "
                    f"{delay} saniye sonra tekrar denenecek..."
                )
                
                # run_id değerini dinamik olarak tespit et
                run_id = "unknown-run-id"
                if args:
                    first_arg = args[0]
                    if hasattr(first_arg, "run_id") and getattr(first_arg, "run_id"):
                        run_id = getattr(first_arg, "run_id")
                if "run_id" in kwargs:
                    run_id = kwargs["run_id"]

                # Veritabanına denetim kaydı at (best-effort)
                try:
                    from app.database.audit_repository import AuditRepository
                    operation_name = func.__name__
                    if args and hasattr(args[0], "__class__"):
                        operation_name = f"{args[0].__class__.__name__}.{func.__name__}"
                    
                    AuditRepository().save_retry_attempt(
                        run_id=run_id,
                        operation=operation_name,
                        attempt=attempt,
                        delay_seconds=delay,
                        error_message=str(e)[:400]  # Maksimum uzunluk sınırı
                    )
                except Exception as audit_err:
                    logger.debug(f"Retry db audit loglama başarısız (best-effort): {audit_err}")

                # Metrik sistemine retry olayını kaydet (best-effort)
                try:
                    from app.monitoring.metrics import get_default_registry, MetricsCollector
                    registry = get_default_registry()
                    collector = MetricsCollector(registry)
                    operation_name = func.__name__
                    if args and hasattr(args[0], "__class__"):
                        operation_name = f"{args[0].__class__.__name__}.{func.__name__}"
                    collector.record_retry_attempt(run_id=run_id, operation=operation_name)
                    registry.flush_and_export()
                except Exception as met_err:
                    logger.debug(f"Retry metrik kaydı başarısız (best-effort): {met_err}")
                
                # Callback tetikleme (Örneğin veritabanı denetim kaydını güncellemek için)
                if self.on_retry_callback:
                    try:
                        self.on_retry_callback(attempt, e, delay)
                    except Exception as cb_err:
                        logger.error(f"Retry callback hatası: {cb_err}")

                time.sleep(delay)

        logger.error(f"İşlem {self.max_retries} deneme sonrasında başarısız oldu.")
        raise last_exception


def with_retry(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    non_retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry_callback: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Neden: Fonksiyonları veya metotları kolayca retry politikasıyla sarmalamak için dekoratör.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            policy = RetryPolicy(
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                retryable_exceptions=retryable_exceptions,
                non_retryable_exceptions=non_retryable_exceptions,
                on_retry_callback=on_retry_callback
            )
            return policy.execute(func, *args, **kwargs)
        return wrapper
    return decorator
