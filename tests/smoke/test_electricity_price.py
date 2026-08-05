"""
Neden: OSB katsayısı aslında türetilmiş bir değer — bir ayın katsayısı BİR ÖNCEKİ ayın
faturasındaki elektrik birim fiyatıdır (mevcut OSB modalinin metni de bunu söylüyor;
Mayıs katsayısı 0.810049 = Nisan faturası, Haziran 1.452381 = Mayıs faturası). Bu akış
kullanıcıyı katsayı yerine kaynağı girmeye taşıyor.

Bu testler dört garantiyi sabitler:
1. Ay kaydırması (N -> N+1) doğru, Aralık→Ocak dahil.
2. Hedef hazır değilse BEKLETİLİR; hazır olduğunda compute() kancasıyla uygulanır.
3. Hedef KİLİTLİ ve değer değiştiyse OTOMATİK ZİNCİRLEME YAPILMAZ — kilitli ayın
   tutarı şifre + gerekçe olmadan değişmemeli.
4. Kanca best-effort: kaynak kütüğündeki hata mahsuplaşma yazımını düşürmez.
"""
from decimal import Decimal

import pytest

from app.billing.models import (
    PRICE_STATUS_APPLIED,
    PRICE_STATUS_CORRECTION_PENDING,
    PRICE_STATUS_PENDING,
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
    BillingValidationError,
)
from app.billing.service import BillingService


class FakeRepo:
    """monthly_billing + monthly_electricity_price davranışını taklit eder."""

    def __init__(self, months=None):
        self.months = months or {}
        self.prices = {}
        self.set_osb_calls = []

    # --- kaynak kütüğü ---
    def upsert_electricity_price(self, source_year, source_month, unit_price_try,
                                 target_year, target_month, created_by,
                                 note=None, status=None):
        key = (source_year, source_month)
        prev = self.prices.get(key, {}).get("unit_price_try")
        row = {
            "source_year": source_year, "source_month": source_month,
            "unit_price_try": unit_price_try,
            "target_year": target_year, "target_month": target_month,
            "status": status or PRICE_STATUS_PENDING,
            "applied_at": None, "applied_by": None,
            "created_by": created_by, "created_at": None, "note": note,
        }
        self.prices[key] = row
        out = dict(row)
        out["_previous_unit_price_try"] = prev
        return out

    def get_electricity_price_for_target(self, target_year, target_month):
        for row in self.prices.values():
            if (row["target_year"], row["target_month"]) == (target_year, target_month):
                return dict(row)
        return None

    def list_electricity_prices(self, limit=24):
        return [dict(r) for r in self.prices.values()]

    def mark_electricity_price_status(self, source_year, source_month, status,
                                      applied_by=None):
        row = self.prices.get((source_year, source_month))
        if row is None:
            return None
        row["status"] = status
        row["applied_by"] = applied_by
        return dict(row)

    # --- monthly_billing ---
    def get_monthly(self, year, month):
        row = self.months.get((year, month))
        return dict(row) if row else None

    def upsert_monthly(self, year, month, production_kwh, excess_sale_kwh,
                       excess_sale_invoice_try, osb_deduction_try,
                       rate_snapshot_try=None, rate_id=None):
        row = self.months.setdefault((year, month), {
            "year": year, "month": month, "status": STATUS_PENDING_RATE,
            "excess_sale_rate_try": None, "excess_sale_rate_id": None,
            "osb_unit_price_try": None, "locked_at": None,
        })
        if row["excess_sale_rate_try"] is None and rate_snapshot_try is not None:
            row["excess_sale_rate_try"] = rate_snapshot_try
            row["excess_sale_rate_id"] = rate_id
        row["production_kwh_snapshot"] = production_kwh
        row["excess_sale_kwh_snapshot"] = excess_sale_kwh
        row["excess_sale_invoice_try"] = excess_sale_invoice_try
        row["osb_deduction_try"] = osb_deduction_try
        row["status"] = STATUS_LOCKED if row["osb_unit_price_try"] is not None else STATUS_PENDING_RATE
        return dict(row)

    def set_osb_price(self, year, month, unit_price_try, entered_by, osb_deduction_try):
        row = self.months[(year, month)]
        self.set_osb_calls.append((year, month, unit_price_try, entered_by))
        row["osb_unit_price_try"] = unit_price_try
        row["osb_deduction_try"] = osb_deduction_try
        row["status"] = STATUS_LOCKED
        return dict(row)

    def get_effective_rate(self, rate_type, as_of):
        return None


def svc_with(**kw):
    s = BillingService()
    s.repo = FakeRepo(**kw)
    return s


