import os
from pathlib import Path
from dataclasses import dataclass

# Neden: Proje kök dizinini dinamik olarak tespit etmek ve dosya yolları için referans almak
BASE_DIR = Path(__file__).resolve().parent.parent.parent

def load_dotenv():
    """
    Neden: python-dotenv kütüphanesi yüklü olmasa bile yerel .env dosyasını
    manuel olarak okuyup os.environ'a yüklemek ve harici bağımlılık riskini azaltmak.
    """
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

# Ortam değişkenlerini yükle
load_dotenv()

@dataclass(frozen=True)
class Settings:
    """
    Neden: Uygulama genelinde konfigürasyon değişkenlerinin tek bir immutable (değiştirilemez)
    nesne üzerinden yönetilmesi, tip güvenliği ve yanlışlıkla üzerine yazılmasını engelleme.
    """
    base_url: str
    username: str
    password: str
    download_directory: Path
    log_directory: Path
    report_directory: Path
    chart_directory: Path
    app_env: str
    headless: bool
    database_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    alert_email: str
    
    # Profil Bazlı Konfigürasyonlar
    log_level: str
    timeout_multiplier: float
    dry_run: bool
    strict_validation: bool

    def validate(self):
        """
        Neden: Başlangıçta kritik kimlik bilgilerinin eksik olup olmadığını kontrol etmek
        ve eksiklik durumunda uygulamayı çalıştırmayıp erken aşamada fail etmek (Fail-Fast).
        """
        missing = []
        if not self.base_url:
            missing.append("ISOLAR_BASE_URL")
        if not self.username:
            missing.append("ISOLAR_USERNAME")
        if not self.password:
            missing.append("ISOLAR_PASSWORD")
        
        if missing:
            raise ValueError(f"Kritik ortam değişkenleri eksik: {', '.join(missing)}. Lütfen .env dosyasını kontrol edin.")

# Profil Lojiği
raw_env = os.environ.get("APP_ENV", "development").lower()
if raw_env not in ["development", "test", "staging", "production", "ci", "debug"]:
    raw_env = "development"

# Profile özgü kuralların belirlenmesi
if raw_env == "production":
    p_log_level = "INFO"
    p_timeout_mult = 1.0
    p_dry_run = False
    p_strict = True
elif raw_env in ["staging", "ci"]:
    p_log_level = "INFO" if raw_env == "staging" else "DEBUG"
    p_timeout_mult = 2.0  # CI ortamları yavaş olabileceği için toleransı artır
    p_dry_run = False if raw_env == "staging" else True
    p_strict = True
elif raw_env == "test":
    p_log_level = "WARNING"
    p_timeout_mult = 1.5
    p_dry_run = True
    p_strict = True
elif raw_env == "debug":
    p_log_level = "DEBUG"
    p_timeout_mult = 2.5
    p_dry_run = True
    p_strict = False
else:  # development
    p_log_level = "DEBUG"
    p_timeout_mult = 1.0
    p_dry_run = True
    p_strict = False

# Global ayar nesnesi
settings = Settings(
    base_url=os.environ.get("ISOLAR_BASE_URL", "https://www.isolarcloud.com/"),
    username=os.environ.get("ISOLAR_USERNAME", ""),
    password=os.environ.get("ISOLAR_PASSWORD", ""),
    download_directory=BASE_DIR / Path(os.environ.get("RAW_EXPORTS_DIR", "outputs/raw_exports")),
    log_directory=BASE_DIR / Path(os.environ.get("LOG_DIR", "logs")),
    report_directory=BASE_DIR / Path(os.environ.get("REPORT_OUTPUT_DIR", "outputs/pdf")),
    chart_directory=BASE_DIR / Path(os.environ.get("CHART_OUTPUT_DIR", "outputs/charts")),
    app_env=raw_env,
    headless=os.environ.get("ISOLAR_HEADLESS", "true").lower() == "true",
    database_url=os.environ.get("DATABASE_URL", ""),
    smtp_host=os.environ.get("SMTP_HOST", ""),
    smtp_port=int(os.environ.get("SMTP_PORT", "587")),
    smtp_username=os.environ.get("SMTP_USERNAME", ""),
    smtp_password=os.environ.get("SMTP_PASSWORD", ""),
    smtp_from=os.environ.get("SMTP_FROM", ""),
    alert_email=os.environ.get("ALERT_EMAIL", ""),
    log_level=p_log_level,
    timeout_multiplier=p_timeout_mult,
    dry_run=p_dry_run,
    strict_validation=p_strict
)

