"""
Neden: Sabit (Enerjisa) katsayısını append-only olarak ekler. Normal yol dashboard'dır;
bu script geriye dönük düzeltmelerde (dashboard'a erişimin olmadığı ya da onaylı bir
dry-run istendiği durumlarda) kullanılır.

Ham INSERT YAPMAZ — BillingService.set_rate üzerinden gider. Böylece ADR-0002 §2
doğrulamaları (pozitif fiyat, valid_from ayın 1'i, created_by zorunlu) ve
UNIQUE(rate_type, valid_from) kısıtı aynen uygulanır; script ikinci bir kural kümesi
oluşturmaz.

Vaka (2026-08-03): Mayıs 2026'nın Enerjisa katsayısı eksikti. Mayıs'ı kapsayan tek kayıt
id=4'tü ve o aslında bir OSB katsayısıydı (0.810049, yanlış tabloda). id=4 silindikten
sonra doğru değer (2.909687, Haziran ile aynı) valid_from=2026-05-01 ile eklenir.

Kullanım:
    python scripts/add_billing_rate.py --price 2.909687 --valid-from 2026-05-01   # dry-run
    python scripts/add_billing_rate.py --price 2.909687 --valid-from 2026-05-01 --apply
"""
import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

AUDIT_ACTION = "billing_rate_change"


def main():
    parser = argparse.ArgumentParser(description="Sabit faturalama katsayısı ekle (append-only)")
    parser.add_argument("--price", required=True, help="Birim fiyat (TL/kWh, KDV hariç)")
    parser.add_argument("--valid-from", required=True, help="Geçerlilik başlangıcı (YYYY-MM-01)")
    parser.add_argument("--note", default=None, help="Kayıt notu")
    parser.add_argument("--by", default="manual-correction", help="created_by / audit kullanıcısı")
    parser.add_argument("--apply", action="store_true", help="Gerçekten ekle (yoksa dry-run)")
    parser.add_argument("--database-url", default=None, help="Hedef DB (varsayılan: .env)")
    args = parser.parse_args()

    # Neden: db_session DATABASE_URL'i import anında okur; override IMPORT'TAN ÖNCE konmalı.
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from sqlalchemy import text  # noqa: E402
    from app.billing.service import BillingService  # noqa: E402
    from app.database.db_session import SessionLocal  # noqa: E402

    valid_from = date.fromisoformat(args.valid_from)
    price = Decimal(str(args.price))
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Katsayı ekleme [{mode}] ===\n")

    service = BillingService()

    print("Eklenecek kayıt:")
    print(f"  unit_price_try = {price}")
    print(f"  valid_from     = {valid_from.isoformat()}")
    print(f"  created_by     = {args.by}")
    print(f"  note           = {args.note!r}")

    print("\nMevcut katsayılar:")
    for r in service.list_rate_history(limit=20):
        print(f"  id={r.id} fiyat={r.unit_price_try} valid_from={r.valid_from}")

    # Neden: Aynı (rate_type, valid_from) için ikinci kayıt UNIQUE kısıtına takılır;
    # bunu apply'da patlamak yerine dry-run'da söylemek gerekir.
    clash = [r for r in service.list_rate_history(limit=50) if r.valid_from == valid_from]
    if clash:
        print(f"\nDURDURULDU: {valid_from.isoformat()} için zaten kayıt var "
              f"(id={clash[0].id}, fiyat={clash[0].unit_price_try}). "
              f"UNIQUE(rate_type, valid_from) kısıtı ikinci kayda izin vermez.")
        return 2

    before = service.get_current_rate(as_of=valid_from)
    print(f"\n{valid_from.isoformat()} için ŞU ANDA etkin katsayı: "
          f"{before.unit_price_try if before else 'YOK'}")
    print(f"Ekleme sonrası etkin olacak: {price}")

    if not args.apply:
        print("\n[DRY-RUN] Hiçbir değişiklik yapılmadı.")
        print("Gerçekten eklemek için: --apply")
        return 0

    created = service.set_rate(
        unit_price_try=price,
        valid_from=valid_from,
        created_by=args.by,
        note=args.note,
    )
    print(f"\n[APPLY] Kayıt eklendi: id={created.id} fiyat={created.unit_price_try} "
          f"valid_from={created.valid_from}")

    # Neden: Dashboard üzerinden yapılan katsayı değişikliği audit_log'a
    # "billing_rate_change" olarak düşüyor; script yolu da aynı izi bırakmalı,
    # yoksa denetimde iki farklı kanal oluşur.
    session = SessionLocal()
    try:
        session.execute(text(
            "INSERT INTO audit_log (timestamp, username, ip_address, action, details, success) "
            "VALUES (:ts, :user, :ip, :action, :details, :success)"
        ), {
            "ts": datetime.now(), "user": args.by, "ip": None, "action": AUDIT_ACTION,
            "details": json.dumps({
                "created_rate": {
                    "id": created.id,
                    "unit_price_try": str(created.unit_price_try),
                    "valid_from": created.valid_from.isoformat(),
                    "created_by": created.created_by,
                    "note": created.note,
                },
                "previous_effective": str(before.unit_price_try) if before else None,
                "source": "scripts/add_billing_rate.py",
            }, ensure_ascii=False),
            "success": True,
        })
        session.commit()
        print(f"[APPLY] audit_log kaydı yazıldı (action={AUDIT_ACTION}, by={args.by})")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
