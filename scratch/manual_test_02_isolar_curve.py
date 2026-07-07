"""
Manuel Test 02 — iSolar Saatlik Curve Raporu (login -> Curve sayfası -> dün için indir).

Başarı kriterleri:
  - xlsx dosyası indirilmeli
  - 24 satır saatlik veri
  - GES sütunları görünmeli
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

import shutil  # noqa: E402

from app.infrastructure.browser.playwright_client import PlaywrightClient  # noqa: E402
from app.extractors.isolar.extractor import IsolarExtractor  # noqa: E402

TARGET_DATE = "2026-07-06"  # dün
output_dir = ROOT / "outputs" / "manual_tests" / "02_isolar_curve"
output_dir.mkdir(parents=True, exist_ok=True)

print("TEST 2: iSolar Saatlik Curve Raporu")
print("=" * 50)

dest = None
try:
    with PlaywrightClient(headless=False) as client:
        page = client.create_page()
        extractor = IsolarExtractor(page, run_id="manual-test-02")

        print("1. Login...")
        extractor.login_and_verify()
        print("   [OK] Login başarılı")

        print("2. Curve sayfasına git...")
        extractor.navigate_to_curve_page()
        print("   [OK] Curve sayfası açıldı")

        print(f"3. Saatlik rapor indiriliyor (tarih: {TARGET_DATE})...")
        temp_path = extractor.download_hourly_curve_report(date_str=TARGET_DATE)
        dest = output_dir / temp_path.name
        shutil.move(str(temp_path), str(dest))
        print(f"   [OK] Dosya indirildi: {dest.name}")
        print(f"   Boyut: {dest.stat().st_size} bytes")
except Exception as e:
    print(f"\nSONUÇ: TEST 2 KALDI [FAIL] — {type(e).__name__}: {e}")
    sys.exit(1)

# ---- Dosya içerik analizi ----
print("\n4. Dosya içeriği analiz ediliyor...")
import pandas as pd

try:
    try:
        raw = pd.read_excel(dest, engine="openpyxl", header=None)
    except Exception:
        raw = pd.read_excel(dest, engine="xlrd", header=None)
except Exception as e:
    print(f"Dosya okunamadı: {type(e).__name__}: {e}")
    print("\nSONUÇ: TEST 2 KALDI [FAIL]")
    sys.exit(1)

print(f"   Ham boyut (satır x sütun): {raw.shape[0]} x {raw.shape[1]}")
print("   İlk 5 satır:")
print(raw.head(5).to_string())

# Başlık satırını bul: ilk hücresi 'Time' olan satır (satır 0 dosya adı başlığıdır)
header_idx = None
for i in range(min(10, len(raw))):
    if str(raw.iloc[i, 0]).strip().lower() == "time":
        header_idx = i
        break

if header_idx is not None:
    header = [str(c) for c in raw.iloc[header_idx].tolist()]
    data = raw.iloc[header_idx + 1:].dropna(how="all")
    print(f"\n   Başlık satırı (satır {header_idx}): {header[:3]} ... (+{len(header)-3} sütun)")
else:
    header = []
    data = raw.dropna(how="all")
    print("\n   [uyarı] 'Time' başlık satırı bulunamadı, tüm satırlar veri sayıldı.")

data_rows = len(data)
ges_cols = [h for h in header if "GES" in h.upper()]

# Veri satırlarındaki tarihler istenen güne mi ait?
dates_in_file = set()
for v in data.iloc[:, 0]:
    s = str(v)
    if len(s) >= 10:
        dates_in_file.add(s[:10])

print(f"   Veri satırı sayısı: {data_rows}")
print(f"   GES içeren sütun sayısı: {len(ges_cols)}")
print(f"   Dosyadaki tarih(ler): {sorted(dates_in_file)}")

k1 = dest.exists() and dest.stat().st_size > 0
k2 = data_rows == 24
k3 = bool(ges_cols)
k4 = dates_in_file == {TARGET_DATE}

print("\nBAŞARI KRİTERLERİ:")
print("  xlsx indirildi:            " + ("GECTI [OK]" if k1 else "KALDI [FAIL]"))
print(f"  24 saatlik satır ({data_rows}):     " + ("GECTI [OK]" if k2 else "KALDI [FAIL]"))
print(f"  GES sütunları ({len(ges_cols)} adet):     " + ("GECTI [OK]" if k3 else "KALDI [FAIL]"))
print(f"  Tarih = {TARGET_DATE}:       " + ("GECTI [OK]" if k4 else f"KALDI [FAIL] — dosyada {sorted(dates_in_file)}"))
print("\nSONUÇ: TEST 2 " + ("GEÇTİ [OK]" if (k1 and k2 and k3 and k4) else "KALDI [FAIL]"))