def hazir_ay(year, month, osb=None):
    return {
        "year": year, "month": month,
        "status": STATUS_LOCKED if osb else STATUS_PENDING_RATE,
        "excess_sale_rate_try": Decimal("2.909687"), "excess_sale_rate_id": 5,
        "osb_unit_price_try": osb,
        "production_kwh_snapshot": Decimal("7248211.700"),
        "excess_sale_kwh_snapshot": Decimal("3693878.600"),
        "excess_sale_invoice_try": Decimal("10748030.54"),
        "osb_deduction_try": None, "locked_at": None,
    }


# ------------------------------------------------------- dönem eşlemesi (ADR-0004)
# Neden: next_month() ARTIK katsayı hedeflemesinde kullanılmıyor; yalnızca
# "kesinti hangi ay faturasından düşülecek" ETİKETİ için duruyor. Aritmetiğin
# kendisi hâlâ tek yerde ve Aralık->Ocak dönümü testli.
@pytest.mark.parametrize("kaynak,hedef", [
    ((2026, 6), (2026, 7)),
    ((2026, 1), (2026, 2)),
    ((2026, 12), (2027, 1)),   # yıl dönümü
    ((2026, 11), (2026, 12)),
])
def test_tahsilat_ayi_hesabi(kaynak, hedef):
    assert BillingService.next_month(*kaynak) == hedef


@pytest.mark.parametrize("donem", [(2026, 12), (2026, 6), (2026, 1)])
def test_hedef_kaynagin_kendisidir(donem):
    """
    ADR-0004: kaydırma YOK. Bir ayın katsayısı, O AYIN kendi üretimini değerleyen
    fiyattır. Regresyon: eskiden hedef next_month(source) idi ve iki gerçek GAOSB
    faturası bunun yanlış olduğunu gösterdi.
    """
    s = svc_with()
    out = s.set_electricity_price(donem[0], donem[1], "1.50", created_by="murat")

    assert (out["target_year"], out["target_month"]) == donem


# ---------------------------------------------------------------- bekletme
def test_hedef_ay_yoksa_bekletilir():
    s = svc_with()
    out = s.set_electricity_price(2026, 6, "1.380000", created_by="murat")

    assert out["status"] == PRICE_STATUS_PENDING
    assert s.repo.set_osb_calls == [], "hedef yokken katsayı yazılmamalı"


def test_compute_kancasi_bekleyeni_uygular():
    """2026-08-03 dersi: kanca job'da değil compute()'ta — izole script yolu da kapsanır."""
    s = svc_with()
    s.set_electricity_price(2026, 6, "1.380000", created_by="murat")
    assert s.repo.set_osb_calls == []

    # Haziran'ın mahsuplaşması şimdi hesaplanıyor (katsayı KENDİ ayına uygulanır)
    s.compute(year=2026, month=6,
              production_kwh=Decimal("7248211.700"),
              excess_sale_kwh=Decimal("3693878.600"))

    assert len(s.repo.set_osb_calls) == 1
    yil, ay, fiyat, giren = s.repo.set_osb_calls[0]
    assert (yil, ay) == (2026, 6)
    assert fiyat == Decimal("1.380000")
    assert "2026-06 faturası" in giren, "katsayının kaynağı izlenebilir olmalı"
    assert s.repo.prices[(2026, 6)]["status"] == PRICE_STATUS_APPLIED


def test_kanca_idempotan():
    """compute() yeniden çağrılırsa ikinci kez uygulanmamalı."""
    s = svc_with()
    s.set_electricity_price(2026, 6, "1.380000", created_by="murat")
    for _ in range(3):
        s.compute(year=2026, month=6, production_kwh=Decimal("100"),
                  excess_sale_kwh=Decimal("40"))

    assert len(s.repo.set_osb_calls) == 1


def test_hedef_hazir_ve_kilitsizse_hemen_uygulanir():
    s = svc_with(months={(2026, 6): hazir_ay(2026, 6)})
    out = s.set_electricity_price(2026, 6, "1.380000", created_by="murat")

    assert out["status"] == PRICE_STATUS_APPLIED
    assert len(s.repo.set_osb_calls) == 1


