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


class SettlementReconciliation(Base):
    """
    Neden: Aylık iş, günlük işin yazdığı veriyi üzerine yazıyor ve iki yolun aynı
    sayıyı üretip üretmediği hiç ölçülmedi (ADR-0003). Bu tablo, aylık iş DB'ye
    YAZMADAN ÖNCE yaptığı karşılaştırmayı kaydeder — Faz 2 (hibrit) kararı 3 aylık
    birikimle bu tablodan verilecek.

    Uzun (long) format: her koşuda her gün × her metrik için bir satır. EŞLEŞEN
    günler de yazılır — yalnızca farklar yazılsaydı "kaç günün kaçı farklı" oranının
    paydası kaybolurdu.

    `within_tolerance=False` iki durumdan biri anlamına gelir: (a) metrik değeri
    toleransı aştı, (b) kapsam uyuşmazlığı var (db_hours != scrape_hours). İkisini
    ayırt etmek için db_hours/scrape_hours kolonlarına bakılır. Basit "sorun var mı"
    sorgusunun hiçbir vakayı sessizce kaçırmaması için bu şekilde birleştirildi.
    """
    __tablename__ = "settlement_reconciliation"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(80), nullable=False)
    target_month = Column(String(7), nullable=False, index=True)  # "2026-07"
    date = Column(Date, nullable=False)
    metric = Column(String(24), nullable=False)
    db_value = Column(Float, nullable=False)       # yazmadan ÖNCE DB'de duran değer
    scrape_value = Column(Float, nullable=False)   # aylık işin yeni hesapladığı değer
    diff = Column(Float, nullable=False)           # scrape_value - db_value
    diff_pct = Column(Float)                       # db_value == 0 ise NULL (bölme yok)
    within_tolerance = Column(Boolean, nullable=False)
    db_hours = Column(Integer, nullable=False)     # o gün DB'de kaç saatlik kayıt vardı
    scrape_hours = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('run_id', 'date', 'metric', name='uq_settlement_reconciliation'),
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


class BillingRate(Base):
    """
    Neden: Faturalama birim fiyatlarının APPEND-ONLY geçmişi (ADR-0002 §2).
    Katsayı değişikliği UPDATE değil yeni satırdır; böylece "kim, ne zaman, hangi
    değeri girdi" denetlenebilir kalır ve geçmiş aylar etkilenmez.

    valid_from ayın İLK GÜNÜ olmak zorundadır (servis katmanı doğrular). Bir ay için
    geçerli katsayı = valid_from <= ay sonu olan en güncel kayıt. Yalnızca created_at'e
    bakan "en son değer" mantığı, dashboard'daki geçmiş ay yeniden hesaplama
    özelliğinde eski aylara güncel (yanlış) katsayı uygulardı.

    Birim fiyatlar KDV HARİÇ (net) TL/kWh'dir; KDV kapsam dışıdır (ADR-0002).
    """
    __tablename__ = "billing_rate"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Neden: Şimdilik tek tip ('EXCESS_SALE_UNIT_PRICE') var; ileride başka sabit
    # tarifeler eklenirse şema değişmeden genişler.
    rate_type = Column(String(50), nullable=False)
    # Neden: Para Float tutulmaz (ADR-0002 §8). Birim fiyat 6 haneye kadar hassas
    # olabilir (ör. 2.909687).
    unit_price_try = Column(Numeric(18, 6), nullable=False)
    valid_from = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=False)
    note = Column(Text, nullable=True)

    # Neden: Aynı tarife tipi için aynı geçerlilik tarihinde iki satır olursa
    # "o ay hangi katsayı geçerli" sorusu belirsizleşir.
    __table_args__ = (
        UniqueConstraint("rate_type", "valid_from", name="uq_billing_rate_type_valid_from"),
    )


class MonthlyBilling(Base):
    """
    Neden: Bir ayın kilitlenmiş finansal kaydı (ADR-0002 §3-4).

    KİLİTLENEN KATSAYIDIR, TUTAR DEĞİLDİR:
    - excess_sale_rate_try satır ilk oluşturulurken yazılır ve bir daha değişmez.
    - osb_unit_price_try elle girilir; girildiğinde status LOCKED olur ve değişmez.
    - *_kwh_snapshot her yeniden hesapta güncellenir (eksik veri sonradan tamamlanabilir).
    - *_try tutarlar kilitli katsayılarla her hesapta yeniden türetilir.

    status:
      PENDING_RATE = OSB birim fiyatı henüz girilmedi (veya veri tutarsız)
      LOCKED       = OSB birim fiyatı girildi, katsayılar kilitli
    """
    __tablename__ = "monthly_billing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    # --- Kilitli girdiler ---
    excess_sale_rate_try = Column(Numeric(18, 6), nullable=True)
    # Neden: Hangi billing_rate satırından geldiği izlenebilsin (denetim).
    excess_sale_rate_id = Column(Integer, ForeignKey("billing_rate.id"), nullable=True)
    osb_unit_price_try = Column(Numeric(18, 6), nullable=True)
    osb_price_entered_by = Column(String(100), nullable=True)
    osb_price_entered_at = Column(DateTime, nullable=True)

    # --- Hesabın dayandığı kWh değerleri ---
    production_kwh_snapshot = Column(Numeric(18, 3), nullable=True)
    excess_sale_kwh_snapshot = Column(Numeric(18, 3), nullable=True)

    # --- Türetilmiş tutarlar (KDV hariç) ---
    excess_sale_invoice_try = Column(Numeric(18, 2), nullable=True)
    osb_deduction_try = Column(Numeric(18, 2), nullable=True)

    status = Column(String(20), nullable=False, default="PENDING_RATE")
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_monthly_billing_year_month"),
    )





