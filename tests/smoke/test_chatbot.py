"""
Neden: Chatbot niyet/tarih/metrik parser'larının genişletilmiş kapsamını sabitlemek (smoke).
Saf mantık — DB/portal gerekmez. DateParser sabit referans tarihiyle (2026-07-20 Pazartesi)
kurulur ki testler deterministik olsun.
"""
from datetime import date

import pytest

from app.chatbot.parser import DateParser, IntentParser, MetricParser
from app.chatbot.response_builder import ResponseBuilder

REF = date(2026, 7, 20)  # Pazartesi


@pytest.fixture
def dp():
    return DateParser(reference_date=REF)


@pytest.fixture
def mp():
    return MetricParser()


@pytest.fixture
def ip():
    return IntentParser()


# ---------------- Tarih: ek ve varyasyon kapsamı ----------------

@pytest.mark.parametrize(
    "soru,beklenen_tip,beklenen_label_parcasi",
    [
        ("dün üretim", "day", "19 Temmuz 2026"),
        ("bugünkü tüketim", "day", "20 Temmuz 2026"),
        ("önceki gün üretim", "day", "18 Temmuz 2026"),
        ("bu ay mahsup", "month", "Temmuz 2026"),
        ("bu ayki fazla satış", "month", "Temmuz 2026"),      # 'ayki' eki — eskiden kırıktı
        ("bu ayın üretimi", "month", "Temmuz 2026"),
        ("geçen ay tüketim", "month", "Haziran 2026"),
        ("geçen ayki üretim", "month", "Haziran 2026"),
        ("önceki ay mahsup", "month", "Haziran 2026"),
        ("bu hafta üretim", "week", "Bu Hafta"),
        ("geçen haftaki tüketim", "week", "Geçen Hafta"),
        ("mayıs 2025 üretim", "month", "Mayıs 2025"),
        ("ocakta ne ürettik", "month", "Ocak"),               # 'ocakta' — locative ek
        ("temmuzda tüketim", "month", "Temmuz"),
        ("son 7 gün üretim", "range", "Son 7 Gün"),
        ("son 2 hafta tüketim", "range", "Son 2 Hafta"),      # yeni: son X hafta
        ("son 3 ay mahsup", "range", "Son 3 Ay"),
        ("bu yıl üretim", "range", "Bu Yıl"),
        ("geçen sene üretim", "range", "Geçen Yıl"),
        ("15.06.2026 üretim", "day", "15 Haziran 2026"),
    ],
)
def test_tarih_kapsami(dp, soru, beklenen_tip, beklenen_label_parcasi):
    result = dp.parse(soru)
    assert result is not None, f"Tarih çözülemedi: {soru!r}"
    assert result["type"] == beklenen_tip
    assert beklenen_label_parcasi in result["label"]


def test_tarih_yok_none_doner(dp):
    # Tarih sinyali olmayan mesaj None döner (eskiden sessizce düne düşüyordu)
    assert dp.parse("merhaba") is None
    assert dp.parse("üretim ne kadar") is None


def test_gelecek_reddedilir(dp):
    with pytest.raises(ValueError):
        dp.parse("yarın üretim ne olacak")


# ---------------- Metrik: eş anlamlı kapsamı ----------------

@pytest.mark.parametrize(
    "soru,beklenen_metrik",
    [
        ("dün ne ürettik", "production"),
        ("güneş üretimi", "production"),
        ("ne kadar harcadık", "consumption"),
        ("ne kullandık", "consumption"),
        ("mahsuplaşma durumu", "settled"),
        ("şebekeden çektik", "grid_import"),
        ("şebekeye sattık", "grid_export"),
        ("fazla satış", "grid_export"),
    ],
)
def test_metrik_kapsami(mp, soru, beklenen_metrik):
    result = mp.parse(soru)
    assert beklenen_metrik in result["metrics"]
    assert result["explicit"] is True


def test_metrik_explicit_bayragi(mp):
    # Belirsiz sorguda tam özete düşer ama explicit=False
    result = mp.parse("bu ay nasıl gitti")  # 'nasıl gitti' özet sinyali → explicit True
    assert result["explicit"] is True
    result2 = mp.parse("bu ay")  # sadece tarih, metrik sinyali yok
    assert result2["explicit"] is False
    assert len(result2["metrics"]) == 5  # varsayılan tam özet


@pytest.mark.parametrize(
    "soru,comparison",
    [
        ("en çok üretim hangi gün", "best"),
        ("en yüksek üretim", "best"),
        ("rekor üretim günü", "best"),
        ("en az tüketim", "worst"),
        ("en düşük mahsup", "worst"),
    ],
)
def test_kiyaslama_yonu(mp, soru, comparison):
    assert mp.parse(soru)["comparison"] == comparison


# ---------------- Niyet sınıflandırması ----------------

@pytest.mark.parametrize(
    "soru,beklenen_kind",
    [
        ("merhaba", "greeting"),
        ("selam", "greeting"),
        ("günaydın", "greeting"),
        ("nasılsın", "greeting"),
        ("yardım", "help"),
        ("neler sorabilirim", "help"),
        ("ne yapabilirsin", "help"),
        ("üretim ile tüketim arasındaki fark", "comparison_diff"),
        ("bu ayı geçen ayla kıyasla", "comparison_diff"),
        ("dün üretim ne kadar", "data"),
        ("santral durumu", "data"),
        ("bu ay özet", "data"),
        ("en çok üretim hangi gün", "data"),
        ("asdfgh qwerty", "unknown"),
        ("bugün hava nasıl", "data"),  # 'bugün' tarih sinyali → data (dünkü/varsayılan akış)
    ],
)
def test_niyet_siniflandirma(ip, soru, beklenen_kind):
    assert ip.classify(soru)["kind"] == beklenen_kind


def test_selam_ile_baslayan_veri_sorusu_data(ip):
    # 'merhaba dün üretim' selamla başlasa da veri sinyali var → data
    assert ip.classify("merhaba dün üretim ne kadar")["kind"] == "data"


# ---------------- Yönlendirme metinleri ----------------

def test_yonlendirme_metinleri_ornek_icerir():
    rb = ResponseBuilder()
    assert "yardımcı" in rb.greeting().lower()
    assert "üretim" in rb.help_menu()
    assert "kıyasla" in rb.comparison_guidance().lower()
    assert "anlayamadım" in rb._unrecognized_response().lower()
