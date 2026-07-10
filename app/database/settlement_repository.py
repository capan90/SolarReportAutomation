from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from app.core.logger import setup_logger
from app.database.db_session import SessionLocal, create_tables
from app.database.models import SettlementHourly, SettlementDaily, SettlementMonthly
from app.settlement.models import HourlySettlement

logger = setup_logger("SettlementRepository")


def _totals(settlements: List[HourlySettlement]) -> Dict[str, float]:
    """Neden: Gün/ay agregatları için beş metriğin toplamını tek yerde hesaplamak."""
    return {
        "production_kwh": sum(s.production_kwh for s in settlements),
        "consumption_kwh": sum(s.consumption_kwh for s in settlements),
        "settled_kwh": sum(s.settled_kwh for s in settlements),
        "grid_import_kwh": sum(s.grid_import_kwh for s in settlements),
        "grid_export_kwh": sum(s.grid_export_kwh for s in settlements),
    }


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

