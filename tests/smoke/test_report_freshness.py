"""
Neden: "Geçmiş Rapor Sorgula" formu cache'i VARLIK kontrolüyle yapıyordu — dosya
diskte varsa "rapor hazır" deyip servis ediyor, dosyanın DB'den eski olup olmadığına
bakmıyordu. 2026-08-04'te Haziran raporu veritabanıyla 2.283.061,89 TL çelişiyordu
(OSB katsayısı 3 Ağustos'ta override ile düzeltilmişti ama Excel 28 Temmuz'dan kalma).

Düzeltme force:true DEĞİL: force tam işi koşturur, portala yeniden gider ve
settlement verisinin ÜZERİNE YAZAR (ADR-0003 teknik borcu). Bunun yerine bayat rapor
yalnızca DB'den yeniden yazılır.

Testler üç garantiyi sabitler:
1. Tazelik karşılaştırması saat dilimi tuzağına düşmez (updated_at naive UTC,
   mtime yerel).
2. Karar verilemeyen durumlarda cache korunur (kontrol indirmeyi engellemez).
3. Rapor yeniden üretimi settlement tablolarına DOKUNMAZ.
"""
import datetime
from pathlib import Path

import pytest

from app.dashboard.web_server import DashboardRequestHandler

STALE = DashboardRequestHandler._monthly_report_is_stale


@pytest.fixture
def rapor(tmp_path):
    p = tmp_path / "mahsup_202606_aylik.xlsx"
    p.write_bytes(b"x")
    return p


def _billing_donen(updated_at):
    """BillingService().repo.get_monthly(...) yerine geçen sahte."""
    class _Repo:
        def get_monthly(self, year, month):
            return None if updated_at is None else {"updated_at": updated_at}

    class _Svc:
        repo = _Repo()

    return _Svc


def _mtime_utc(p):
    return datetime.datetime.utcfromtimestamp(p.stat().st_mtime)


def test_db_daha_yeniyse_bayat_sayilir(rapor, monkeypatch):
    import app.billing as billing

    sonra = _mtime_utc(rapor) + datetime.timedelta(hours=1)
    monkeypatch.setattr(billing, "BillingService", _billing_donen(sonra))

    assert STALE("2026-06", str(rapor)) is True


def test_dosya_daha_yeniyse_taze_sayilir(rapor, monkeypatch):
    import app.billing as billing

    once = _mtime_utc(rapor) - datetime.timedelta(hours=1)
    monkeypatch.setattr(billing, "BillingService", _billing_donen(once))

    assert STALE("2026-06", str(rapor)) is False


def test_saat_dilimi_tuzagi_yanlis_taze_uretmez(rapor, monkeypatch):
    """
    KRİTİK: updated_at naive UTC, mtime yerel saat. UTC+3'te mtime yerel olarak
    okunsaydı, DB'den 2 saat SONRA güncellenmiş bir kayıt bile "dosya daha yeni"
    görünür ve bayat rapor taze sayılırdı. Bu test o 3 saatlik kör noktayı kapatır.
    """
    import app.billing as billing

    # Dosyadan 2 saat SONRA güncellenmis DB kaydi (yerel saatte okunsa "eski" gorunurdu)
    iki_saat_sonra = _mtime_utc(rapor) + datetime.timedelta(hours=2)
    monkeypatch.setattr(billing, "BillingService", _billing_donen(iki_saat_sonra))

    assert STALE("2026-06", str(rapor)) is True, (
        "mtime yerel saatte okunuyor olabilir — bayat rapor taze sayılıyor"
    )


@pytest.mark.parametrize("senaryo,updated_at", [
    ("faturalama kaydi yok", None),
    ("updated_at bos", "YOK"),
])
def test_karar_verilemezse_cache_korunur(rapor, monkeypatch, senaryo, updated_at):
    """Tazelik kontrolü bir kolaylık; şüphede indirmeyi engellememeli."""
    import app.billing as billing

    if updated_at == "YOK":
        class _Repo:
            def get_monthly(self, year, month):
                return {"updated_at": None}

        class _Svc:
            repo = _Repo()
        monkeypatch.setattr(billing, "BillingService", _Svc)
    else:
        monkeypatch.setattr(billing, "BillingService", _billing_donen(None))

    assert STALE("2026-06", str(rapor)) is False


def test_dosya_yoksa_bayat_denmez(tmp_path):
    assert STALE("2026-06", str(tmp_path / "olmayan.xlsx")) is False


def test_kontrol_patlarsa_cache_korunur(rapor, monkeypatch):
    """Kontrolün kendi hatası indirmeyi bloklamamalı (best-effort)."""
    import app.billing as billing

    class _Patlayan:
        def __init__(self):
            raise RuntimeError("DB yok")

    monkeypatch.setattr(billing, "BillingService", _Patlayan)
    assert STALE("2026-06", str(rapor)) is False


def test_rapor_yeniden_uretimi_settlement_tablolarina_yazmaz():
    """
    KRİTİK: rewrite_report_from_db yalnızca Excel'i yazmalı. run() ile aynı şeyi
    yapsaydı geçmiş bir ayı GÖRÜNTÜLEMEK o ayın mahsuplaşma verisini üzerine yazardı
    (ADR-0003) ve portala yeniden giderdi.
    """
    kaynak = Path("app/jobs/monthly_settlement_job.py").read_text(encoding="utf-8")
    govde = kaynak.split("def rewrite_report_from_db", 1)[1].split("\n    def run(", 1)[0]

    for yasak in ("upsert_hourly", "upsert_daily", "upsert_monthly", "compute(",
                  "PlaywrightClient", "IsolarExtractor", "GaosbExtractor"):
        assert yasak not in govde, f"rewrite_report_from_db {yasak} çağırmamalı"
    assert "_write_monthly_report" in govde, "raporu yine de yazmalı"
    assert "list_hourly_month" in govde, "veriyi DB'den okumalı"


def test_faturalama_butonunun_force_davranisi_korundu():
    """Regresyon: Faturalama sekmesindeki 'Raporu Yeniden Üret' hâlâ force:true göndermeli."""
    html = Path("app/dashboard/static/index.html").read_text(encoding="utf-8")
    blok = html.split("async function regenerateBillingMonth", 1)[1][:1600]
    assert "force: true" in blok
    assert '"cached"' in blok, "force ile 'cached' dönerse hâlâ hata sayılmalı"
