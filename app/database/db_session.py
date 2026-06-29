from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.database.db_config import DATABASE_URL
from app.core.logger import setup_logger

logger = setup_logger("DBSession")

# Neden: Veritabanı motorunu (engine) ve session fabrikasını (SessionLocal) kurmak.
# PostgreSQL veya SQLite olabileceği için esnek bağlantı ayarları uygulandı.
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite için multi-thread erişim izni ver
    connect_args = {"check_same_thread": False}

try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.critical(f"SQLAlchemy engine oluşturulurken hata: {e}")
    raise

Base = declarative_base()

def create_tables() -> None:
    """
    Neden: Tanımlı ORM modellerini (Base altındaki tüm tabloları) veritabanında oluşturmak.
    """
    logger.info("Veritabanı tabloları oluşturuluyor...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Tablolar başarıyla oluşturuldu.")
    except Exception as e:
        logger.error(f"Tablolar oluşturulurken hata: {e}")
        raise

def test_connection() -> bool:
    """
    Neden: Veritabanı bağlantısının aktif ve sağlıklı olup olmadığını kontrol etmek.
    """
    logger.info("Veritabanı bağlantısı test ediliyor...")
    try:
        # Basit bir SELECT 1 sorgusu çalıştır
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        logger.info("Veritabanı bağlantısı BAŞARILI.")
        return True
    except Exception as e:
        logger.error(f"Veritabanı bağlantı testi BAŞARISIZ: {e}")
        return False
