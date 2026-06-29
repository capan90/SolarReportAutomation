from app.core.config import settings

# Neden: DATABASE_URL konfigürasyonunu okumak ve eksiklik durumunda fail-fast yapmak.
DATABASE_URL = settings.database_url.strip() if settings.database_url else ""

if not DATABASE_URL:
    raise ValueError(
        "Kritik veritabanı konfigürasyonu eksik: DATABASE_URL ortam değişkeni tanımlanmalıdır. "
        "Lütfen .env dosyasını kontrol edin."
    )
