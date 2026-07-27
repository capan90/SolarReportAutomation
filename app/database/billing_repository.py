"""
Neden: billing_rate ve monthly_billing tablolarının persistans katmanı (ADR-0002).
Kilit garantileri (append-only tarife, aya kilitlenen katsayı snapshot'ı) BURADA
uygulanır — servis katmanındaki bir hata veya ileride eklenecek başka bir çağıran
kilidi atlayamasın diye.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError

from app.billing.models import (
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
    BillingLockedError,
    BillingMonthNotFoundError,
    BillingRateExistsError,
)
from app.core.logger import setup_logger
from app.database.db_session import SessionLocal, create_tables
from app.database.models import BillingRate, MonthlyBilling

logger = setup_logger("BillingRepository")


def _rate_to_dict(row: BillingRate) -> Dict[str, Any]:
    return {
        "id": row.id,
        "rate_type": row.rate_type,
        "unit_price_try": Decimal(str(row.unit_price_try)),
        "valid_from": row.valid_from,
        "created_at": row.created_at,
        "created_by": row.created_by,
        "note": row.note,
    }


def _monthly_to_dict(row: MonthlyBilling) -> Dict[str, Any]:
    def _dec(value) -> Optional[Decimal]:
        return Decimal(str(value)) if value is not None else None

    return {
        "year": row.year,
        "month": row.month,
        "status": row.status,
        "excess_sale_rate_try": _dec(row.excess_sale_rate_try),
        "excess_sale_rate_id": row.excess_sale_rate_id,
        "osb_unit_price_try": _dec(row.osb_unit_price_try),
        "osb_price_entered_by": row.osb_price_entered_by,
        "osb_price_entered_at": row.osb_price_entered_at,
        "production_kwh_snapshot": _dec(row.production_kwh_snapshot),
        "excess_sale_kwh_snapshot": _dec(row.excess_sale_kwh_snapshot),
        "excess_sale_invoice_try": _dec(row.excess_sale_invoice_try),
        "osb_deduction_try": _dec(row.osb_deduction_try),
        "locked_at": row.locked_at,
    }


class BillingRepository:
    """
    Neden: Faturalama verisinin tek yazma kapısı. Kilit kuralları:

    1. billing_rate APPEND-ONLY — güncelleme metodu yoktur.
    2. monthly_billing.excess_sale_rate_try bir kez yazılır; NULL değilse bir daha
       değişmez (status'tan bağımsız — snapshot dokunulmazlığı).
    3. status LOCKED iken osb_unit_price_try değiştirilemez.
    4. kWh snapshot'ları ve türetilmiş tutarlar her hesapta güncellenebilir —
       kilitlenen katsayıdır, tutar değildir (ADR-0002 §4).
    """

    def __init__(self):
        # Neden: create_all idempotenttir; SettlementRepository ile aynı kalıp.
        create_tables()

    # ------------------------------------------------------------------
    # billing_rate (append-only)
    # ------------------------------------------------------------------
    def add_rate(
        self,
        rate_type: str,
        unit_price_try: Decimal,
        valid_from: date,
        created_by: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Neden: Yeni tarife satırı ekler. UPDATE yoktur — değişiklik yeni satırdır.
        Aynı (rate_type, valid_from) ikilisi zaten varsa BillingRateExistsError.
        """
        session = SessionLocal()
        try:
            row = BillingRate(
                rate_type=rate_type,
                unit_price_try=unit_price_try,
                valid_from=valid_from,
                created_by=created_by,
                note=note,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            logger.info(
                "Tarife eklendi: %s = %s TL/kWh (geçerlilik: %s, ekleyen: %s)",
                rate_type, unit_price_try, valid_from, created_by,
            )
            return _rate_to_dict(row)
        except IntegrityError:
            session.rollback()
            logger.warning(
                "Tarife eklenemedi — %s için %s tarihli kayıt zaten var.",
                rate_type, valid_from,
            )
            raise BillingRateExistsError(
                f"{rate_type} tarifesi için {valid_from} tarihli kayıt zaten mevcut."
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_effective_rate(self, rate_type: str, as_of: date) -> Optional[Dict[str, Any]]:
        """
        Neden: Verilen tarihte geçerli tarifeyi döner: valid_from <= as_of olan
        kayıtlar içinde valid_from'u en büyük olan. Yoksa None.

        as_of olarak ayın SON günü verilir (bkz. BillingService) — ay içinde
        başlayan bir tarife o ayın tamamına uygulanır.
        """
        session = SessionLocal()
        try:
            row = (
                session.query(BillingRate)
                .filter(BillingRate.rate_type == rate_type, BillingRate.valid_from <= as_of)
                .order_by(BillingRate.valid_from.desc(), BillingRate.id.desc())
                .first()
            )
            return _rate_to_dict(row) if row else None
        finally:
            session.close()

    def list_rates(self, rate_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Neden: Dashboard'da katsayı geçmişini göstermek (Sprint B)."""
        session = SessionLocal()
        try:
            rows = (
                session.query(BillingRate)
                .filter(BillingRate.rate_type == rate_type)
                .order_by(BillingRate.valid_from.desc(), BillingRate.id.desc())
                .limit(limit)
                .all()
            )
            return [_rate_to_dict(r) for r in rows]
        finally:
            session.close()

    # ------------------------------------------------------------------
    # monthly_billing
    # ------------------------------------------------------------------
    def get_monthly(self, year: int, month: int) -> Optional[Dict[str, Any]]:
        session = SessionLocal()
        try:
            row = (
                session.query(MonthlyBilling)
                .filter(MonthlyBilling.year == year, MonthlyBilling.month == month)
                .first()
            )
            return _monthly_to_dict(row) if row else None
        finally:
            session.close()

    def upsert_monthly(
        self,
        year: int,
        month: int,
        production_kwh: Optional[Decimal],
        excess_sale_kwh: Optional[Decimal],
        excess_sale_invoice_try: Optional[Decimal],
        osb_deduction_try: Optional[Decimal],
        rate_snapshot_try: Optional[Decimal] = None,
        rate_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Neden: Ayın finansal satırını ekler/günceller.

        Kilit davranışı:
        - excess_sale_rate_try YALNIZCA halihazırda NULL ise yazılır. Doluysa gelen
          değer yok sayılır; farklıysa uyarı loglanır (snapshot dokunulmazlığı).
        - osb_unit_price_try bu metotla HİÇ yazılmaz; yalnızca set_osb_price ile.
        - kWh snapshot'ları ve tutarlar her çağrıda güncellenir.
        - status: osb_unit_price_try doluysa LOCKED korunur, aksi halde PENDING_RATE.
        """
        session = SessionLocal()
        try:
            row = (
                session.query(MonthlyBilling)
                .filter(MonthlyBilling.year == year, MonthlyBilling.month == month)
                .first()
            )
            if row is None:
                row = MonthlyBilling(year=year, month=month, status=STATUS_PENDING_RATE)
                session.add(row)

            if row.excess_sale_rate_try is None:
                if rate_snapshot_try is not None:
                    row.excess_sale_rate_try = rate_snapshot_try
                    row.excess_sale_rate_id = rate_id
                    logger.info(
                        "%04d-%02d için fazla satış katsayısı kilitlendi: %s TL/kWh",
                        year, month, rate_snapshot_try,
                    )
            elif rate_snapshot_try is not None and Decimal(str(row.excess_sale_rate_try)) != rate_snapshot_try:
                # Neden: Sessiz hata yok — snapshot korunuyor ama fark loglanıyor.
                logger.warning(
                    "%04d-%02d için kilitli katsayı %s; yeni değer %s YOK SAYILDI "
                    "(geçmiş aylar katsayı değişikliğinden etkilenmez).",
                    year, month, row.excess_sale_rate_try, rate_snapshot_try,
                )

            row.production_kwh_snapshot = production_kwh
            row.excess_sale_kwh_snapshot = excess_sale_kwh
            row.excess_sale_invoice_try = excess_sale_invoice_try
            row.osb_deduction_try = osb_deduction_try
            row.status = STATUS_LOCKED if row.osb_unit_price_try is not None else STATUS_PENDING_RATE

            session.commit()
            session.refresh(row)
            logger.info("monthly_billing upsert tamamlandı: %04d-%02d (%s)", year, month, row.status)
            return _monthly_to_dict(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_osb_price(
        self,
        year: int,
        month: int,
        unit_price_try: Decimal,
        entered_by: str,
        osb_deduction_try: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Neden: OSB birim fiyatını bir kez yazar ve ayı kilitler.
        Satır yoksa BillingMonthNotFoundError, zaten LOCKED ise BillingLockedError.
        """
        session = SessionLocal()
        try:
            row = (
                session.query(MonthlyBilling)
                .filter(MonthlyBilling.year == year, MonthlyBilling.month == month)
                .first()
            )
            if row is None:
                raise BillingMonthNotFoundError(
                    f"{year}-{month:02d} için faturalama kaydı yok; önce aylık mahsuplaşma hesaplanmalı."
                )
            if row.status == STATUS_LOCKED or row.osb_unit_price_try is not None:
                logger.warning(
                    "%04d-%02d kilitli; OSB birim fiyatı değiştirme denemesi reddedildi (deneyen: %s).",
                    year, month, entered_by,
                )
                raise BillingLockedError(
                    f"{year}-{month:02d} ayı kilitli; OSB birim fiyatı değiştirilemez."
                )

            row.osb_unit_price_try = unit_price_try
            row.osb_price_entered_by = entered_by
            row.osb_price_entered_at = datetime.utcnow()
            row.osb_deduction_try = osb_deduction_try
            row.status = STATUS_LOCKED
            row.locked_at = datetime.utcnow()

            session.commit()
            session.refresh(row)
            logger.info(
                "%04d-%02d OSB birim fiyatı girildi ve ay kilitlendi: %s TL/kWh (giren: %s)",
                year, month, unit_price_try, entered_by,
            )
            return _monthly_to_dict(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
