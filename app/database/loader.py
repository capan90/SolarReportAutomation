import json
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import List, Dict, Any, Union, Optional
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.models import SolarPlant, DailyGeneration
from app.database.db_session import SessionLocal
from app.core.logger import setup_logger

logger = setup_logger("DatabaseLoader")

@dataclass
class LoadResult:
    """
    Neden: Yükleme (Load) işlemi sonrasında veritabanına eklenen ve güncellenen
    tesis ile günlük üretim kayıt sayısını ve oluşan hataları özetlemek.
    """
    status: str  # 'SUCCESS' veya 'FAILED'
    inserted_plants: int = 0
    updated_plants: int = 0
    inserted_generations: int = 0
    updated_generations: int = 0
    failed_records: int = 0
    issues: List[str] = field(default_factory=list)

class DatabaseLoader:
    """
    Neden: TransformResult objesinden veya serileştirilmiş JSON dosyasından okunan
    canonical kayıtları transaction kullanarak ve mükerrerliği engelleyerek (UPSERT)
    ilişkisel veritabanına yüklemek.
    """
    def __init__(self, session: Optional[Session] = None):
        self.session_factory = SessionLocal
        self.external_session = session

    def _parse_date(self, val: Any) -> Any:
        """
        Neden: JSON'dan string olarak okunan tarih alanlarını SQLAlchemy için
        datetime.date nesnesine çevirmek.
        """
        if isinstance(val, str):
            try:
                return datetime.strptime(val.split("T")[0], "%Y-%m-%d").date()
            except ValueError:
                return val
        return val

    def load(self, transform_result: Union[Any, str, Path]) -> LoadResult:
        """
        Neden: Girdi verilerini parse etmek ve tek bir transaction altında veritabanına yüklemek.
        """
        logger.info("Veritabanına yükleme (load) işlemi başlatılıyor...")
        
        # 1. Ham Veriyi Oku ve Standardize Et
        records = []
        source_file = "unknown"
        mapping_key = "unknown"
        
        if isinstance(transform_result, (str, Path)):
            try:
                with open(transform_result, "r", encoding="utf-8") as f:
                    data = json.load(f)
                records = data.get("records", [])
                source_file = data.get("source_file", "unknown")
                mapping_key = data.get("mapping_key", "unknown")
            except Exception as e:
                return LoadResult(
                    status="FAILED",
                    issues=[f"Transformed JSON dosyası okunamadı: {e}"]
                )
        else:
            # Dataclass TransformResult nesnesi
            records = [
                {
                    "entity": r.entity,
                    "data": r.data,
                    "source_row_number": r.source_row_number
                }
                for r in transform_result.records
            ]
            source_file = transform_result.source_file
            mapping_key = transform_result.mapping_key

        if not records:
            logger.warning("Yüklenecek kayıt bulunamadı.")
            return LoadResult(status="SUCCESS", issues=["Yüklenecek kayıt bulunamadı."])

        # 2. Satır Numarasına Göre Tesis Adı İlişki Haritasını Kur
        row_to_plant_name: Dict[int, str] = {}
        for rec in records:
            if rec["entity"] == "solar_plant":
                row_to_plant_name[rec["source_row_number"]] = rec["data"]["plant_name"]

        # 3. Session Yönetimi
        session = self.external_session if self.external_session else self.session_factory()
        dialect_name = session.bind.dialect.name
        
        # İstatistikler
        result = LoadResult(status="SUCCESS")
        plant_name_to_id: Dict[str, int] = {}

        try:
            # --- TRANSACTION BAŞLANGICI ---
            # A. Tesisleri Upsert Et
            for rec in records:
                if rec["entity"] != "solar_plant":
                    continue
                
                data = rec["data"]
                plant_name = data["plant_name"]
                
                db_values = {
                    "name": plant_name,
                    "installed_power_kwp": data["installed_power_kwp"],
                    "grid_connection_date": self._parse_date(data["grid_connection_date"]),
                    "address": data.get("address")
                }

                # Kayıt var mı denetle (İstatistik sayacı için)
                existing = session.query(SolarPlant).filter_by(name=plant_name).first()
                is_update = existing is not None

                if dialect_name == "postgresql":
                    stmt = pg_insert(SolarPlant).values(db_values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["name"],
                        set_={
                            "installed_power_kwp": stmt.excluded.installed_power_kwp,
                            "grid_connection_date": stmt.excluded.grid_connection_date,
                            "address": stmt.excluded.address,
                            "updated_at": datetime.utcnow()
                        }
                    )
                    session.execute(stmt)
                    plant_id = session.query(SolarPlant).filter_by(name=plant_name).first().id
                elif dialect_name == "sqlite":
                    stmt = sqlite_insert(SolarPlant).values(db_values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["name"],
                        set_={
                            "installed_power_kwp": stmt.excluded.installed_power_kwp,
                            "grid_connection_date": stmt.excluded.grid_connection_date,
                            "address": stmt.excluded.address,
                            "updated_at": datetime.utcnow()
                        }
                    )
                    session.execute(stmt)
                    plant_id = session.query(SolarPlant).filter_by(name=plant_name).first().id
                else:
                    # Genel ANSI SQL Fallback
                    if is_update:
                        existing.installed_power_kwp = db_values["installed_power_kwp"]
                        existing.grid_connection_date = db_values["grid_connection_date"]
                        existing.address = db_values["address"]
                        existing.updated_at = datetime.utcnow()
                        plant_id = existing.id
                    else:
                        new_plant = SolarPlant(**db_values)
                        session.add(new_plant)
                        session.flush()
                        plant_id = new_plant.id

                plant_name_to_id[plant_name] = plant_id
                
                if is_update:
                    result.updated_plants += 1
                else:
                    result.inserted_plants += 1

            # B. Günlük Üretimleri Upsert Et
            for rec in records:
                if rec["entity"] != "daily_generation":
                    continue
                
                data = rec["data"]
                source_row = rec["source_row_number"]
                
                # İlgili satırdaki tesis adını bul
                plant_name = row_to_plant_name.get(source_row)
                if not plant_name:
                    raise ValueError(f"Satır {source_row} için ilişkili tesis adı bulunamadı.")
                
                plant_id = plant_name_to_id.get(plant_name)
                if not plant_id:
                    raise ValueError(f"Tesis '{plant_name}' için veritabanı ID'si çözülemedi.")

                target_date = self._parse_date(data["date"])
                db_values = {
                    "plant_id": plant_id,
                    "date": target_date,
                    "yield_today_kwh": data["yield_today_kwh"],
                    "total_yield_kwh": data["total_yield_kwh"],
                    "equivalent_hours": data["equivalent_hours"],
                    "revenue_today": data.get("revenue_today"),
                    "revenue_currency": data.get("revenue_currency"),
                    "co2_reduction_kg": data["co2_reduction_kg"],
                    "inverter_serial_numbers": data.get("inverter_serial_numbers"),
                    "raw_archive_file": source_file
                }

                # Kayıt var mı denetle (İstatistik sayacı için)
                existing_gen = session.query(DailyGeneration).filter_by(
                    plant_id=plant_id,
                    date=target_date
                ).first()
                is_update = existing_gen is not None

                if dialect_name == "postgresql":
                    stmt = pg_insert(DailyGeneration).values(db_values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["plant_id", "date"],
                        set_={
                            "yield_today_kwh": stmt.excluded.yield_today_kwh,
                            "total_yield_kwh": stmt.excluded.total_yield_kwh,
                            "equivalent_hours": stmt.excluded.equivalent_hours,
                            "revenue_today": stmt.excluded.revenue_today,
                            "revenue_currency": stmt.excluded.revenue_currency,
                            "co2_reduction_kg": stmt.excluded.co2_reduction_kg,
                            "inverter_serial_numbers": stmt.excluded.inverter_serial_numbers,
                            "raw_archive_file": stmt.excluded.raw_archive_file,
                            "updated_at": datetime.utcnow()
                        }
                    )
                    session.execute(stmt)
                elif dialect_name == "sqlite":
                    stmt = sqlite_insert(DailyGeneration).values(db_values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["plant_id", "date"],
                        set_={
                            "yield_today_kwh": stmt.excluded.yield_today_kwh,
                            "total_yield_kwh": stmt.excluded.total_yield_kwh,
                            "equivalent_hours": stmt.excluded.equivalent_hours,
                            "revenue_today": stmt.excluded.revenue_today,
                            "revenue_currency": stmt.excluded.revenue_currency,
                            "co2_reduction_kg": stmt.excluded.co2_reduction_kg,
                            "inverter_serial_numbers": stmt.excluded.inverter_serial_numbers,
                            "raw_archive_file": stmt.excluded.raw_archive_file,
                            "updated_at": datetime.utcnow()
                        }
                    )
                    session.execute(stmt)
                else:
                    if is_update:
                        existing_gen.yield_today_kwh = db_values["yield_today_kwh"]
                        existing_gen.total_yield_kwh = db_values["total_yield_kwh"]
                        existing_gen.equivalent_hours = db_values["equivalent_hours"]
                        existing_gen.revenue_today = db_values["revenue_today"]
                        existing_gen.revenue_currency = db_values["revenue_currency"]
                        existing_gen.co2_reduction_kg = db_values["co2_reduction_kg"]
                        existing_gen.inverter_serial_numbers = db_values["inverter_serial_numbers"]
                        existing_gen.raw_archive_file = db_values["raw_archive_file"]
                        existing_gen.updated_at = datetime.utcnow()
                    else:
                        new_gen = DailyGeneration(**db_values)
                        session.add(new_gen)

                if is_update:
                    result.updated_generations += 1
                else:
                    result.inserted_generations += 1

            # Dışarıdan gelen session ise commit yükümlülüğü dışarıdadır,
            # değilse commit işlemini yap ve kapat.
            if not self.external_session:
                session.commit()
                logger.info("Transaction başarıyla commit edildi.")
            
        except Exception as e:
            if not self.external_session:
                session.rollback()
                logger.error(f"Hata oluştu, transaction ROLLBACK yapıldı: {e}")
            result.status = "FAILED"
            result.failed_records = len(records)
            result.issues.append(f"Veritabanı transaction hatası: {str(e)}")
            
        finally:
            if not self.external_session:
                session.close()

        logger.info(f"Yükleme tamamlandı. Durum: {result.status}. Tesisler (Yeni: {result.inserted_plants}, Güncellenen: {result.updated_plants}), Üretimler (Yeni: {result.inserted_generations}, Güncellenen: {result.updated_generations})")
        return result
