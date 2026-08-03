"""
Neden: Bir ayın faturalama satırını (monthly_billing) SCRAPING YAPMADAN, veritabanında
zaten duran mahsuplaşma sonucundan oluşturur.

Vaka (2026-08-03): Mayıs 2026'nın mahsuplaşması tamdı (settlement_daily 31 gün,
settlement_hourly 744/744 saat, settlement_monthly mevcut) ama monthly_billing satırı
YOKTU — faturalama katmanı (ADR-0002 / S19) Temmuz sonunda eklendi, Mayıs koşusu ondan
önceydi. Satır olmadığı için OSB birim fiyatı hiçbir ekrandan girilemiyordu.

Tek alternatif MonthlySettlementJob'u Mayıs için yeniden koşturmaktı; o iş iSolar ve
GAOSB'den veriyi YENİDEN ÇEKER ve mevcut mahsuplaşma verisinin ÜZERİNE YAZAR (ADR-0003'te
takip edilen teknik borç). Eksiksiz duran bir ayı yeniden çekimle riske atmak yerine,
faturalama adımı izole edilir.

Bu script'in dokunduğu TEK tablo monthly_billing'dir:
- settlement_hourly / settlement_daily / settlement_monthly'ye YALNIZCA OKUMA yapar.
- Portala hiç çıkmaz, tarayıcı açmaz.
- BillingService.compute() üzerinden gider; katsayı snapshot'ı, tutar türetme ve veri
  tutarlılığı kuralları (ADR-0002 §6-7) aynen uygulanır, ikinci bir hesap yolu doğmaz.

Girdi eşlemesi MonthlySettlementJob ile birebir aynıdır (monthly_settlement_job.py:716):
    production_kwh  = settlement toplam production_kwh
    excess_sale_kwh = settlement toplam grid_export_kwh
Eşleme Haziran ve Temmuz 2026 üzerinde doğrulandı: settlement_monthly'den türetilen
değerler, o ayların KAYITLI monthly_billing snapshot'larıyla (3 hane hassasiyetle) birebir
tutuyor.

Kullanım:
    python scripts/create_monthly_billing_row.py --month 2026-05           # dry-run
    python scripts/create_monthly_billing_row.py --month 2026-05 --apply
"""
import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="monthly_billing satırını mevcut mahsuplaşmadan oluştur (scraping yok)")
    parser.add_argument("--month", required=True, help="Hedef ay (YYYY-MM)")
    parser.add_argument("--apply", action="store_true", help="Gerçekten yaz (yoksa dry-run)")
    parser.add_argument("--database-url", default=None, help="Hedef DB (varsayılan: .env)")
    args = parser.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from sqlalchemy import text  # noqa: E402
    from app.billing.service import BillingService  # noqa: E402
    from app.database.db_session import SessionLocal  # noqa: E402

    year, month = int(args.month[:4]), int(args.month[5:7])
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== {year}-{month:02d} faturalama satırı [{mode}] ===\n")

    session = SessionLocal()
    try:
        agg = session.execute(text(
            "SELECT production_kwh, grid_export_kwh FROM settlement_monthly "
            "WHERE year = :y AND month = :m"
        ), {"y": year, "m": month}).fetchone()

        if agg is None:
            print(f"DURDURULDU: settlement_monthly'de {year}-{month:02d} yok. "
                  f"Bu ayın mahsuplaşması hiç hesaplanmamış — izole faturalama yapılamaz.")
            return 2

        # Neden: Kısmi bir ay (eksik saat) faturalanırsa tutar sessizce düşük çıkar.
        hours = session.execute(text(
            "SELECT COUNT(*) FROM settlement_hourly WHERE date >= make_date(:y,:m,1) "
            "AND date < (make_date(:y,:m,1) + INTERVAL '1 month')"
        ), {"y": year, "m": month}).scalar()
        days = session.execute(text(
            "SELECT COUNT(*) FROM settlement_daily WHERE date >= make_date(:y,:m,1) "
            "AND date < (make_date(:y,:m,1) + INTERVAL '1 month')"
        ), {"y": year, "m": month}).scalar()

        existing = session.execute(text(
            "SELECT status, excess_sale_rate_try, osb_unit_price_try FROM monthly_billing "
            "WHERE year = :y AND month = :m"
        ), {"y": year, "m": month}).fetchone()
    finally:
        session.close()

    production = Decimal(str(agg[0]))
    excess = Decimal(str(agg[1]))

    print("Mahsuplaşma kaynağı (settlement_monthly — SALT OKUNUR):")
    print(f"  production_kwh  = {production}")
    print(f"  grid_export_kwh = {excess}   (faturalamada 'excess_sale_kwh')")
    print(f"  kapsam          = {days} gün / {hours} saat")

    if existing:
        print(f"\nDURDURULDU: {year}-{month:02d} için monthly_billing satırı ZATEN VAR "
              f"(status={existing[0]}, katsayı={existing[1]}, osb={existing[2]}). "
              f"Bu script yalnızca eksik satır oluşturur; mevcut satıra dokunmaz.")
        return 2

    service = BillingService()
    from app.billing.service import _month_end  # noqa: E402
    rate = service.get_current_rate(as_of=_month_end(year, month))
    print(f"\nAy sonuna göre etkin Enerjisa katsayısı: "
          f"{rate.unit_price_try if rate else 'YOK'}"
          f"{'' if rate else '  <-- katsayı yoksa fatura tutarı hesaplanmaz'}")

    if rate:
        print(f"  beklenen fatura = {excess} x {rate.unit_price_try} = "
              f"{(excess * rate.unit_price_try).quantize(Decimal('0.01'))} TL")
    print(f"  öz tüketim      = {production - excess} kWh "
          f"(OSB kesintisi bu değerle, fiyat girilince hesaplanır)")

    if not args.apply:
        print("\n[DRY-RUN] Hiçbir değişiklik yapılmadı. settlement_* tablolarına dokunulmadı.")
        print("Gerçekten yazmak için: --apply")
        return 0

    result = service.compute(
        year=year, month=month,
        production_kwh=production,
        excess_sale_kwh=excess,
    )
    print(f"\n[APPLY] monthly_billing yazıldı: {result.year}-{result.month:02d} "
          f"status={result.status}")
    print(f"        katsayı={result.excess_sale_rate_try} fatura={result.excess_sale_invoice_try} TL")
    print("        OSB birim fiyatı dashboard'dan girilecek (ay o zaman kilitlenir).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
