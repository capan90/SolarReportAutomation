"""
Neden: SettlementEngine'in delta/mahsup hesap davranışını sabitlemek (smoke).
Tüm girdiler tmp_path altında pandas ile üretilen sentetik Excel dosyalarıdır —
gerçek portal, DB veya .env bağımlılığı yoktur.

Not: GAOSB çarpanı (26.400) kod tabanında uygulanmaz; portal çıktısında hazır
gelir. Bu yüzden burada çarpan testi yoktur — endeks sütununun "doğrudan
tüketim" alınması test edilir.

iSolar curve dosya formatı: 1. satır etiket (boş bırakılır), 2. satır başlık
(engine header=1 ile okur). GAOSB formatı: 0. sütun tarih, 5. sütun endeks.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.settlement.engine import SettlementEngine
from app.settlement.models import HourlySettlement

GES2 = "ERDEMSOFT-GES_2(88133)/Plant daily yield(kWh)"
GES3 = "ERDEMSOFT-GES_3(88134)/Plant daily yield(kWh)"
GES10 = "ERDEMSOFT-GES_10(88140)/Plant daily yield(kWh)"


def yaz_isolar(path, times, kolonlar):
    """Sentetik iSolar curve dosyası: başlık 2. satırda (startrow=1)."""
    df = pd.DataFrame({"Time": times, **kolonlar})
    df.to_excel(path, index=False, startrow=1)


def yaz_gaosb(path, tarihler, endeks):
    """Sentetik GAOSB dosyası: 0. sütun tarih, 5. sütun endeks değeri."""
    df = pd.DataFrame({
        "Tarih": tarihler,
        "Sutun1": 0, "Sutun2": 0, "Sutun3": 0, "Sutun4": 0,
        "Endeks": endeks,
    })
    df.to_excel(path, index=False)


@pytest.fixture
def engine():
    return SettlementEngine()


def test_isolar_kumulatiften_delta(engine, tmp_path):
    path = tmp_path / "curve.xlsx"
    yaz_isolar(path, ["2026-07-20 00:00:00", "2026-07-20 01:00:00", "2026-07-20 02:00:00"],
               {GES2: [100.0, 150.0, 210.0]})
    result = engine.load_isolar_curve(path)
    assert list(result["production_kwh"]) == [0.0, 50.0, 60.0]
    assert list(result["timestamp"]) == [
        "2026-07-20 00:00:00", "2026-07-20 01:00:00", "2026-07-20 02:00:00",
    ]


def test_isolar_negatif_delta_sifirlanir(engine, tmp_path):
    # Gece sıfırlanması / sayaç reseti: 150 → 50 düşüşü 0 sayılmalı.
    path = tmp_path / "curve.xlsx"
    yaz_isolar(path, ["2026-07-20 00:00:00", "2026-07-20 01:00:00", "2026-07-20 02:00:00"],
               {GES2: [100.0, 150.0, 50.0]})
    result = engine.load_isolar_curve(path)
    assert list(result["production_kwh"]) == [0.0, 50.0, 0.0]


def test_isolar_referans_satiri(engine, tmp_path):
    # Önceki günün son saati referans: ilk delta hesabına girer, çıktıya girmez.
    path = tmp_path / "curve.xlsx"
    yaz_isolar(path, ["2026-07-19 23:00:00", "2026-07-20 00:00:00", "2026-07-20 01:00:00"],
               {GES2: [90.0, 100.0, 150.0]})
    result = engine.load_isolar_curve(path)
    assert list(result["timestamp"]) == ["2026-07-20 00:00:00", "2026-07-20 01:00:00"]
    # 00:00 üretimi referans sayesinde kaybolmaz: 100 - 90 = 10
    assert list(result["production_kwh"]) == [10.0, 50.0]


def test_isolar_ges_kolon_ayrismasi(engine, tmp_path):
    path = tmp_path / "curve.xlsx"
    yaz_isolar(path, ["2026-07-20 00:00:00", "2026-07-20 01:00:00"],
               {GES10: [5.0, 25.0], GES3: [10.0, 30.0]})
    result = engine.load_isolar_curve(path)
    # Kısa kolonlar üretilir ve GES numarasına göre sayısal sıralanır (3 < 10)
    assert list(result.columns) == ["timestamp", "production_kwh", "ges_3_kwh", "ges_10_kwh"]
    assert list(result["ges_3_kwh"]) == [0.0, 20.0]
    assert list(result["ges_10_kwh"]) == [0.0, 20.0]


def test_gaosb_endeks_dogrudan_tuketim(engine, tmp_path):
    # Endeks sütunu (index 5) delta hesabı YAPILMADAN tüketimdir.
    path = tmp_path / "gaosb.xlsx"
    yaz_gaosb(path, ["2026-07-20 00:00:00", "2026-07-20 01:00:00"], [120.5, 80.0])
    result = engine.load_gaosb(path)
    assert list(result["consumption_kwh"]) == [120.5, 80.0]
    assert list(result["timestamp"]) == ["2026-07-20 00:00:00", "2026-07-20 01:00:00"]


def test_gaosb_excel_seri_tarih(engine, tmp_path):
    # Sayısal Excel seri tarihi (1899-12-30 bazlı) doğru saate çevrilmeli.
    # Not: Saat 12:00 seçildi çünkü gün kesri (0.5) binary float'ta tam temsil
    # edilir; 13/24 gibi kesirler 12:59:59.999... çözülür ve saat kayar —
    # bu, motorun değil float aritmetiğinin doğasıdır (gerçek dosyalarda
    # tarih hücreleri datetime olarak gelir, seri sayı yolu nadir durumdur).
    hedef = datetime(2026, 7, 20, 12, 0, 0)
    seri = (hedef - datetime(1899, 12, 30)).total_seconds() / 86400
    path = tmp_path / "gaosb.xlsx"
    yaz_gaosb(path, [seri], [42.0])
    result = engine.load_gaosb(path)
    assert list(result["timestamp"]) == ["2026-07-20 12:00:00"]
    assert list(result["consumption_kwh"]) == [42.0]


def test_gaosb_ikinci_gun_filtresi(engine, tmp_path):
    # GAOSB'ye +1 gün sorgulandığından ertesi güne taşan satırlar atılmalı.
    path = tmp_path / "gaosb.xlsx"
    yaz_gaosb(
        path,
        ["2026-07-20 00:00:00", "2026-07-20 01:00:00", "2026-07-20 02:00:00",
         "2026-07-21 00:00:00", "2026-07-21 01:00:00"],
        [10.0, 20.0, 30.0, 40.0, 50.0],
    )
    result = engine.load_gaosb(path)
    assert len(result) == 3
    assert all(ts.startswith("2026-07-20") for ts in result["timestamp"])


def test_calculate_mahsup_matematigi(engine, tmp_path):
    isolar = tmp_path / "curve.xlsx"
    gaosb = tmp_path / "gaosb.xlsx"
    # Üretim deltaları: 00:00 → 0, 01:00 → 60, 02:00 → 80
    yaz_isolar(isolar, ["2026-07-20 00:00:00", "2026-07-20 01:00:00", "2026-07-20 02:00:00"],
               {GES2: [100.0, 160.0, 240.0]})
    # Tüketim: 50, 30, 100 + iSolar'da olmayan 03:00 (inner join dışında kalmalı)
    yaz_gaosb(gaosb,
              ["2026-07-20 00:00:00", "2026-07-20 01:00:00",
               "2026-07-20 02:00:00", "2026-07-20 03:00:00"],
              [50.0, 30.0, 100.0, 999.0])

    settlements = engine.calculate(isolar, gaosb)

    assert len(settlements) == 3  # inner join: yalnızca ortak saatler
    beklenen = [
        # (üretim, tüketim, mahsup=min, satış=max(0,ü-t), çekiş=max(0,t-ü))
        (0.0, 50.0, 0.0, 0.0, 50.0),
        (60.0, 30.0, 30.0, 30.0, 0.0),
        (80.0, 100.0, 80.0, 0.0, 20.0),
    ]
    for s, (prod, cons, settled, export_val, import_val) in zip(settlements, beklenen):
        assert s.production_kwh == prod
        assert s.consumption_kwh == cons
        assert s.settled_kwh == settled
        assert s.grid_export_kwh == export_val
        assert s.grid_import_kwh == import_val


def test_to_dataframe_kolonlari(engine):
    settlements = [HourlySettlement(
        timestamp="2026-07-20 01:00:00", production_kwh=60.0, consumption_kwh=30.0,
        settled_kwh=30.0, grid_export_kwh=30.0, grid_import_kwh=0.0,
    )]
    df = engine.to_dataframe(settlements)
    assert list(df.columns) == [
        "timestamp", "production_kwh", "consumption_kwh",
        "settled_kwh", "grid_export_kwh", "grid_import_kwh",
    ]
    assert len(df) == 1
    assert df.iloc[0]["settled_kwh"] == 30.0
