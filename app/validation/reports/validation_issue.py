from dataclasses import dataclass
from typing import Any, Optional
from app.validation.reports.severity import Severity

@dataclass(frozen=True)
class ValidationIssue:
    """
    Neden: Doğrulama kurallarından herhangi biri başarısız olduğunda, hatanın
    detaylarını (hangi sheet, kolon, satır, kural adı, beklenen vs. mevcut durum)
    ve önem seviyesini bir arada saklamak.
    """
    sheet: str
    column: Optional[str]
    row: Optional[int]
    rule: str
    severity: Severity
    expected: Any
    actual: Any
    message: str
    timestamp: str
