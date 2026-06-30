from abc import ABC, abstractmethod
from typing import Any, Dict
from dataclasses import dataclass

@dataclass
class HealthCheckResult:
    """
    Neden: Her bağımsız sağlık kontrolünün çıktısını standart bir veri modeli ile temsil etmek.
    """
    name: str
    status: str  # SUCCESS, WARNING, FAILED, SKIPPED, TIMEOUT
    duration_ms: int
    message: str
    details: Dict[str, Any]

class IHealthCheck(ABC):
    """
    Neden: Tüm sağlık kontrolü sınıflarının uyması gereken ortak sözleşmeyi tanımlamak (SOLID - ISP & LSP).
    """
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def timeout_seconds(self) -> float:
        pass

    @property
    @abstractmethod
    def severity(self) -> str:  # CRITICAL, WARNING
        pass

    @abstractmethod
    def run(self) -> HealthCheckResult:
        pass
