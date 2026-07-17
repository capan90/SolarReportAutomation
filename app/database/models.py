from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Date,
    Float,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Boolean
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
    # Neden: run_id UUID (36) değil serbest formatlı olabilir; ör.
    # "job-settlement-monthly-YYYY-MM-{ts}" 41+ karakterdir ve PostgreSQL'de
    # varchar(36) taşmasına (StringDataRightTruncation) yol açar.
    run_id = Column(String(100), unique=True, nullable=False)
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
    run_id = Column(String(100), nullable=False)
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
    run_id = Column(String(100), nullable=False)
    operation = Column(String(100), nullable=False)
    attempt = Column(Integer, nullable=False)
    delay_seconds = Column(Numeric(6, 2), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SettlementHourly(Base):
    """
    Neden: Saatlik mahsuplaşma (üretim/tüketim/mahsup) kayıtlarını kalıcı tutmak;
    günlük ve aylık job'lar aynı tabloya upsert eder (date+hour benzersizdir).
    """
    __tablename__ = "settlement_hourly"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=False)  # 0-23
    timestamp = Column(DateTime, nullable=False)
    production_kwh = Column(Float, default=0)
    consumption_kwh = Column(Float, default=0)
    settled_kwh = Column(Float, default=0)
    grid_import_kwh = Column(Float, default=0)
    grid_export_kwh = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('date', 'hour', name='uq_settlement_hourly'),
    )


class SettlementDaily(Base):
    """
    Neden: Gün bazında toplanmış mahsuplaşma metriklerini tutmak (rapor ve
    ay içi karşılaştırmalar için hazır agregat).
    """
    __tablename__ = "settlement_daily"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)
    production_kwh = Column(Float, default=0)
    consumption_kwh = Column(Float, default=0)
    settled_kwh = Column(Float, default=0)
    grid_import_kwh = Column(Float, default=0)
    grid_export_kwh = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class SettlementMonthly(Base):
    """
    Neden: Ay bazında toplanmış mahsuplaşma metriklerini tutmak; aylık raporun
    'önceki ay karşılaştırması' bu tablodan beslenir (year+month benzersizdir).
    """
    __tablename__ = "settlement_monthly"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    production_kwh = Column(Float, default=0)
    consumption_kwh = Column(Float, default=0)
    settled_kwh = Column(Float, default=0)
    grid_import_kwh = Column(Float, default=0)
    grid_export_kwh = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('year', 'month', name='uq_settlement_monthly'),
    )


class PerformanceMetric(Base):
    """
    Neden: Pipeline aşama süreleri, sistem durumları (CPU/RAM/Disk) ve operasyonel metriklerin 
    canlı ortamlarda izlenebilmesi ve Dashboard'lara veri beslenebilmesi için veritabanında saklanması.
    """
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(100), nullable=False)
    stage_name = Column(String(100), nullable=True)
    metric_category = Column(String(50), nullable=False)  # system, application, business, operational
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Numeric(12, 4), nullable=False)
    labels = Column(Text, nullable=True)                  # JSON string dimensions
    timestamp = Column(DateTime, default=datetime.utcnow)


class PlantStatus(Base):
    __tablename__ = "plant_status"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    plant_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    previous_status = Column(String, nullable=True)
    notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DashboardUser(Base):
    __tablename__ = "dashboard_users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    username = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    action = Column(String, nullable=False)
    details = Column(String, nullable=True)
    success = Column(Boolean, default=True)





