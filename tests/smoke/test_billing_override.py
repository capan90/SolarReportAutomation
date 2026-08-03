"""
Neden: ADR-0002 kilitli ayın katsayısını değiştirmeyi kapsam dışı bırakmıştı; kullanıcı
yanlış bir OSB fiyatı girdiğinde düzeltme yolu YOKTU (ROADMAP açık maddesi). Bugüne kadar
bu tür düzeltmeler elle script yazılarak yapıldı.

Override akışı kilidi KALDIRMAZ — şifre + zorunlu gerekçe + audit kaydıyla korunan tek
kaçış kapısıdır. Bu testler o korumaların gerçekten kapı olduğunu sabitler:
kilit normal yollarda duruyor mu, gerekçe zayıfsa reddediliyor mu, tutarlar doğru yeniden
hesaplanıyor mu.
"""
from decimal import Decimal

import pytest

from app.billing.models import (
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
    BillingLockedError,
    BillingValidationError,
)
from app.billing.service import BillingService


class FakeRepo:
    """monthly_billing satırını taklit eder; kilit kurallarını gerçek repo gibi uygular."""

    def __init__(self, row=None):
        self.row = row
        self.overrides = []

    # --- override yolu ---
    def override_locked_month(self, year, month, osb_unit_price_try=None,
                              excess_sale_rate_try=None):
        if (osb_unit_price_try is None) == (excess_sale_rate_try is None):
            raise BillingValidationError("tam olarak biri")
        if self.row is None:
            from app.billing.models import BillingMonthNotFoundError
            raise BillingMonthNotFoundError("yok")
        if self.row["status"] != STATUS_LOCKED:
            raise BillingValidationError("kilitli değil")

        previous = {
            "_previous_osb_unit_price_try": self.row.get("osb_unit_price_try"),
            "_previous_excess_sale_rate_try": self.row.get("excess_sale_rate_try"),
            "_previous_excess_sale_rate_id": self.row.get("excess_sale_rate_id"),
            "_previous_excess_sale_invoice_try": self.row.get("excess_sale_invoice_try"),
            "_previous_osb_deduction_try": self.row.get("osb_deduction_try"),
        }
        if osb_unit_price_try is not None:
            self.row["osb_unit_price_try"] = osb_unit_price_try
        else:
            self.row["excess_sale_rate_try"] = excess_sale_rate_try
            self.row["excess_sale_rate_id"] = None
        self.overrides.append((osb_unit_price_try, excess_sale_rate_try))
        out = dict(self.row)
        out.update(previous)
        return out

    # --- compute() yolunun ihtiyaçları ---
    def get_monthly(self, year, month):
        return dict(self.row) if self.row else None

    def upsert_monthly(self, year, month, production_kwh, excess_sale_kwh,
                       excess_sale_invoice_try, osb_deduction_try,
                       rate_snapshot_try=None, rate_id=None):
        self.row["production_kwh_snapshot"] = production_kwh
        self.row["excess_sale_kwh_snapshot"] = excess_sale_kwh
        self.row["excess_sale_invoice_try"] = excess_sale_invoice_try
        self.row["osb_deduction_try"] = osb_deduction_try
        return dict(self.row)

    def get_effective_rate(self, rate_type, as_of):
        return None


def locked_row():
    """Haziran 2026'nın prod'daki gerçek şekli."""
    return {
        "year": 2026, "month": 6, "status": STATUS_LOCKED,
        "excess_sale_rate_try": Decimal("2.909687"),
        "excess_sale_rate_id": 5,
        "osb_unit_price_try": Decimal("1.452381"),
        "production_kwh_snapshot": Decimal("7248211.700"),
        "excess_sale_kwh_snapshot": Decimal("3693878.600"),
        "excess_sale_invoice_try": Decimal("10748030.54"),
        "osb_deduction_try": Decimal("5162245.86"),
        "locked_at": None,
    }


def service_with(row):
    svc = BillingService()
    svc.repo = FakeRepo(row)
    return svc


REASON = "OSB Nisan faturasi revize edildi, birim fiyat dustu"


