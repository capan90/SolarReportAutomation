"""
Donem (Period) ve granularite modelleri.

Neden: Her portaldan cekilecek veri bir tarih araligina ve granulariteye sahiptir.
Bu kavramlari portal-agnostic, dogrulanmis (start <= end) deger nesneleri olarak modellemek.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Granularity(str, Enum):
    """
    Neden: Veri cozunurlugunu (saatlik, gunluk, aylik vb.) tip-guvenli ifade etmek.
    str tabanli enum: JSON serilestirme ve karsilastirma kolayligi icin.
    """

    P01_15MIN = "p01_15min"
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass(frozen=True)
class DateRange:
    """
    Neden: Kapali bir tarih araligini (start <= end) degismez (immutable) ve
    kendini dogrulayan bir deger nesnesi olarak temsil etmek.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if not isinstance(self.start, date) or not isinstance(self.end, date):
            raise TypeError("DateRange.start ve end birer datetime.date olmalidir.")
        if self.start > self.end:
            raise ValueError(
                f"Gecersiz tarih araligi: start ({self.start}) > end ({self.end})."
            )

    @property
    def days(self) -> int:
        """Aralik gun sayisi (her iki uc dahil)."""
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Period:
    """
    Neden: Bir tarih araligini granularitesi ile birlikte tek bir extraction
    talebi parametresi olarak baglamak.
    """

    date_range: DateRange
    granularity: Granularity

    @property
    def start(self) -> date:
        return self.date_range.start

    @property
    def end(self) -> date:
        return self.date_range.end
