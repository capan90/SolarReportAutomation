"""
Yetenek (Capability) modeli.

Neden: Portal davranis farklarini if/else yerine acik/kapali yetenek sorgusu ile
yonetmek (ADR-004). Yeni portal eklemek = yetenek kombinasyonu secmek.
"""

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Iterable

from app.portal_framework.exceptions import UnsupportedCapabilityError


class PortalCapability(str, Enum):
    """
    Neden: Bir portalin sundugu yetenekleri tip-guvenli sabitlerle tanimlamak.
    Yeni yetenek = bu enum'a deger eklemek (kod akisi degismez).
    """

    # Extraction
    ASYNC_EXPORT = "async_export"
    SYNC_EXPORT = "sync_export"
    POLLING_REQUIRED = "polling_required"
    SESSION_REUSE = "session_reuse"
    CAPTCHA_REQUIRED = "captcha_required"
    OAUTH2_LOGIN = "oauth2_login"
    MULTI_PLANT = "multi_plant"

    # Data
    GENERATION_DATA = "generation_data"
    CONSUMPTION_DATA = "consumption_data"
    METER_DATA = "meter_data"
    EXPORT_DATA = "export_data"
    OBIS_CODES = "obis_codes"
    TARIFF_BREAKDOWN = "tariff_breakdown"
    REACTIVE_ENERGY = "reactive_energy"
    MAX_DEMAND = "max_demand"
    REALTIME_DATA = "realtime_data"

    # Granularity
    HOURLY_DATA = "hourly_data"
    DAILY_DATA = "daily_data"
    MONTHLY_DATA = "monthly_data"
    YEARLY_DATA = "yearly_data"

    # Export format
    CSV_EXPORT = "csv_export"
    EXCEL_EXPORT = "excel_export"
    PDF_EXPORT = "pdf_export"


@dataclass(frozen=True)
class CapabilitySet:
    """
    Neden: Bir portalin yetenek kumesini degismez (immutable) sekilde tutmak ve
    yetenek sorgularini okunabilir, tip-guvenli hale getirmek.
    """

    capabilities: FrozenSet[PortalCapability]

    @classmethod
    def of(cls, *caps: PortalCapability) -> "CapabilitySet":
        """Degisken sayida yetenekten CapabilitySet uretir."""
        return cls(frozenset(caps))

    @classmethod
    def from_iterable(cls, caps: Iterable[PortalCapability]) -> "CapabilitySet":
        return cls(frozenset(caps))

    def supports(self, cap: PortalCapability) -> bool:
        """Verilen yetenegin destekleniyor olup olmadigini doner."""
        return cap in self.capabilities

    def supports_all(self, *caps: PortalCapability) -> bool:
        """Verilen tum yeteneklerin desteklendigini doner."""
        return all(c in self.capabilities for c in caps)

    def supports_any(self, *caps: PortalCapability) -> bool:
        """Verilen yeteneklerden en az birinin desteklendigini doner."""
        return any(c in self.capabilities for c in caps)

    def require(self, cap: PortalCapability, portal_id: str = "unknown") -> None:
        """
        Neden: Bir adim calismadan once gerekli yetenegin varligini zorunlu kilmak.
        Yoksa UnsupportedCapabilityError firlatir (fail-fast).
        """
        if cap not in self.capabilities:
            raise UnsupportedCapabilityError(portal_id, cap.value)