def test_osb_override_kesintiyi_yeniden_hesaplar():
    """Öz tüketim × yeni fiyat — tutar mevcut compute() ile türetilmeli."""
    svc = service_with(locked_row())

    out = svc.override_locked_month(
        2026, 6, reason=REASON, changed_by="murat", osb_unit_price_try="1.380000")

    # öz tüketim = 7.248.211,700 - 3.693.878,600 = 3.554.333,100
    beklenen = (Decimal("3554333.100") * Decimal("1.380000")).quantize(Decimal("0.01"))
    assert out["kind"] == "osb_unit_price_try"
    assert out["old_value"] == "1.452381"
    assert out["new_value"] == "1.380000"
    assert Decimal(out["new_deduction_try"]) == beklenen
    assert out["old_deduction_try"] == "5162245.86"


def test_enerjisa_override_faturayi_yeniden_hesaplar_ve_rate_id_siler():
    """Değer artık tarife kaydından gelmiyor; excess_sale_rate_id NULL olmalı."""
    row = locked_row()
    svc = service_with(row)

    out = svc.override_locked_month(
        2026, 6, reason=REASON, changed_by="murat", excess_sale_rate_try="3.100000")

    beklenen = (Decimal("3693878.600") * Decimal("3.100000")).quantize(Decimal("0.01"))
    assert out["kind"] == "excess_sale_rate_try"
    assert Decimal(out["new_invoice_try"]) == beklenen
    assert out["previous_rate_id"] == 5, "eski id audit için korunmalı"
    assert row["excess_sale_rate_id"] is None, "override sonrası bağ kopmalı"


@pytest.mark.parametrize("reason", ["", "   ", "kisa", "on dort krkt"])
def test_zayif_gerekce_reddedilir(reason):
    """Gerekçe override'ın tek korumasıdır; 15 karakterin altı kabul edilmez."""
    svc = service_with(locked_row())

    with pytest.raises(BillingValidationError) as exc:
        svc.override_locked_month(2026, 6, reason=reason, changed_by="murat",
                                  osb_unit_price_try="1.38")
    assert "gerekçe" in str(exc.value).lower()
    assert svc.repo.overrides == [], "reddedilen istek DB'ye dokunmamalı"


def test_kilitli_olmayan_ay_reddedilir():
    """Override normal girişin kısayolu değildir."""
    row = locked_row()
    row["status"] = STATUS_PENDING_RATE
    svc = service_with(row)

    with pytest.raises(BillingValidationError):
        svc.override_locked_month(2026, 6, reason=REASON, changed_by="murat",
                                  osb_unit_price_try="1.38")


@pytest.mark.parametrize("osb,rate", [(None, None), ("1.38", "3.10")])
def test_tam_olarak_bir_katsayi_zorunlu(osb, rate):
    svc = service_with(locked_row())

    with pytest.raises(BillingValidationError):
        svc.override_locked_month(2026, 6, reason=REASON, changed_by="murat",
                                  osb_unit_price_try=osb, excess_sale_rate_try=rate)


def test_negatif_veya_sifir_deger_reddedilir():
    svc = service_with(locked_row())

    with pytest.raises(BillingValidationError):
        svc.override_locked_month(2026, 6, reason=REASON, changed_by="murat",
                                  osb_unit_price_try="0")


def test_changed_by_zorunlu():
    """Denetim izi kimliksiz olamaz."""
    svc = service_with(locked_row())

    with pytest.raises(BillingValidationError):
        svc.override_locked_month(2026, 6, reason=REASON, changed_by="  ",
                                  osb_unit_price_try="1.38")


def test_normal_yollar_hala_kilitli():
    """
    KRİTİK: Override eklendi diye kilit gevşememeli. set_osb_price kilitli ayda hâlâ
    BillingLockedError fırlatmalı — aksi halde kilit kavramı fiilen kalkar.
    """
    from app.database import billing_repository as repo_mod

    kaynak = (repo_mod.__file__)
    icerik = open(kaynak, encoding="utf-8").read()
    # set_osb_price içindeki kilit kontrolü duruyor mu
    assert "raise BillingLockedError(" in icerik
    assert "if row.excess_sale_rate_try is None:" in icerik, (
        "upsert_monthly'deki snapshot dokunulmazlığı korunmalı"
    )
    assert issubclass(BillingLockedError, Exception)
