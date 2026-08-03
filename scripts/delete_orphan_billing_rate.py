"""
Neden: billing_rate id=1 (2.909687, valid_from=2028-01-01) orijinal girişte tarihi
yanlışlıkla 2028 yazılmış bir kayıt. Aynı katsayı 2026-06-01 geçerlilikle id=5 olarak
yeniden girildi (manual-correction) ve tüm faturalama o kaydı kullanıyor.

id=1 hiçbir monthly_billing satırında kullanılmadı, ama zararsız değil: valid_from=2028
olduğu için 1 Ocak 2028'de kendiliğinden "en güncel geçerli katsayı" haline gelir ve o
tarihe kadar girilmiş her yeni katsayıyı sessizce ezer. Temizliğin gerçek gerekçesi budur.

ADR-0002 append-only ilkesi kapsamı: ilke, hesaplanmış bir ayın tutarını etkileyen
kayıtlar içindir (onlar asla silinmez, üzerine yeni kayıt eklenir). id=1 hiçbir hesapta
kullanılmadığı için bu kapsamın dışında. Yine de silme İZLENEBİLİR yapılır: kaydın tüm
alanları audit_log'a yazılır ve silme ile aynı transaction'da commit edilir.

Kullanım:
    python scripts/delete_orphan_billing_rate.py                 # dry-run (varsayılan)
    python scripts/delete_orphan_billing_rate.py --apply         # gerçekten sil
    python scripts/delete_orphan_billing_rate.py --database-url ...   # hedef DB override
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

TARGET_RATE_ID = 1
AUDIT_ACTION = "billing_rate_deletion"
DELETION_REASON = (
    "Orijinal girişte valid_from 2028-01-01 olarak yanlış yazılmış kayıt; aynı katsayı "
    "id=5 olarak 2026-06-01 geçerlilikle yeniden girildi. Hiçbir monthly_billing satırı "
    "bu kaydı kullanmadı. Silinmeseydi 2028-01-01'de kendiliğinden geçerli katsayı olup "
    "araya girilecek yeni katsayıları ezecekti."
)


def resolve_url(override):
    if override:
        return override
    from app.core.config import settings
    return settings.database_url


def main():
    parser = argparse.ArgumentParser(description="billing_rate id=1 temizliği")
    parser.add_argument("--apply", action="store_true",
                        help="Gerçekten sil (verilmezse yalnızca dry-run)")
    parser.add_argument("--database-url", default=None, help="Hedef DB (varsayılan: .env)")
    parser.add_argument("--by", default="manual-cleanup", help="audit_log kullanıcı adı")
    args = parser.parse_args()

    url = resolve_url(args.database_url)
    engine = create_engine(url)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== billing_rate id={TARGET_RATE_ID} temizliği [{mode}] ===\n")

    with engine.begin() as con:
        row = con.execute(text(
            "SELECT id, rate_type, unit_price_try, valid_from, created_at, created_by, note "
            "FROM billing_rate WHERE id = :rid"
        ), {"rid": TARGET_RATE_ID}).fetchone()

        if row is None:
            print(f"Kayıt bulunamadı (id={TARGET_RATE_ID}). Yapılacak bir şey yok.")
            return 0

        record = {
            "id": row[0],
            "rate_type": row[1],
            "unit_price_try": str(row[2]),
            "valid_from": str(row[3]),
            "created_at": str(row[4]),
            "created_by": row[5],
            "note": row[6],
        }
        print("Silinecek kayıt:")
        for k, v in record.items():
            print(f"  {k:16} = {v}")

        # Neden: Ön koşul apply anında YENİDEN doğrulanır. Dry-run ile apply arasında
        # geçen sürede bir ay bu katsayıya bağlanmış olabilir; o durumda silmek
        # faturalama geçmişini bozar ve FK ihlali üretir.
        refs = con.execute(text(
            "SELECT id, year, month, status FROM monthly_billing "
            "WHERE excess_sale_rate_id = :rid ORDER BY year, month"
        ), {"rid": TARGET_RATE_ID}).fetchall()

        print(f"\nBu katsayıyı kullanan monthly_billing satırı: {len(refs)}")
        for r in refs:
            print(f"  id={r[0]} {r[1]}-{r[2]:02d} status={r[3]}")

        if refs:
            print("\nDURDURULDU: kayıt faturalama hesaplarında kullanılmış. "
                  "ADR-0002 append-only ilkesi gereği silinemez.")
            return 2

        if not args.apply:
            print("\n[DRY-RUN] Hiçbir değişiklik yapılmadı.")
            print("Gerçekten silmek için: --apply")
            return 0

        details = json.dumps({
            "deleted_record": record,
            "reason": DELETION_REASON,
            "monthly_billing_references": 0,
        }, ensure_ascii=False)

        # Neden: audit kaydı ile silme AYNI transaction'da; biri yazılıp diğeri
        # yazılmadan kalırsa iz kopar.
        con.execute(text(
            "INSERT INTO audit_log (timestamp, username, ip_address, action, details, success) "
            "VALUES (:ts, :user, :ip, :action, :details, :success)"
        ), {
            "ts": datetime.now(), "user": args.by, "ip": None,
            "action": AUDIT_ACTION, "details": details, "success": True,
        })
        deleted = con.execute(text("DELETE FROM billing_rate WHERE id = :rid"),
                              {"rid": TARGET_RATE_ID}).rowcount

        print(f"\n[APPLY] Silinen satır: {deleted}")
        print(f"[APPLY] audit_log kaydı yazıldı (action={AUDIT_ACTION}, by={args.by})")

    with engine.connect() as con:
        remaining = con.execute(text(
            "SELECT id, unit_price_try, valid_from FROM billing_rate ORDER BY id"
        )).fetchall()
        print("\nKalan billing_rate kayıtları:")
        for r in remaining:
            print(f"  id={r[0]} fiyat={r[1]} valid_from={r[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