# ---------------------------------------------------------------- kilitli hedef
def test_kilitli_hedefte_otomatik_zincirleme_YAPILMAZ():
    """
    KRİTİK: Otomatik zincirleme, override'ın üç korumasını (şifre, 15 karakter gerekçe,
    denetim kaydı) aynı gün baypas ederdi.
    """
    aylar = {(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381"))}
    s = svc_with(months=aylar)

    out = s.set_electricity_price(2026, 6, "1.380000", created_by="murat")

    assert out["status"] == PRICE_STATUS_CORRECTION_PENDING
    assert s.repo.set_osb_calls == [], "kilitli aya dokunulmamalı"
    assert aylar[(2026, 6)]["osb_unit_price_try"] == Decimal("1.452381"), "değer değişmemeli"


def test_kilitli_hedefte_ayni_deger_duzeltme_istemez():
    """Aynı değer yeniden girildiyse ortada düzeltilecek bir şey yok; boş uyarı üretme."""
    aylar = {(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381"))}
    s = svc_with(months=aylar)

    out = s.set_electricity_price(2026, 6, "1.452381", created_by="murat")

    assert out["status"] == PRICE_STATUS_APPLIED


def test_override_onaylaninca_kaynak_uygulandiya_doner():
    """Zincirin kapanışı: kullanıcı override ile onaylayınca kaynak da güncellenir."""
    aylar = {(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381"))}
    s = svc_with(months=aylar)
    s.set_electricity_price(2026, 6, "1.380000", created_by="murat")
    assert s.repo.prices[(2026, 6)]["status"] == PRICE_STATUS_CORRECTION_PENDING

    # Kullanıcı override akışıyla onaylıyor
    s.repo.override_locked_month = lambda **kw: _fake_override(aylar, **kw)
    s.override_locked_month(2026, 6, reason="Haziran faturasi duzeltildi, fiyat dustu",
                            changed_by="murat", osb_unit_price_try="1.380000")

    assert s.repo.prices[(2026, 6)]["status"] == PRICE_STATUS_APPLIED


def test_override_farkli_deger_yazarsa_kaynak_beklemede_kalir():
    """Kullanıcı kaynaktan farklı bir sayı yazdıysa tutarsızlık ekranda görünmeye devam etmeli."""
    aylar = {(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381"))}
    s = svc_with(months=aylar)
    s.set_electricity_price(2026, 6, "1.380000", created_by="murat")

    s.repo.override_locked_month = lambda **kw: _fake_override(aylar, **kw)
    s.override_locked_month(2026, 6, reason="Elle farkli bir deger giriliyor test",
                            changed_by="murat", osb_unit_price_try="1.900000")

    assert s.repo.prices[(2026, 6)]["status"] == PRICE_STATUS_CORRECTION_PENDING


def _fake_override(aylar, year, month, osb_unit_price_try=None, excess_sale_rate_try=None):
    row = aylar[(year, month)]
    prev = {
        "_previous_osb_unit_price_try": row.get("osb_unit_price_try"),
        "_previous_excess_sale_rate_try": row.get("excess_sale_rate_try"),
        "_previous_excess_sale_rate_id": row.get("excess_sale_rate_id"),
        "_previous_excess_sale_invoice_try": row.get("excess_sale_invoice_try"),
        "_previous_osb_deduction_try": row.get("osb_deduction_try"),
    }
    if osb_unit_price_try is not None:
        row["osb_unit_price_try"] = osb_unit_price_try
    out = dict(row)
    out.update(prev)
    return out


# ---------------------------------------------------------------- doğrulama / dayanıklılık
@pytest.mark.parametrize("fiyat", ["0", "-1"])
def test_pozitif_olmayan_fiyat_reddedilir(fiyat):
    s = svc_with()
    with pytest.raises(BillingValidationError):
        s.set_electricity_price(2026, 6, fiyat, created_by="murat")


def test_created_by_zorunlu():
    s = svc_with()
    with pytest.raises(BillingValidationError):
        s.set_electricity_price(2026, 6, "1.38", created_by="  ")


def test_kanca_patlarsa_mahsuplasma_yazimi_etkilenmez():
    """
    Best-effort garantisi: kaynak kütüğündeki bir hata compute()'un yazımını
    düşürmemeli (ADR-0003 Faz 1'deki _reconcile_best_effort ile aynı gerekçe).
    """
    s = svc_with()

    def patla(*_a, **_kw):
        raise RuntimeError("kaynak kütüğü okunamadı")

    s.repo.get_electricity_price_for_target = patla

    sonuc = s.compute(year=2026, month=7,
                      production_kwh=Decimal("7612731.200"),
                      excess_sale_kwh=Decimal("3955487.000"))

    assert sonuc.year == 2026 and sonuc.month == 7
    assert (2026, 7) in s.repo.months, "mahsuplaşma satırı yazılmış olmalı"


# ------------------------------------------------- ayın KENDİ fiyatı / önizleme
# Neden: ADR-0004 sonrası "ayın kendi fiyatı" ile "ayın katsayısı" AYNI şeydir —
# kaydırma kaldırıldı. Bu testler eskiden bir ay ileri bakıyordu; artık kaymanın
# GERİ GELMEDİĞİNİ sabitliyorlar.
def test_ayin_kendi_fiyati_ayin_kendi_katsayisidir():
    s = svc_with(months={
        (2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381")),
        (2026, 7): hazir_ay(2026, 7, osb=Decimal("1.680000")),
    })
    assert s.get_own_electricity_price(2026, 6) == Decimal("1.452381")
    # Regresyon: eskiden burada Temmuz'un katsayısı dönüyordu (bir ay ileri bakılıyordu)
    assert s.get_own_electricity_price(2026, 6) != Decimal("1.680000")


def test_ayin_kendi_fiyati_ay_kilitli_degilse_kutukten_okunur():
    """
    Neden: Fatura, ayın mahsuplaşması hesaplanmadan önce girilebilir. O durumda
    değer kütükte bekliyordur ve önizleme yine üretilmeli.
    """
    s = svc_with()
    s.set_electricity_price(2026, 6, "1.452381", created_by="murat")
    assert s.get_own_electricity_price(2026, 6) == Decimal("1.452381")


def test_ayin_kendi_fiyati_override_edilmisse_uygulanani_verir():
    """
    Neden: Kilitli ay override ile düzeltilmişse GERÇEKTE uygulanan değer
    monthly_billing'dedir; kaynak kütüğü düzeltmeyi taşımayabilir
    (DUZELTME_BEKLIYOR). monthly_billing önce okunmalı.
    """
    s = svc_with(months={(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.600000"))})
    s.repo.prices[(2026, 6)] = {
        "source_year": 2026, "source_month": 6, "unit_price_try": Decimal("1.452381"),
        "target_year": 2026, "target_month": 6, "status": PRICE_STATUS_CORRECTION_PENDING,
        "applied_at": None, "applied_by": None, "created_by": "murat",
        "created_at": None, "note": None,
    }
    assert s.get_own_electricity_price(2026, 6) == Decimal("1.600000")


def test_ayin_kendi_fiyati_hic_yoksa_none():
    s = svc_with(months={(2026, 6): hazir_ay(2026, 6)})
    assert s.get_own_electricity_price(2026, 6) is None


def test_onizleme_ayin_kendi_fiyatiyla_hesaplanir():
    s = svc_with(months={(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381"))})
    kalan = Decimal("7248211.700") - Decimal("3693878.600")   # 3.554.333,100 kWh
    assert s.get_preview_deduction(2026, 6) == (kalan * Decimal("1.452381")).quantize(Decimal("0.01"))


def test_onizleme_resmi_kesintiyi_degistirmez():
    """
    Neden: Önizleme SALT GÖSTERİM. Çağrılması monthly_billing'e dokunmamalı.
    """
    s = svc_with(months={(2026, 6): hazir_ay(2026, 6, osb=Decimal("1.452381"))})
    s.repo.months[(2026, 6)]["osb_deduction_try"] = Decimal("5162245.86")
    once = dict(s.repo.months[(2026, 6)])

    s.get_preview_deduction(2026, 6)

    assert s.repo.months[(2026, 6)] == once, "önizleme kaydı değiştirmiş"
    assert not s.repo.set_osb_calls, "önizleme fiyat yazmış"


def test_onizleme_fiyat_yoksa_none():
    # Neden: Uydurulmuş sayı ile "önizleme yok" karışmamalı; çağıran "Bekleniyor" yazar.
    s = svc_with(months={(2026, 6): hazir_ay(2026, 6)})
    assert s.get_preview_deduction(2026, 6) is None


def test_onizleme_kwh_snapshot_yoksa_none():
    ay = hazir_ay(2026, 6, osb=Decimal("1.452381"))
    ay["production_kwh_snapshot"] = None
    s = svc_with(months={(2026, 6): ay})
    assert s.get_preview_deduction(2026, 6) is None


def test_onizleme_kaydi_olmayan_ay_icin_none():
    assert svc_with().get_preview_deduction(2026, 7) is None


def test_aralik_katsayisi_ocaga_kaymaz():
    """Regresyon: Aralık'ın katsayısı Aralık'ındır; yıl dönümünde kaymamalı."""
    s = svc_with()
    out = s.set_electricity_price(2026, 12, "1.900000", created_by="murat")
    assert (out["target_year"], out["target_month"]) == (2026, 12)
    assert s.get_own_electricity_price(2026, 12) == Decimal("1.900000")
    assert s.get_own_electricity_price(2027, 1) is None
