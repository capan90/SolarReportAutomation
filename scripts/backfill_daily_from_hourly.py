# -*- coding: utf-8 -*-
"""
Neden: MonthlySettlementJob geçmişte settlement_daily'ye yazmıyordu (yalnızca
hourly + monthly). Aylık job ile doldurulan aylarda dashboard'daki günlük
grafikler/"Mahsuplaşmalarım" boş görünüyordu. Bu script mevcut settlement_hourly
kayıtlarından settlement_daily'yi yeniden türetir (onarım/backfill).

Davranış:
  - settlement_hourly'deki TÜM kayıtları okur, tarihe göre gruplar
  - Her gün için beş metriğin (üretim/tüketim/mahsup/çekiş/satış) toplamını alır
  - settlement_daily'ye upsert eder (var olan gün güncellenir, mükerrer oluşmaz)
  - Eklenen / güncellenen / toplam gün sayısını raporlar

DATABASE_URL .env'den okunur; SQLite (dev) ve PostgreSQL (prod) ile çalışır.

Kullanım: python scripts\\backfill_daily_from_hourly.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_dotenv
load_dotenv()

from app.database.db_session import SessionLocal, create_tables, engine  # noqa: E402
from app.database.models import SettlementDaily, SettlementHourly  # noqa: E402

METRICS = ["production_kwh", "consumption_kwh", "settled_kwh",
           "grid_import_kwh", "grid_export_kwh"]


def main():
    print(f"Veritabanı: {engine.url.render_as_string(hide_password=True)}")
    create_tables()

    session = SessionLocal()
    try:
        hourly_rows = session.query(SettlementHourly).all()
        if not hourly_rows:
            print("settlement_hourly boş — yapılacak bir şey yok.")
            return

        # Tarihe göre grupla ve metrik toplamlarını hesapla
        by_day = defaultdict(lambda: {m: 0.0 for m in METRICS})
        hours_per_day = defaultdict(int)
        for row in hourly_rows:
            day = row.date
            hours_per_day[day] += 1
            for m in METRICS:
                by_day[day][m] += float(getattr(row, m) or 0.0)

        print(f"settlement_hourly: {len(hourly_rows)} satır, {len(by_day)} benzersiz gün")
        incomplete = {d: n for d, n in hours_per_day.items() if n != 24}
        if incomplete:
            # Neden: Eksik saatli gün sessizce tam günmüş gibi yazılmasın; yine de
            # yazılır (mevcut veri en iyi bilgi) ama kullanıcı uyarılır.
            print(f"UYARI: {len(incomplete)} günün saat sayısı 24 değil: "
                  + ", ".join(f"{d} ({n}sa)" for d, n in sorted(incomplete.items())))

        inserted = 0
        updated = 0
        for day in sorted(by_day):
            row = (
                session.query(SettlementDaily)
                .filter(SettlementDaily.date == day)
                .first()
            )
            if row is None:
                row = SettlementDaily(date=day)
                session.add(row)
                inserted += 1
            else:
                updated += 1
            for m in METRICS:
                setattr(row, m, by_day[day][m])
        session.commit()

        total_daily = session.query(SettlementDaily).count()
        print(f"\nSONUÇ: {inserted} gün eklendi, {updated} gün güncellendi "
              f"(settlement_daily toplam: {total_daily} satır)")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
