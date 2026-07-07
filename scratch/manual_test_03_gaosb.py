"""
Manuel Test 03 — GAOSB scraper: dün (2026-07-06) için veri çekme.

date_to = +1 gün gönderilir (portal Date2'yi hariç tutar).

Başarı kriterleri:
  - xlsx indirilmeli
  - Endeks kodu P.01.1.9 olmalı
  - 24 satır (saatlik)
  - Değerler 5.000-16.000 kWh aralığında
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env():
    """dotenv varsa onu, yoksa manuel .env yükleyiciyi kullan."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        return
    except Exception:
        pass
    import os
    env_path = ROOT / ".env"
    if not env_path.exists():
        print(f"[uyarı] .env bulunamadı: {env_path}")
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_env()

from app.sources.gaosb.extractor import GaosbExtractor  # noqa: E402

DATE_FROM = "2026-07-06"  # dün
DATE_TO = "2026-07-07"    # +1 gün (portal Date2'yi hariç tutar)
output_dir = ROOT / "outputs" / "manual_tests" / "03_gaosb"
output_dir.mkdir(parents=True, exist_ok=True)

print("TEST 3: GAOSB Sayaç Sorgu Raporu")
print("=" * 50)

try:
    extractor = GaosbExtractor()
    print(f"1. GAOSB raporu indiriliyor ({DATE_FROM} -> {DATE_TO})...")
    dest = Path(extractor.download_report(
        output_dir=output_dir,
        date_from=DATE_FROM,
        date_to=DATE_TO,
    ))
    print(f"   [OK] Dosya indirildi: {dest.name}")
    print(f"   Boyut: {dest.stat().st_size} bytes")
except Exception as e:
    print(f"\nSONUÇ: TEST 3 KALDI [FAIL] — {type(e).__name__}: {e}")
    sys.exit(1)

# ---- Dosya içerik analizi ----
print("\n2. Dosya içeriği analiz ediliyor...")
import pandas as pd

try:
    try:
        raw = pd.read_excel(dest, engine="xlrd", header=0)
    except Exception:
        raw = pd.read_excel(dest, engine="openpyxl", header=0)
except Exception as e:
    print(f"Dosya okunamadı: {type(e).__name__}: {e}")
    print("\nSONUÇ: TEST 3 KALDI [FAIL]")
    sys.exit(1)

# Kolonlar: 0=Tarih, 1=Endeks Kodu, 2=Açıklama, 3=Okunan Değer, 4=Çarpan, 5=Endeks değeri
n_rows = len(raw)
endeks_kodlari = sorted(set(raw.iloc[:, 1].dropna().astype(str))) if n_rows else []
degerler = pd.to_numeric(raw.iloc[:, 5], errors="coerce").dropna() if n_rows else pd.Series(dtype=float)
tarihler = sorted(set(str(v)[:10] for v in raw.iloc[:, 0].dropna())) if n_rows else []

print(f"   Satır sayısı: {n_rows}")
print(f"   Endeks kod(lar)ı: {endeks_kodlari}")
print(f"   Tarih(ler): {tarihler}")
print("   İlk 3 satır (tarih, endeks, değer):")
for i in range(min(3, n_rows)):
    print(f"     {raw.iloc[i, 0]} | {raw.iloc[i, 1]} | {raw.iloc[i, 5]}")
if len(degerler):
    print(f"   Değer aralığı: {degerler.min():.1f} - {degerler.max():.1f} kWh")

# Neden: +1 gün aralığı ham dosyaya ertesi günün 00:00 satırını da getirir;
# üretim hattında bu satırı SettlementEngine.load_gaosb() filtreler.
# 24 satır kriteri bu yüzden engine çıktısı üzerinden değerlendirilir.
print("\n3. SettlementEngine.load_gaosb() ile filtrelenmiş çıktı...")
from app.settlement.engine import SettlementEngine  # noqa: E402

df = SettlementEngine().load_gaosb(dest)
print(f"   Filtrelenmiş satır sayısı: {len(df)}")
if len(df):
    print(f"   İlk timestamp: {df['timestamp'].iloc[0]}")
    print(f"   Son timestamp: {df['timestamp'].iloc[-1]}")

k1 = dest.exists() and dest.stat().st_size > 0
k2 = endeks_kodlari == ["P.01.1.9"]
k3 = len(df) == 24 and df['timestamp'].str.startswith(DATE_FROM).all()
k4 = len(degerler) > 0 and degerler.between(5000, 16000).all()

print("\nBAŞARI KRİTERLERİ:")
print("  xlsx indirildi:                    " + ("GECTI [OK]" if k1 else "KALDI [FAIL]"))
print("  Endeks kodu P.01.1.9:              " + ("GECTI [OK]" if k2 else "KALDI [FAIL]"))
print(f"  24 saatlik satır (engine, {len(df)}):     " + ("GECTI [OK]" if k3 else "KALDI [FAIL]"))
print("  Değerler 5.000-16.000 kWh:         " + ("GECTI [OK]" if k4 else "KALDI [FAIL]"))
print("\nSONUÇ: TEST 3 " + ("GEÇTİ [OK]" if (k1 and k2 and k3 and k4) else "KALDI [FAIL]"))
