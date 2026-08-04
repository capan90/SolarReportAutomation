from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Dict

from sqlalchemy import func

from app.core.logger import setup_logger
from app.database.db_session import SessionLocal, create_tables
from app.database.models import (
    SettlementHourly, SettlementDaily, SettlementMonthly, SettlementReconciliation,
)
from app.settlement.models import HourlySettlement

logger = setup_logger("SettlementRepository")

# Neden: Beş mahsuplaşma metriğinin adı hem agregatlarda hem ADR-0003 karşılaştırma
# katmanında kullanılıyor; tek yerde tanımlı olsun ki ikisi ayrışmasın.
RECON_METRICS = [
    "production_kwh",
    "consumption_kwh",
    "settled_kwh",
    "grid_import_kwh",
    "grid_export_kwh",
]


def _totals(settlements: List[HourlySettlement]) -> Dict[str, float]:
    """Neden: Gün/ay agregatları için beş metriğin toplamını tek yerde hesaplamak."""
    return {m: sum(getattr(s, m) for s in settlements) for m in RECON_METRICS}


class SettlementRepository:
    """
    Neden: Mahsuplaşma sonuçlarını settlement_hourly / settlement_daily /
    settlement_monthly tablolarına idempotent (upsert) şekilde yazmak.
    Aynı dönem yeniden hesaplanırsa kayıtlar güncellenir, mükerrer satır oluşmaz.
    """

    def __init__(self):
        # Neden: create_all idempotenttir; ilk kullanımda tabloların varlığını garanti eder.
        create_tables()

    def upsert_hourly(self, settlements: List[HourlySettlement]) -> int:
        """
        Neden: Saatlik kayıtları (date, hour) anahtarına göre ekler/günceller.
        Dönüş: işlenen satır sayısı.
        """
        session = SessionLocal()
        count = 0
        try:
            for s in settlements:
                ts = datetime.strptime(str(s.timestamp), "%Y-%m-%d %H:%M:%S")
                row = (
                    session.query(SettlementHourly)
                    .filter(SettlementHourly.date == ts.date(), SettlementHourly.hour == ts.hour)
                    .first()
                )
                if row is None:
                    row = SettlementHourly(date=ts.date(), hour=ts.hour)
                    session.add(row)
                row.timestamp = ts
                row.production_kwh = float(s.production_kwh)
                row.consumption_kwh = float(s.consumption_kwh)
                row.settled_kwh = float(s.settled_kwh)
                row.grid_import_kwh = float(s.grid_import_kwh)
                row.grid_export_kwh = float(s.grid_export_kwh)
                count += 1
            session.commit()
            logger.info(f"settlement_hourly upsert tamamlandı: {count} satır")
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_daily(self, date: str, settlements: List[HourlySettlement]) -> int:
        """
        Neden: Bir güne ait saatlik kayıtları toplayıp settlement_daily'ye
        tek satır olarak ekler/günceller. date formatı: YYYY-MM-DD.
        """
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        totals = _totals(settlements)

        session = SessionLocal()
        try:
            row = (
                session.query(SettlementDaily)
                .filter(SettlementDaily.date == target_date)
                .first()
            )
            if row is None:
                row = SettlementDaily(date=target_date)
                session.add(row)
            for key, value in totals.items():
                setattr(row, key, float(value))
            session.commit()
            logger.info(f"settlement_daily upsert tamamlandı: {target_date}")
            return 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_monthly(self, year: int, month: int, settlements: List[HourlySettlement]) -> int:
        """
        Neden: Bir aya ait saatlik kayıtları toplayıp settlement_monthly'ye
        tek satır olarak ekler/günceller.
        """
        totals = _totals(settlements)

        session = SessionLocal()
        try:
            row = (
                session.query(SettlementMonthly)
                .filter(SettlementMonthly.year == year, SettlementMonthly.month == month)
                .first()
            )
            if row is None:
                row = SettlementMonthly(year=year, month=month)
                session.add(row)
            for key, value in totals.items():
                setattr(row, key, float(value))
            session.commit()
            logger.info(f"settlement_monthly upsert tamamlandı: {year}-{month:02d}")
            return 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_hourly_month_snapshot(self, year: int, month: int) -> Dict[str, Dict[str, float]]:
        """
        Neden: ADR-0003 Faz 1 — aylık iş DB'ye yazmadan ÖNCE o ayda hâlihazırda ne
        olduğunu görmek zorunda. settlement_hourly'deki ilgili ay kayıtları güne
        gruplanıp beş metriğin toplamı ve o günün saat sayısı ile döner.

        Dönüş: {"YYYY-MM-DD": {"production_kwh": .., ..., "hours": 24}}
        Ay hiç yoksa boş sözlük (hata değil — ilk koşuda beklenen durum).
        """
        session = SessionLocal()
        try:
            rows = (
                session.query(SettlementHourly)
                .filter(
                    SettlementHourly.date >= date(year, month, 1),
                    SettlementHourly.date < (date(year + 1, 1, 1) if month == 12
                                             else date(year, month + 1, 1)),
                )
                .all()
            )
            snapshot: Dict[str, Dict[str, float]] = {}
            for row in rows:
                key = row.date.strftime("%Y-%m-%d")
                day = snapshot.setdefault(
                    key, {m: 0.0 for m in RECON_METRICS} | {"hours": 0}
                )
                for m in RECON_METRICS:
                    day[m] += float(getattr(row, m) or 0.0)
                day["hours"] += 1
            return snapshot
        finally:
            session.close()

    def save_reconciliation(self, run_id: str, target_month: str,
                            comparisons: List[Dict]) -> int:
        """
        Neden: Karşılaştırma sonuçlarını settlement_reconciliation'a yazar (ADR-0003
        Faz 1). Eşleşen satırlar da yazılır — payda kaybolmasın diye.

        comparisons: _compare_month_with_db çıktısı. Dönüş: yazılan satır sayısı.
        """
        session = SessionLocal()
        try:
            for c in comparisons:
                session.add(SettlementReconciliation(
                    run_id=run_id,
                    target_month=target_month,
                    date=datetime.strptime(c["date"], "%Y-%m-%d").date(),
                    metric=c["metric"],
                    db_value=float(c["db_value"]),
                    scrape_value=float(c["scrape_value"]),
                    diff=float(c["diff"]),
                    diff_pct=None if c["diff_pct"] is None else float(c["diff_pct"]),
                    within_tolerance=bool(c["within_tolerance"]),
                    db_hours=int(c["db_hours"]),
                    scrape_hours=int(c["scrape_hours"]),
                ))
            session.commit()
            logger.info("settlement_reconciliation yazıldı: %d satır (%s)",
                        len(comparisons), target_month)
            return len(comparisons)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_monthly(self, year: int, month: int) -> Optional[Dict[str, float]]:
        """
        Neden: Aylık raporun 'önceki ay karşılaştırması' için kayıtlı ay
        agregatını sözlük olarak döndürmek (yoksa None).
        """
        session = SessionLocal()
        try:
            row = (
                session.query(SettlementMonthly)
                .filter(SettlementMonthly.year == year, SettlementMonthly.month == month)
                .first()
            )
            if row is None:
                return None
            return {
                "production_kwh": row.production_kwh or 0.0,
                "consumption_kwh": row.consumption_kwh or 0.0,
                "settled_kwh": row.settled_kwh or 0.0,
                "grid_import_kwh": row.grid_import_kwh or 0.0,
                "grid_export_kwh": row.grid_export_kwh or 0.0,
            }
        finally:
            session.close()

    def list_hourly_month(self, year: int, month: int) -> List[HourlySettlement]:
        """
        Neden: Aylık Excel raporu, portala HİÇ gitmeden yalnızca DB'den yeniden
        üretilebilsin diye ayın saatlik kayıtlarını döndürür (2026-08-04 bayat rapor
        olayı). Aynı veri MonthlySettlementJob'ın rapor yazıcısına beslenir.

        SALT OKUMA — bu metot hiçbir tabloya yazmaz.
        """
        session = SessionLocal()
        try:
            rows = (
                session.query(SettlementHourly)
                .filter(
                    SettlementHourly.date >= date(year, month, 1),
                    SettlementHourly.date < (date(year + 1, 1, 1) if month == 12
                                             else date(year, month + 1, 1)),
                )
                .order_by(SettlementHourly.timestamp)
                .all()
            )
            return [
                HourlySettlement(
                    timestamp=str(r.timestamp),
                    production_kwh=float(r.production_kwh or 0.0),
                    consumption_kwh=float(r.consumption_kwh or 0.0),
                    settled_kwh=float(r.settled_kwh or 0.0),
                    grid_export_kwh=float(r.grid_export_kwh or 0.0),
                    grid_import_kwh=float(r.grid_import_kwh or 0.0),
                )
                for r in rows
            ]
        finally:
            session.close()

    def has_daily_data(self, date: str) -> bool:
        """settlement_daily tablosunda o tarih var mı?"""
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return False
        session = SessionLocal()
        try:
            row = (
                session.query(SettlementDaily)
                .filter(SettlementDaily.date == target_date)
                .first()
            )
            return row is not None
        finally:
            session.close()

    def count_hourly(self, date: str) -> int:
        """
        Neden: Veri-eksik kontrolü "gün var mı"nın yanında "gün TAM mı"yı da sormak
        zorunda. 2026-07-13 vakasında settlement_daily satırı VARDI ama
        settlement_hourly yalnızca 12 saat içeriyordu (yarım kalan çekim) — yalnızca
        satır varlığına bakan bir kontrol o günü sağlıklı sayardı.

        Geçersiz tarih biçimi veri eksikliği değil çağıran hatasıdır; ValueError
        fırlatılır (has_daily_data'nın False'u ile karıştırılmasın).
        """
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(f"Geçersiz tarih biçimi: {date!r} (beklenen YYYY-MM-DD)") from e
        session = SessionLocal()
        try:
            return int(
                session.query(func.count(SettlementHourly.id))
                .filter(SettlementHourly.date == target_date)
                .scalar() or 0
            )
        finally:
            session.close()

    def has_monthly_data(self, year: int, month: int) -> bool:
        """settlement_monthly tablosunda o ay var mı?"""
        session = SessionLocal()
        try:
            row = (
                session.query(SettlementMonthly)
                .filter(SettlementMonthly.year == year, SettlementMonthly.month == month)
                .first()
            )
            return row is not None
        finally:
            session.close()

    def get_daily_report_path(self, date: str) -> Optional[str]:
        """outputs/reports/YYYY-MM/mahsup_YYYYMMDD.xlsx varsa path döndür"""
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return None
        month_str = dt.strftime("%Y-%m")
        formatted_date = dt.strftime("%Y%m%d")
        path = Path("outputs/reports") / month_str / f"mahsup_{formatted_date}.xlsx"
        return str(path) if path.exists() else None

    def get_monthly_report_path(self, year: int, month: int) -> Optional[str]:
        """outputs/reports/YYYY-MM/mahsup_YYYYMM_aylik.xlsx varsa path döndür"""
        month_str = f"{year:04d}-{month:02d}"
        formatted_month = f"{year:04d}{month:02d}"
        path = Path("outputs/reports") / month_str / f"mahsup_{formatted_month}_aylik.xlsx"
        return str(path) if path.exists() else None

