"""
Neden: app.core.config'in env çevirim davranışını sabitlemek (smoke).
`settings` import anında kurulan frozen singleton olduğundan, env senaryoları
importlib.reload ile kontrollü ortamda yeniden kurularak test edilir.
Reload sırasında Path.exists monkeypatch'lenir (False döner) — load_dotenv
gerçek .env dosyasını hiç okumaz; testler tamamen sentetik env ile çalışır.
Teardown'da env geri alınıp modül tekrar reload edilir, orijinal ayarlar döner.
"""
import dataclasses
import importlib
from pathlib import Path

import pytest

import app.core.config as cfg

# İlk import'ta .env'den os.environ'a yüklenmiş olabilecek, testlerin kontrol
# etmek istediği anahtarlar — her reload öncesi temizlenir.
SMTP_KEYS = [
    "SMTP_TO", "ALERT_EMAIL", "SMTP_TO_DAILY", "SMTP_TO_MONTHLY",
    "SMTP_TO_PLANT_ALERT", "SMTP_TO_SYSTEM", "SMTP_PORT", "SMTP_USE_TLS",
    "DASHBOARD_PORT", "APP_ENV", "ISOLAR_HEADLESS",
    "ISOLAR_USERNAME", "ISOLAR_PASSWORD",
]


@pytest.fixture
def reload_config(monkeypatch):
    """Verilen env ile config modülünü yeniden kurar; test sonunda eski hale döndürür."""

    def _reload(**env):
        for key in SMTP_KEYS:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        # load_dotenv gerçek .env'i okumasın: reload süresince exists() False döner.
        monkeypatch.setattr(Path, "exists", lambda self: False)
        return importlib.reload(cfg)

    yield _reload
    monkeypatch.undo()
    importlib.reload(cfg)


@pytest.mark.parametrize(
    "ozel_anahtar,alan",
    [
        ("SMTP_TO_DAILY", "smtp_to_daily"),
        ("SMTP_TO_MONTHLY", "smtp_to_monthly"),
        ("SMTP_TO_PLANT_ALERT", "smtp_to_plant_alert"),
        ("SMTP_TO_SYSTEM", "smtp_to_system"),
    ],
)
def test_smtp_to_spesifik_oncelikli(reload_config, ozel_anahtar, alan):
    modul = reload_config(SMTP_TO="genel@test.local", **{ozel_anahtar: "ozel@test.local"})
    assert getattr(modul.settings, alan) == "ozel@test.local"


def test_smtp_to_fallback(reload_config):
    modul = reload_config(SMTP_TO="genel@test.local")
    assert modul.settings.smtp_to_daily == "genel@test.local"
    assert modul.settings.smtp_to_monthly == "genel@test.local"
    assert modul.settings.smtp_to_plant_alert == "genel@test.local"
    assert modul.settings.smtp_to_system == "genel@test.local"
    assert modul.settings.alert_email == "genel@test.local"


def test_bool_cevirimleri(reload_config):
    modul = reload_config(SMTP_ENABLED="True", SMTP_USE_TLS="FALSE", ISOLAR_HEADLESS="TRUE")
    assert modul.settings.smtp_enabled is True
    assert modul.settings.smtp_use_tls is False
    assert modul.settings.headless is True

    # "true" dışındaki her değer False sayılır (örn. "yes", "1")
    modul = reload_config(SMTP_ENABLED="yes", SMTP_USE_TLS="1")
    assert modul.settings.smtp_enabled is False
    assert modul.settings.smtp_use_tls is False


def test_int_cevirimleri_ve_varsayilanlar(reload_config):
    modul = reload_config(SMTP_PORT="465", DASHBOARD_PORT="9090")
    assert modul.settings.smtp_port == 465
    assert modul.settings.dashboard_port == 9090

    # Anahtarlar yokken varsayılanlar
    modul = reload_config()
    assert modul.settings.smtp_port == 587
    assert modul.settings.dashboard_port == 8080


def test_gecersiz_app_env_development_profili(reload_config):
    modul = reload_config(APP_ENV="sacma_deger")
    assert modul.settings.app_env == "development"
    assert modul.settings.dry_run is True
    assert modul.settings.log_level == "DEBUG"
    assert modul.settings.timeout_multiplier == 1.0
    assert modul.settings.strict_validation is False


def test_validate_eksik_degisken_hatasi(reload_config):
    modul = reload_config(ISOLAR_USERNAME="", ISOLAR_PASSWORD="")
    with pytest.raises(ValueError) as excinfo:
        modul.settings.validate()
    assert "ISOLAR_USERNAME" in str(excinfo.value)
    assert "ISOLAR_PASSWORD" in str(excinfo.value)


def test_settings_immutable(reload_config):
    modul = reload_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        modul.settings.smtp_host = "degistirilemez.local"
