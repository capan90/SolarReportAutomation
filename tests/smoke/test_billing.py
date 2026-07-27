"""
Neden: Billing katmanının (ADR-0002) kilit garantilerini duman testiyle sabitlemek.
Kapsam: append-only tarife, aya kilitlenen katsayı snapshot'ı, LOCKED guard,
tutarsız veride PENDING davranışı ve Decimal/ROUND_HALF_UP yuvarlaması.

Gerçek veritabanına DOKUNULMAZ: her test tmp_path altında kendi SQLite dosyasını
kurar ve billing_repository'nin SessionLocal'ını oraya yönlendirir.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.billing_repository as billing_repo_module
from app.billing import (
    BillingLockedError,
    BillingMonthNotFoundError,
    BillingRateExistsError,
    BillingService,
    BillingValidationError,
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
)
from app.database.db_session import Base

JUL = (2026, 7)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Neden: İzole SQLite; testler solar_report_db.sqlite'ı kirletmemeli."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'billing_test.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(billing_repo_module, "SessionLocal", TestSession)
    # Neden: create_tables gerçek engine'e bağlıdır; fixture tabloları zaten kurdu.
    monkeypatch.setattr(billing_repo_module, "create_tables", lambda: None)
    return billing_repo_module.BillingRepository()


@pytest.fixture
def service(repo):
    return BillingService(repository=repo)


# ----------------------------------------------------------------------
# 1. Tarife: append-only ve doğrulama
# ----------------------------------------------------------------------
def test_set_rate_is_append_only(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    service.set_rate("3.100000", date(2026, 8, 1), created_by="admin")

    history = service.list_rate_history()
    assert len(history) == 2
    # En güncel valid_from başta
    assert history[0].valid_from == date(2026, 8, 1)
    assert history[1].unit_price_try == Decimal("2.909687")


def test_duplicate_valid_from_rejected(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    with pytest.raises(BillingRateExistsError):
        service.set_rate("3.000000", date(2026, 6, 1), created_by="admin")


def test_valid_from_must_be_first_day_of_month(service):
    with pytest.raises(BillingValidationError, match="ayın ilk günü"):
        service.set_rate("2.909687", date(2026, 6, 15), created_by="admin")


def test_rate_must_be_positive(service):
    with pytest.raises(BillingValidationError, match="pozitif"):
        service.set_rate("0", date(2026, 6, 1), created_by="admin")


def test_created_by_required(service):
    with pytest.raises(BillingValidationError, match="created_by"):
        service.set_rate("2.909687", date(2026, 6, 1), created_by="  ")


def test_effective_rate_uses_valid_from_not_insertion_order(service):
    # Neden: Geçmiş ay yeniden hesaplanırken "en son eklenen" değil, o ayda
    # GEÇERLİ olan tarife kullanılmalı.
    service.set_rate("3.100000", date(2026, 8, 1), created_by="admin")
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")

    assert service.get_current_rate(as_of=date(2026, 7, 31)).unit_price_try == Decimal("2.909687")
    assert service.get_current_rate(as_of=date(2026, 8, 31)).unit_price_try == Decimal("3.100000")


def test_no_rate_defined_returns_none(service):
    assert service.get_current_rate(as_of=date(2026, 7, 31)) is None


# ----------------------------------------------------------------------
# 2. Aylık hesap ve snapshot kilidi
# ----------------------------------------------------------------------
def test_compute_creates_pending_row_with_invoice(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    result = service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)

    assert result.status == STATUS_PENDING_RATE
    assert result.excess_sale_rate_try == Decimal("2.909687")
    # 1000 × 2.909687 = 2909.687 -> 2909.69
    assert result.excess_sale_invoice_try == Decimal("2909.69")
    # OSB katsayısı girilmedi -> kesinti "Bekleniyor" (None), 0 DEĞİL
    assert result.osb_deduction_try is None


def test_rate_change_does_not_affect_computed_month(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    first = service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)
    assert first.excess_sale_invoice_try == Decimal("2909.69")

    # Katsayı Temmuz'un içinde geçerli olacak şekilde değiştiriliyor
    service.set_rate("5.000000", date(2026, 7, 1), created_by="admin")
    again = service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)

    # Snapshot kilitli: eski katsayı korunur
    assert again.excess_sale_rate_try == Decimal("2.909687")
    assert again.excess_sale_invoice_try == Decimal("2909.69")


def test_recompute_updates_amount_with_locked_rate(service):
    # Neden: Kilitlenen KATSAYIDIR; kWh sonradan tamamlanırsa tutar yeniden türetilir.
    service.set_rate("2.000000", date(2026, 6, 1), created_by="admin")
    service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)

    updated = service.compute(*JUL, production_kwh=12000.0, excess_sale_kwh=1500.0)
    assert updated.excess_sale_rate_try == Decimal("2.000000")
    assert updated.excess_sale_kwh == Decimal("1500.0")
    assert updated.excess_sale_invoice_try == Decimal("3000.00")


def test_repository_rejects_snapshot_overwrite(repo):
    # Neden: Kilit servis katmanına değil repository'ye ait — başka bir çağıran
    # eklendiğinde de snapshot korunmalı.
    repo.upsert_monthly(
        year=2026, month=7,
        production_kwh=Decimal("100"), excess_sale_kwh=Decimal("10"),
        excess_sale_invoice_try=Decimal("20.00"), osb_deduction_try=None,
        rate_snapshot_try=Decimal("2.000000"), rate_id=None,
    )
    row = repo.upsert_monthly(
        year=2026, month=7,
        production_kwh=Decimal("100"), excess_sale_kwh=Decimal("10"),
        excess_sale_invoice_try=Decimal("99.00"), osb_deduction_try=None,
        rate_snapshot_try=Decimal("9.999999"), rate_id=None,
    )
    assert row["excess_sale_rate_try"] == Decimal("2.000000")


def test_compute_without_rate_leaves_invoice_none(service):
    result = service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)
    assert result.status == STATUS_PENDING_RATE
    assert result.excess_sale_rate_try is None
    assert result.excess_sale_invoice_try is None


# ----------------------------------------------------------------------
# 3. LOCKED guard
# ----------------------------------------------------------------------
def test_osb_price_computes_deduction_and_locks(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)

    locked = service.set_osb_unit_price(*JUL, unit_price_try="1.500000", entered_by="admin")

    assert locked.status == STATUS_LOCKED
    assert locked.is_locked is True
    assert locked.locked_at is not None
    # (10000 - 1000) × 1.5 = 13500.00
    assert locked.osb_deduction_try == Decimal("13500.00")


def test_locked_month_rejects_second_price(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)
    service.set_osb_unit_price(*JUL, unit_price_try="1.500000", entered_by="admin")

    with pytest.raises(BillingLockedError, match="kilitli"):
        service.set_osb_unit_price(*JUL, unit_price_try="9.000000", entered_by="admin")


def test_osb_price_on_uncomputed_month_raises(service):
    with pytest.raises(BillingMonthNotFoundError):
        service.set_osb_unit_price(2026, 5, unit_price_try="1.500000", entered_by="admin")


def test_recompute_after_lock_preserves_price_and_status(service):
    service.set_rate("2.000000", date(2026, 6, 1), created_by="admin")
    service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)
    service.set_osb_unit_price(*JUL, unit_price_try="1.500000", entered_by="admin")

    again = service.compute(*JUL, production_kwh=20000.0, excess_sale_kwh=2000.0)
    assert again.status == STATUS_LOCKED
    assert again.osb_unit_price_try == Decimal("1.500000")
    # Kesinti kilitli fiyatla yeniden türetildi: (20000 - 2000) × 1.5
    assert again.osb_deduction_try == Decimal("27000.00")


def test_osb_price_must_be_positive(service):
    service.set_rate("2.000000", date(2026, 6, 1), created_by="admin")
    service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=1000.0)
    with pytest.raises(BillingValidationError, match="pozitif"):
        service.set_osb_unit_price(*JUL, unit_price_try="-1", entered_by="admin")


# ----------------------------------------------------------------------
# 4. Tutarsız veri -> PENDING, sessiz kırpma yok
# ----------------------------------------------------------------------
def test_negative_production_stays_pending_without_amounts(service):
    service.set_rate("2.000000", date(2026, 6, 1), created_by="admin")
    result = service.compute(*JUL, production_kwh=-5.0, excess_sale_kwh=1000.0)

    assert result.status == STATUS_PENDING_RATE
    assert result.excess_sale_invoice_try is None
    assert result.osb_deduction_try is None
    # Tutarsız kWh snapshot'a yazılmaz
    assert result.production_kwh is None


def test_excess_greater_than_production_stays_pending(service):
    # Neden: (üretim - fazla satış) negatif olurdu; sessizce 0'a kırpılmaz.
    service.set_rate("2.000000", date(2026, 6, 1), created_by="admin")
    result = service.compute(*JUL, production_kwh=100.0, excess_sale_kwh=500.0)

    assert result.status == STATUS_PENDING_RATE
    assert result.excess_sale_invoice_try is None
    assert result.osb_deduction_try is None


def test_invalid_input_type_raises(service):
    with pytest.raises(BillingValidationError):
        service.compute(*JUL, production_kwh="abc", excess_sale_kwh=1000.0)


# ----------------------------------------------------------------------
# 5. Decimal / yuvarlama
# ----------------------------------------------------------------------
def test_rounding_is_half_up_not_half_even(service):
    # Neden: 0.125 -> ROUND_HALF_UP 0.13; bankacılık varsayılanı HALF_EVEN 0.12 verirdi.
    service.set_rate("0.125000", date(2026, 6, 1), created_by="admin")
    result = service.compute(*JUL, production_kwh=10.0, excess_sale_kwh=1.0)
    assert result.excess_sale_invoice_try == Decimal("0.13")


def test_float_input_does_not_leak_binary_artifacts(service):
    # Neden: Decimal(float) ikili gösterim artığı taşır; str üzerinden çevriliyor.
    service.set_rate("1.000000", date(2026, 6, 1), created_by="admin")
    result = service.compute(*JUL, production_kwh=1.0, excess_sale_kwh=0.1)
    assert result.excess_sale_invoice_try == Decimal("0.10")


def test_amounts_are_quantized_to_two_places(service):
    service.set_rate("2.909687", date(2026, 6, 1), created_by="admin")
    result = service.compute(*JUL, production_kwh=10000.0, excess_sale_kwh=3333.0)
    assert result.excess_sale_invoice_try.as_tuple().exponent == -2
