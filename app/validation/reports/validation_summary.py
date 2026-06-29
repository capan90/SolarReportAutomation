from dataclasses import dataclass

@dataclass(frozen=True)
class ValidationSummary:
    """
    Neden: Doğrulama adımlarının genel performansını, toplam kontrol sayısını,
    başarılı/başarısız adetlerini ve önem seviyesine göre hata dağılımını özetlemek.
    """
    total_checks: int
    passed: int
    failed: int
    warnings: int
    errors: int
    critical: int
    duration_ms: int
