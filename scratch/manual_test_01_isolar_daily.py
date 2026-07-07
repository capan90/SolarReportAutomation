"""
Manuel Test 01 — iSolar Günlük Özet Raporu (login -> rapor sayfası -> indirme).
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

output_dir = ROOT / "outputs" / "manual_tests" / "01_isolar_daily"
output_dir.mkdir(parents=True, exist_ok=True)

print("TEST 1: iSolar Günlük Özet Raporu")
print("=" * 50)

try:
    with PlaywrightClient(headless=False) as client:
        page = client.create_page()
        extractor = IsolarExtractor(page, run_id="manual-test-01")

        print("1. Login...")
        extractor.login_and_verify()
        print("   [OK] Login başarılı")

        print("2. Rapor sayfasına git...")
        extractor.navigate_to_daily_report()
        print("   [OK] Rapor sayfası açıldı")

        print("3. Günlük rapor indiriliyor...")
        temp_path = extractor.download_daily_report()
        dest = output_dir / temp_path.name
        shutil.move(str(temp_path), str(dest))
        print(f"   [OK] Dosya indirildi: {dest.name}")
        print(f"   Boyut: {dest.stat().st_size} bytes")

    print()
    print("SONUÇ: TEST 1 GEÇTİ [OK]")
except Exception as e:
    print(f"SONUÇ: TEST 1 KALDI [FAIL] — {type(e).__name__}: {e}")
