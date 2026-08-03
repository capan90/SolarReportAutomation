"""
Neden: Faturalama iş kuralları (ADR-0002). Settlement Engine'e eklenmedi çünkü
engine saf ve DB'siz kalmalı; ayrıca mahsuplaşma kuralı hiç değişmezken tarife her
ay değişir — farklı değişim hızındaki iki sorumluluk ayrı sınıflarda tutulur.

Hesaplar (her ikisi de KDV HARİÇ / net TL):
  Fazla Satış Faturası = Fazla Satış (kWh)                × sabit katsayı (TL/kWh)
  OSB Kesintisi        = (Üretim - Fazla Satış) (kWh)     × değişken katsayı (TL/kWh)
"""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from app.billing.models import (
    RATE_TYPE_EXCESS_SALE,
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
    BillingRateDto,
    BillingValidationError,
    MonthlyBillingResult,
)
from app.core.logger import setup_logger

logger = setup_logger("BillingService")

# Neden: Tutarlar kuruşa yuvarlanır; bankacılık varsayılanı ROUND_HALF_EVEN fatura
# tutarında beklenmedik aşağı yuvarlama üretir, ROUND_HALF_UP fatura pratiğine uyar.
_MONEY_QUANT = Decimal("0.01")


def _to_decimal(value: Any, field: str) -> Decimal:
    """
    Neden: float kWh değerleri Decimal'e str üzerinden çevrilir; doğrudan
    Decimal(float) ikili gösterim artığı taşır (0.1 -> 0.1000000000000000055...).
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as e:
        raise BillingValidationError(f"{field} sayıya çevrilemedi: {value!r}") from e


def _money(value: Decimal) -> Decimal:
    """Neden: Tutar alanları 2 haneye ROUND_HALF_UP ile sabitlenir."""
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _month_end(year: int, month: int) -> date:
    """Neden: Tarife araması ayın son gününe göre yapılır (ADR-0002 §3)."""
    return date(year, month, calendar.monthrange(year, month)[1])


class BillingService:
    """
    Neden: Faturalama hesaplarının tek giriş noktası. Persistans ve kilit
    garantileri BillingRepository'de; iş kuralları ve yuvarlama burada.
    """

    def __init__(self, repository=None):
        # Neden: Testler sahte repository enjekte edebilsin (DB'siz birim test).
        if repository is None:
            from app.database.billing_repository import BillingRepository

            repository = BillingRepository()
        self.repo = repository

    # ------------------------------------------------------------------
    # Sabit katsayı
    # ------------------------------------------------------------------
    def get_current_rate(self, as_of: Optional[date] = None) -> Optional[BillingRateDto]:
        """
        Neden: Verilen tarihte (varsayılan: bugün) geçerli sabit katsayıyı döner.
        Hiç tarife tanımlanmamışsa None — çağıran taraf bunu "tanımsız" olarak
        göstermeli, 0 olarak değil.
        """
        as_of = as_of or date.today()
        row = self.repo.get_effective_rate(RATE_TYPE_EXCESS_SALE, as_of)
        if row is None:
            logger.warning("%s için geçerli tarife bulunamadı (as_of=%s).", RATE_TYPE_EXCESS_SALE, as_of)
            return None
        return BillingRateDto(
            id=row["id"],
            rate_type=row["rate_type"],
            unit_price_try=row["unit_price_try"],
            valid_from=row["valid_from"],
            created_by=row["created_by"],
            created_at=row.get("created_at"),
            note=row.get("note"),
        )

    def set_rate(
        self,
        unit_price_try: Any,
        valid_from: date,
        created_by: str,
        note: Optional[str] = None,
    ) -> BillingRateDto:
        """
        Neden: Yeni sabit katsayı kaydeder (append-only). Geçmiş aylara etki etmez —
        her ayın katsayısı monthly_billing'e snapshot olarak kilitlenmiştir.

        valid_from ayın İLK GÜNÜ olmak zorundadır (ADR-0002 §2): tarife ay ortasında
        değişemez, aksi halde bir ayın hangi katsayıyla faturalandığı belirsizleşir.
        """
        price = _to_decimal(unit_price_try, "unit_price_try")
        if price <= 0:
            raise BillingValidationError(f"Birim fiyat pozitif olmalıdır: {price}")
        if not isinstance(valid_from, date):
            raise BillingValidationError(f"valid_from bir tarih olmalıdır: {valid_from!r}")
        if valid_from.day != 1:
            raise BillingValidationError(
                f"valid_from ayın ilk günü olmalıdır (verilen: {valid_from.isoformat()})."
            )
        if not str(created_by).strip():
            raise BillingValidationError("created_by boş olamaz (denetim izi zorunlu).")

        row = self.repo.add_rate(
            rate_type=RATE_TYPE_EXCESS_SALE,
            unit_price_try=price,
            valid_from=valid_from,
            created_by=str(created_by).strip(),
            note=note,
        )
        return BillingRateDto(
            id=row["id"],
            rate_type=row["rate_type"],
            unit_price_try=row["unit_price_try"],
            valid_from=row["valid_from"],
            created_by=row["created_by"],
            created_at=row.get("created_at"),
            note=row.get("note"),
        )

    def list_rate_history(self, limit: int = 50) -> List[BillingRateDto]:
        """Neden: Dashboard katsayı geçmişi (Sprint B'de kullanılacak)."""
        return [
            BillingRateDto(
                id=r["id"],
                rate_type=r["rate_type"],
                unit_price_try=r["unit_price_try"],
                valid_from=r["valid_from"],
                created_by=r["created_by"],
                created_at=r.get("created_at"),
                note=r.get("note"),
            )
            for r in self.repo.list_rates(RATE_TYPE_EXCESS_SALE, limit=limit)
        ]

    # ------------------------------------------------------------------
    # Aylık hesap
    # ------------------------------------------------------------------
    def compute(
        self,
        year: int,
        month: int,
        production_kwh: Any,
        excess_sale_kwh: Any,
    ) -> MonthlyBillingResult:
        """
        Neden: Ayın finansal satırını oluşturur/günceller.

        - Satır ilk kez oluşuyorsa o ay için geçerli sabit katsayı snapshot'lanır ve
          bir daha değişmez. Zaten snapshot varsa yeniden okunmaz.
        - Veri tutarsızsa (negatif değer veya fazla satış > üretim) HİÇBİR tutar
          hesaplanmaz; ay PENDING_RATE'te bırakılır ve hata loglanır (ADR-0002 §7).
          Sessizce sıfıra kırpma yapılmaz.
        - OSB birim fiyatı girilmişse kesinti de kilitli fiyatla yeniden türetilir.
        """
        production = _to_decimal(production_kwh, "production_kwh")
        excess = _to_decimal(excess_sale_kwh, "excess_sale_kwh")

        existing = self.repo.get_monthly(year, month)

        # 1. Katsayı snapshot'ı — yalnızca henüz kilitlenmemişse okunur.
        rate_snapshot: Optional[Decimal] = existing.get("excess_sale_rate_try") if existing else None
        rate_id: Optional[int] = existing.get("excess_sale_rate_id") if existing else None
        if rate_snapshot is None:
            current = self.get_current_rate(as_of=_month_end(year, month))
            if current is not None:
                rate_snapshot = current.unit_price_try
                rate_id = current.id
            else:
                logger.error(
                    "%04d-%02d için fazla satış katsayısı tanımlı değil; fatura tutarı "
                    "hesaplanamadı. Dashboard'dan katsayı tanımlanmalı.",
                    year, month,
                )

        # 2. Veri tutarlılığı — kırpma yok, hesap yapılmaz.
        self_consumed: Optional[Decimal] = None
        data_ok = True
        if production < 0 or excess < 0:
            logger.error(
                "%04d-%02d faturalama girdisi negatif (üretim=%s, fazla satış=%s); "
                "tutar hesaplanmadı, ay PENDING_RATE bırakıldı.",
                year, month, production, excess,
            )
            data_ok = False
        elif excess > production:
            logger.error(
                "%04d-%02d fazla satış (%s kWh) üretimden (%s kWh) büyük — veri tutarsız; "
                "tutar hesaplanmadı, ay PENDING_RATE bırakıldı.",
                year, month, excess, production,
            )
            data_ok = False
        else:
            self_consumed = production - excess

        # 3. Tutarları türet.
        invoice_try: Optional[Decimal] = None
        deduction_try: Optional[Decimal] = None
        if data_ok and rate_snapshot is not None:
            invoice_try = _money(excess * rate_snapshot)

        osb_price = existing.get("osb_unit_price_try") if existing else None
        if data_ok and osb_price is not None and self_consumed is not None:
            deduction_try = _money(self_consumed * osb_price)

        row = self.repo.upsert_monthly(
            year=year,
            month=month,
            production_kwh=production if data_ok else None,
            excess_sale_kwh=excess if data_ok else None,
            excess_sale_invoice_try=invoice_try,
            osb_deduction_try=deduction_try,
            rate_snapshot_try=rate_snapshot,
            rate_id=rate_id,
        )
        return self._to_result(row)

    def set_osb_unit_price(
        self,
        year: int,
        month: int,
        unit_price_try: Any,
        entered_by: str,
    ) -> MonthlyBillingResult:
        """
        Neden: Bir önceki ayın gerçek OSB faturasından okunan birim fiyatı girer,
        kesintiyi hesaplar ve ayı kilitler. Kilitli ayda BillingLockedError fırlar
        (düzeltme için override akışı gerekir — ADR-0002'de kapsam dışı).
        """
        price = _to_decimal(unit_price_try, "osb_unit_price_try")
        if price <= 0:
            raise BillingValidationError(f"OSB birim fiyatı pozitif olmalıdır: {price}")
        if not str(entered_by).strip():
            raise BillingValidationError("entered_by boş olamaz (denetim izi zorunlu).")

        existing = self.repo.get_monthly(year, month)
        deduction_try: Optional[Decimal] = None
        if existing:
            production = existing.get("production_kwh_snapshot")
            excess = existing.get("excess_sale_kwh_snapshot")
            if production is not None and excess is not None:
                deduction_try = _money((production - excess) * price)
            else:
                # Neden: kWh snapshot'ı yoksa (tutarsız veri) tutar üretilemez; ay
                # kilitlenir ama kesinti bir sonraki hesapta türetilir.
                logger.warning(
                    "%04d-%02d kWh snapshot'ı yok; OSB kesintisi şimdilik hesaplanamadı.",
                    year, month,
                )

        row = self.repo.set_osb_price(
            year=year,
            month=month,
            unit_price_try=price,
            entered_by=str(entered_by).strip(),
            osb_deduction_try=deduction_try,
        )
        return self._to_result(row)

    def get_monthly(self, year: int, month: int) -> Optional[MonthlyBillingResult]:
        row = self.repo.get_monthly(year, month)
        return self._to_result(row) if row else None

    def list_pending_months(self, limit: int = 24) -> List[MonthlyBillingResult]:
        """
        Neden: OSB birim fiyatı bekleyen aylar (dashboard banner'ı). En yeni başta.
        Tümü döner; kaç tanesinin gösterileceğine sunum katmanı karar verir.
        """
        return [self._to_result(r) for r in self.repo.list_pending_months(limit=limit)]

    def list_months(self, limit: int = 24) -> List[MonthlyBillingResult]:
        """
        Neden: OSB birim fiyatının geçmişi hiçbir ekranda görünmüyordu — giriş yalnızca
        bekleyen ay varken banner'dan açılan modaldan yapılabiliyor, girildikten sonra
        "hangi aya hangi fiyat, kim, ne zaman girdi" sorusunun cevabı kayboluyordu.
        Enerjisa katsayısının append-only geçmiş tablosu vardı, OSB'nin karşılığı yoktu.

        Bekleyen ve kilitli TÜM ayları en yeniden eskiye döner (salt-okunur).
        """
        return [self._to_result(r) for r in self.repo.list_months(limit=limit)]

    @staticmethod
    def _to_result(row: Dict[str, Any]) -> MonthlyBillingResult:
        return MonthlyBillingResult(
            year=row["year"],
            month=row["month"],
            status=row.get("status") or STATUS_PENDING_RATE,
            excess_sale_rate_try=row.get("excess_sale_rate_try"),
            osb_unit_price_try=row.get("osb_unit_price_try"),
            production_kwh=row.get("production_kwh_snapshot"),
            excess_sale_kwh=row.get("excess_sale_kwh_snapshot"),
            excess_sale_invoice_try=row.get("excess_sale_invoice_try"),
            osb_deduction_try=row.get("osb_deduction_try"),
            locked_at=row.get("locked_at"),
            osb_price_entered_by=row.get("osb_price_entered_by"),
            osb_price_entered_at=row.get("osb_price_entered_at"),
        )


__all__ = ["BillingService", "STATUS_LOCKED", "STATUS_PENDING_RATE"]
