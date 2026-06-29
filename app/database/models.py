from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Date,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.db_session import Base

class SolarPlant(Base):
    """
    Neden: Güneş enerjisi santrallerinin (plants) sabit ve kurulu güç bilgilerini
    temsil eden ORM modeli.
    """
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    installed_power_kwp = Column(Numeric(12, 2), nullable=False)
    grid_connection_date = Column(Date, nullable=False)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişki: Tesisin günlük üretim kayıtları
    generations = relationship("DailyGeneration", back_populates="plant", cascade="all, delete-orphan")

class DailyGeneration(Base):
    """
    Neden: Tesislere ait günlük üretim, gelir, eşdeğer saat ve çevresel fayda (CO2)
    metriklerini tutan zamansal ORM modeli.
    """
    __tablename__ = "daily_generations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    yield_today_kwh = Column(Numeric(12, 2), nullable=False)
    total_yield_kwh = Column(Numeric(15, 2), nullable=False)
    equivalent_hours = Column(Numeric(6, 2), nullable=False)
    revenue_today = Column(Numeric(12, 2), nullable=True)
    revenue_currency = Column(String(10), nullable=True)
    co2_reduction_kg = Column(Numeric(12, 2), nullable=False)
    inverter_serial_numbers = Column(Text, nullable=True)
    raw_archive_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişki: Üretim kaydının ait olduğu tesis
    plant = relationship("SolarPlant", back_populates="generations")

    # Neden: Aynı tesis için aynı günde mükerrer üretim kaydı girilmesini engellemek.
    __table_args__ = (
        UniqueConstraint("plant_id", "date", name="uq_plant_date"),
    )
