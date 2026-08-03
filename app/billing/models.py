"""
Neden: Billing katmanının DTO'ları ve alan hataları (ADR-0002).
Hatalar ayrı bir modül yerine burada tutulur — Sprint A'nın dosya bütçesi
`app/billing/` için üç dosyayla sınırlıdır (CLAUDE.md: tek task <= 10 dosya).
"""
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

# Neden: Sabit tarife tipi tek yerde tanımlansın; ileride başka tarifeler
# eklenirse şema değişmeden genişler (bkz. BillingRate.rate_type).
RATE_TYPE_EXCESS_SALE = "EXCESS_SALE_UNIT_PRICE"

STATUS_PENDING_RATE = "PENDING_RATE"
STATUS_LOCKED = "LOCKED"


class BillingError(Exception):
    """Billing katmanının temel hata tipi."""


class BillingValidationError(BillingError):
    """Neden: Geçersiz girdi (negatif fiyat, ayın 1'i olmayan valid_from vb.)."""


class BillingLockedError(BillingError):
    """
    Neden: LOCKED bir ayın katsayısını değiştirme denemesi. Düzeltme için ayrı bir
    override akışı gerekir; ADR-0002'de kapsam dışı bırakıldı (ROADMAP teknik borç).
    """


class BillingMonthNotFoundError(BillingError):
    """
    Neden: Henüz hesaplanmamış bir ay için OSB birim fiyatı girilmeye çalışıldı.
    Ay önce mahsuplaşma job'ı ile hesaplanmalıdır (monthly_billing satırı orada açılır).
    """


class BillingRateExistsError(BillingError):
    """Neden: Aynı tarife tipi + valid_from için ikinci bir kayıt (append-only ihlali)."""


@dataclass(frozen=True)
class BillingRateDto:
    """Neden: billing_rate satırının katman dışına taşınan salt-okunur temsili."""

    id: Optional[int]
    rate_type: str
    unit_price_try: Decimal
    valid_from: date
    created_by: str
    created_at: Optional[datetime] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["unit_price_try"] = str(self.unit_price_try)
        data["valid_from"] = self.valid_from.isoformat() if self.valid_from else None
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        return data


@dataclass(frozen=True)
class MonthlyBillingResult:
    """
    Neden: Bir ayın finansal sonucunun katman dışına taşınan temsili.

    Tutarlar KDV HARİÇ (net) TL'dir. status PENDING_RATE ise osb_deduction_try
    None'dır — çağıran taraf bunu "Bekleniyor" olarak göstermelidir, 0 olarak değil
    (ADR-0002 §6; sessiz hata yok kuralı).
    """

    year: int
    month: int
    status: str
    excess_sale_rate_try: Optional[Decimal] = None
    osb_unit_price_try: Optional[Decimal] = None
    production_kwh: Optional[Decimal] = None
    excess_sale_kwh: Optional[Decimal] = None
    excess_sale_invoice_try: Optional[Decimal] = None
    osb_deduction_try: Optional[Decimal] = None
    locked_at: Optional[datetime] = None
    # Neden: OSB birim fiyatının denetim izi (kim/ne zaman girdi) repository dict'inde
    # vardı ama DTO'da düşüyordu; dashboard'daki OSB geçmiş tablosu bunu gösteriyor.
    osb_price_entered_by: Optional[str] = None
    osb_price_entered_at: Optional[datetime] = None

    @property
    def is_locked(self) -> bool:
        return self.status == STATUS_LOCKED

    def to_dict(self) -> Dict[str, Any]:
        def _num(value: Optional[Decimal]) -> Optional[str]:
            return str(value) if value is not None else None

        return {
            "year": self.year,
            "month": self.month,
            "status": self.status,
            "excess_sale_rate_try": _num(self.excess_sale_rate_try),
            "osb_unit_price_try": _num(self.osb_unit_price_try),
            "production_kwh": _num(self.production_kwh),
            "excess_sale_kwh": _num(self.excess_sale_kwh),
            "excess_sale_invoice_try": _num(self.excess_sale_invoice_try),
            "osb_deduction_try": _num(self.osb_deduction_try),
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "osb_price_entered_by": self.osb_price_entered_by,
            "osb_price_entered_at": (
                self.osb_price_entered_at.isoformat() if self.osb_price_entered_at else None
            ),
        }
