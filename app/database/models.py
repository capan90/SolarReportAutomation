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

class EtlRun(Base):
    """
    Neden: Her ETL pipeline çalışmasının başlangıç/bitiş zamanları, durum bilgileri,
    üretilen dosya referansları, veritabanı istatistikleri ve hata sayılarını
    kalıcı olarak saklamak (Run History & Audit Trail).
    """
    __tablename__ = "etl_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    cli_mode = Column(String(50), nullable=True)
    target_date = Column(Date, nullable=True)
    source_file = Column(String(255), nullable=True)
    profiling_file = Column(String(255), nullable=True)
    validation_file = Column(String(255), nullable=True)
    transformed_file = Column(String(255), nullable=True)
    inserted_records = Column(Integer, default=0)
    updated_records = Column(Integer, default=0)
    skipped_stages = Column(Text, nullable=True)
    issues_count = Column(Integer, default=0)
    warnings_count = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    exit_code = Column(Integer, nullable=True)
    hostname = Column(String(255), nullable=True)
    git_commit = Column(String(80), nullable=True)
    source_name = Column(String(100), default="isolarcloud", nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class NotificationHistory(Base):
    """
    Neden: Gönderilen e-posta bildirimlerinin hangi pipeline çalışmasına (run_id) 
    ait olduğunu, gönderim durumunu, deneme sayılarını ve varsa hata detaylarını
    veritabanında denetim (audit) amacıyla saklamak.
    """
    __tablename__ = "notification_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)
    channel = Column(String(50), nullable=False)
    recipient = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)  # SENT, FAILED
    attempt_count = Column(Integer, nullable=False, default=1)
    sent_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)


class RetryHistory(Base):
    """
    Neden: Pipeline veya dış servis operasyonlarında gerçekleşen tekrar deneme (retry)
    işlemlerini, hangi çalışmada (run_id) ve hangi hata ile kaçıncı kez denendiği bilgileriyle
    birlikte denetlemek ve Dashboard metrikleri hazırlamak.
    """
    __tablename__ = "retry_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)
    operation = Column(String(100), nullable=False)
    attempt = Column(Integer, nullable=False)
    delay_seconds = Column(Numeric(6, 2), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PerformanceMetric(Base):
    """
    Neden: Pipeline aşama süreleri, sistem durumları (CPU/RAM/Disk) ve operasyonel metriklerin 
    canlı ortamlarda izlenebilmesi ve Dashboard'lara veri beslenebilmesi için veritabanında saklanması.
    """
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)
    stage_name = Column(String(100), nullable=True)
    metric_category = Column(String(50), nullable=False)  # system, application, business, operational
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Numeric(12, 4), nullable=False)
    labels = Column(Text, nullable=True)                  # JSON string dimensions
    timestamp = Column(DateTime, default=datetime.utcnow)



