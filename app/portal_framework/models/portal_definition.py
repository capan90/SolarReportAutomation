"""
PortalDefinition ve yardimci konfigurasyon modelleri.

Neden: Bir portalin tam teknik manifestosunu (selector, route, timeout, capability,
field map) tek bir tip-guvenli nesnede toplamak (ADR-002). PortalConfig'ten zengin:
selectorlerin nereye ait oldugunu ve hangi yeteneklerin var oldugunu acikca ifade eder.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from app.portal_framework.exceptions import SelectorNotFoundError
from app.portal_framework.models.capability import CapabilitySet
from app.portal_framework.models.period import Granularity


@dataclass(frozen=True)
class SelectorMap:
    """
    Neden: Portal selectorlerini isimli ve degismez bir harita olarak tutmak.
    Eksik bir selector istegi sessizce None donmek yerine SelectorNotFoundError firlatir.
    """

    selectors: Mapping[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str:
        """Tanimli selectoru doner; yoksa SelectorNotFoundError firlatir."""
        if key not in self.selectors:
            raise SelectorNotFoundError(key)
        return self.selectors[key]

    def has(self, key: str) -> bool:
        return key in self.selectors


@dataclass(frozen=True)
class TimeoutConfig:
    """
    Neden: Portal-spesifik zaman asimi degerlerini (manuel login bekleme, async export
    polling vb.) kod icine gomulu sihirli sayilar yerine merkezi olarak tanimlamak.
    """

    navigation_ms: int = 30_000
    selector_ms: int = 15_000
    download_ms: int = 60_000
    login_wait_ms: int = 300_000
    network_idle_ms: int = 5_000
    poll_interval_ms: int = 5_000
    poll_max_attempts: int = 12


@dataclass(frozen=True)
class PortalDefinition:
    """
    Neden: Bir portali, framework kodu degistirmeden tanimlayabilmek. Adapter bu
    manifestoyu okuyarak davranir; yeni portal = yeni PortalDefinition kaydi (ADR-007).
    """

    portal_id: str
    name: str
    vendor: str
    technology: str
    base_url: str
    login_url: str
    auth_type: str
    nav_type: str
    capabilities: CapabilitySet
    selectors: SelectorMap = field(default_factory=SelectorMap)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    supported_reports: List[str] = field(default_factory=list)
    supported_exports: List[str] = field(default_factory=list)
    supported_periods: List[Granularity] = field(default_factory=list)
    field_map: Dict[str, str] = field(default_factory=dict)
    stability: str = "EXPERIMENTAL"
    last_verified: Optional[str] = None
