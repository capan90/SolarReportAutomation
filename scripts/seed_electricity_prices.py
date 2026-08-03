"""
Neden: `monthly_electricity_price` kütüğü yeni; geçmiş aylar kaynaksız kalırsa ekranda
"bu katsayı nereden geldi" sorusunun cevabı yalnızca yeni aylar için görünür olur.
Bu script, hâlihazırda uygulanmış olan kaynak fiyatları geriye dönük kütüğe yazar.

TOHUMLAMA MEVCUT AYLARA DOKUNMAZ:
- `BillingService.set_electricity_price` yolundan GEÇMEZ — o yol hedef ayı karşılaştırır,
  gerekirse DUZELTME_BEKLIYOR üretir veya kilitsiz aya uygular. Tohumlanan değerler zaten
  uygulanmış durumda; yeniden uygulanmamalı.
- `compute()` çağrılmaz, `monthly_billing`'e tek bir yazma yapılmaz.
- Doğrudan repository'nin kütük metodu kullanılır.

GÜVENLİK KONTROLÜ: Her satır için hedef ayın GERÇEK katsayısı tohum değeriyle
karşılaştırılır. Eşleşmezse o satır YAZILMAZ — aksi halde kütük gerçekle çelişir ve
sistem o ayı anında "düzeltme bekliyor" sanıp kullanıcıyı yanlış değere geri çağırırdı.

Kaynak: 2026-08-03 tarihli prod verisi + kullanıcı teyidi.
    Nisan 2026 faturası  0.810049 -> Mayıs'ı besledi
    Mayıs 2026 faturası  0.810049 -> Haziran'ı besledi
    Haziran 2026 faturası 1.452381 -> Temmuz'u besledi

Kullanım:
    python scripts/seed_electricity_prices.py                # dry-run
    python scripts/seed_electricity_prices.py --apply
"""
import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# (kaynak_yıl, kaynak_ay, birim_fiyat, hedef_yıl, hedef_ay)
SEEDS = [
    (2026, 4, "0.810049", 2026, 5),
    (2026, 5, "0.810049", 2026, 6),
    (2026, 6, "1.452381", 2026, 7),
]

AY = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
      "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def main():
    parser = argparse.ArgumentParser(description="Geçmiş fatura fiyatlarını kütüğe yaz")
    parser.add_argument("--apply", action="store_true", help="Gerçekten yaz (yoksa dry-run)")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--by", default="tohumlama", help="created_by / applied_by")
    args = parser.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from app.billing.models import PRICE_STATUS_APPLIED  # noqa: E402
    from app.database.billing_repository import BillingRepository  # noqa: E402

    repo = BillingRepository()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Fatura fiyatı kütüğü tohumlaması [{mode}] ===\n")

    # Önce mevcut durumu göster — uygulama sonrası karşılaştırma için referans.
    print("monthly_billing (tohumlama ÖNCESİ — dokunulmayacak):")
    for y, m in sorted({(s[3], s[4]) for s in SEEDS}):
        row = repo.get_monthly(y, m)
        if row is None:
            print(f"  {y}-{m:02d}: SATIR YOK")
        else:
            print(f"  {y}-{m:02d}: durum={row['status']} osb={row['osb_unit_price_try']} "
                  f"kesinti={row['osb_deduction_try']}")

    print("\nTohumlanacak kayıtlar:")
    plan = []
    for sy, sm, price_raw, ty, tm in SEEDS:
        price = Decimal(price_raw)
        target = repo.get_monthly(ty, tm)
        mevcut = target.get("osb_unit_price_try") if target else None

        if target is None:
            durum, yazilir = "hedef ay YOK", False
        elif mevcut is None:
            durum, yazilir = "hedef ayın katsayısı boş", False
        elif Decimal(str(mevcut)) != price:
            durum, yazilir = f"UYUŞMAZLIK — hedefteki değer {mevcut}", False
        else:
            durum, yazilir = "eşleşiyor", True

        var_mi = repo.get_electricity_price_for_target(ty, tm)
        if var_mi is not None:
            durum, yazilir = f"kütükte ZATEN VAR ({var_mi['unit_price_try']})", False

        plan.append((sy, sm, price, ty, tm, yazilir))
        isaret = "YAZILACAK" if yazilir else "ATLANACAK"
        print(f"  {AY[sm]} {sy} faturası {price} -> {AY[tm]} {ty}  [{isaret}] ({durum})")

    yazilacak = [p for p in plan if p[5]]
    print(f"\nÖzet: {len(yazilacak)} yazılacak, {len(plan) - len(yazilacak)} atlanacak.")

    if not args.apply:
        print("\n[DRY-RUN] Hiçbir değişiklik yapılmadı. Uygulamak için: --apply")
        return 0

    for sy, sm, price, ty, tm, yazilir in plan:
        if not yazilir:
            continue
        repo.upsert_electricity_price(
            source_year=sy, source_month=sm, unit_price_try=price,
            target_year=ty, target_month=tm, created_by=args.by,
            note=f"Geriye dönük tohumlama — {AY[tm]} {ty} katsayısı bu faturadan gelmişti.",
            status=PRICE_STATUS_APPLIED,
        )
        repo.mark_electricity_price_status(sy, sm, PRICE_STATUS_APPLIED, applied_by=args.by)
        print(f"[APPLY] {AY[sm]} {sy} -> {AY[tm]} {ty} yazıldı ({price}, UYGULANDI)")

    print("\nmonthly_billing (tohumlama SONRASI — değişmemiş olmalı):")
    for y, m in sorted({(s[3], s[4]) for s in SEEDS}):
        row = repo.get_monthly(y, m)
        print(f"  {y}-{m:02d}: durum={row['status']} osb={row['osb_unit_price_try']} "
              f"kesinti={row['osb_deduction_try']}")

    print("\nKütük:")
    for p in repo.list_electricity_prices():
        print(f"  {p['source_year']}-{p['source_month']:02d} {p['unit_price_try']} -> "
              f"{p['target_year']}-{p['target_month']:02d} [{p['status']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
