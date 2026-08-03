"""
Neden: Arıza bildirimleri (FAILED, CAPTCHA_REQUIRED) 2026-08-03'e kadar başarı raporuyla
AYNI listeye gidiyordu (SMTP_TO_DAILY / SMTP_TO_MONTHLY). Yönetici her hatanın teknik
dökümünü alıyor, müdahale edecek teknik ekip ise ayrı kanaldaydı.

Yönlendirme artık şöyle:
    SUCCESS           -> daily / monthly profili  (rapor alıcıları — DEĞİŞMEDİ)
    FAILED            -> system profili           (SMTP_TO_SYSTEM)
    CAPTCHA_REQUIRED  -> system profili           (SMTP_TO_SYSTEM)

Bu testler iki katmanı birden sabitler:
1. İşlerin hangi profili geçtiği (asıl değişiklik burada — AST ile okunur, metin
   eşleştirme kırılganlığı olmadan).
2. Profilden alıcıya çözümleme (SMTP'ye çıkmadan, sahte sunucuyla).
"""
import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

JOBS = {
    "daily": PROJECT_ROOT / "app" / "jobs" / "daily_settlement_job.py",
    "monthly": PROJECT_ROOT / "app" / "jobs" / "monthly_settlement_job.py",
}


def _notify_calls(path: Path):
    """
    notify_pipeline çağrılarını (event_type, email_profile) olarak döndürür.

    Neden AST: Kaynakta düz metin aramak biçim değişikliğinde (satır kaydırma, tırnak
    tipi) sessizce yanlış sonuç verir. AST, argümanın gerçekten o çağrıya ait olduğunu
    garanti eder. event_type verilmemişse None döner — o dal exit_code'dan türetilen
    başarısızlık dalıdır.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "notify_pipeline":
            continue
        kw = {k.arg: k.value for k in node.keywords}

        def literal(key):
            v = kw.get(key)
            return v.value if isinstance(v, ast.Constant) else None

        calls.append((literal("event_type"), literal("email_profile")))
    return calls


@pytest.mark.parametrize("job", ["daily", "monthly"])
def test_success_maili_rapor_alicilarina_gider(job):
    """Başarı raporu iş biriminin işine yarar; alıcısı DEĞİŞMEMELİ."""
    success = [p for et, p in _notify_calls(JOBS[job]) if et == "SUCCESS"]

    assert success, f"{job} işinde SUCCESS bildirimi bulunamadı"
    assert all(p == job for p in success), (
        f"{job} SUCCESS maili '{job}' profilinde kalmalı, bulunan: {success}"
    )


@pytest.mark.parametrize("job", ["daily", "monthly"])
def test_captcha_maili_teknik_ekibe_gider(job):
    """CAPTCHA_REQUIRED bir arıza bildirimidir; teknik ekibe gitmeli."""
    captcha = [p for et, p in _notify_calls(JOBS[job]) if et == "CAPTCHA_REQUIRED"]

    assert captcha, f"{job} işinde CAPTCHA_REQUIRED bildirimi bulunamadı"
    assert all(p == "system" for p in captcha), (
        f"CAPTCHA_REQUIRED 'system' profilinde olmalı, bulunan: {captcha}"
    )


@pytest.mark.parametrize("job", ["daily", "monthly"])
def test_basarisizlik_maili_rapor_alicilarina_gitmez(job):
    """
    event_type verilmeyen çağrı, exit_code'dan türetilen başarısızlık dalıdır.
    Rapor alıcılarına (daily/monthly) düşmemeli.
    """
    failures = [p for et, p in _notify_calls(JOBS[job]) if et is None]

    assert failures, f"{job} işinde başarısızlık bildirimi bulunamadı"
    assert all(p == "system" for p in failures), (
        f"Başarısızlık maili 'system' profilinde olmalı, bulunan: {failures}"
    )
    assert job not in failures, (
        f"Başarısızlık maili hâlâ rapor alıcılarına ('{job}') gidiyor"
    )


# --- Profilden alıcıya çözümleme (SMTP'ye çıkmadan) ---

class _FakeSMTP:
    """send_message'a düşen mesajı yakalar; ağa çıkmaz."""
    captured = []

    def __init__(self, *_a, **_kw):
        pass

    def ehlo(self):
        pass

    def has_extn(self, _name):
        return False

    def login(self, *_a):
        pass

    def send_message(self, msg):
        _FakeSMTP.captured.append(msg)

    def quit(self):
        pass


def _patch_settings(monkeypatch, mod, **overrides):
    """
    Neden: Settings frozen bir dataclass — alan ataması FrozenInstanceError verir.
    dataclasses.replace yeni bir örnek üretir, modüldeki referans onunla değiştirilir.
    Gerçek .env değerleri (ve içindeki kimlik bilgileri) teste hiç sızmaz.
    """
    import dataclasses

    base = dict(
        smtp_enabled=True, smtp_host="smtp.test", smtp_port=587,
        smtp_username="", smtp_password="", smtp_from="from@test",
        smtp_use_tls=False, alert_email="default@test",
    )
    base.update(overrides)
    monkeypatch.setattr(mod, "settings", dataclasses.replace(mod.settings, **base))
    monkeypatch.setattr(mod.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.captured = []


def _event(event_type="SUCCESS", exit_code=0):
    from app.notifications.notification_models import NotificationEvent
    return NotificationEvent(
        run_id="r1", event_type=event_type, exit_code=exit_code, duration_ms=1,
        machine_name="T", git_commit="c", stage_summary="s",
    )


@pytest.mark.parametrize("profile,expected", [
    ("daily", "daily@test"),
    ("monthly", "monthly@test"),
    ("system", "system@test"),
])
def test_profil_dogru_aliciya_cozumlenir(profile, expected, monkeypatch):
    from app.notifications import email_sender as mod

    _patch_settings(
        monkeypatch, mod,
        smtp_to_daily="daily@test", smtp_to_monthly="monthly@test",
        smtp_to_system="system@test",
    )

    ok, _attempts, _err = mod.EmailSender().send(_event(), email_profile=profile)

    assert ok, "sahte SMTP ile gönderim başarılı sayılmalı"
    assert _FakeSMTP.captured[-1]["To"] == expected


def test_system_profili_yonetici_listesinden_ayridir(monkeypatch):
    """
    Asıl güvence: 'system' profili, rapor alıcı listelerinden BAĞIMSIZ bir değişken
    okur. Aynı değişkene bağlansaydı yönlendirme değişikliği hiçbir şey çözmezdi.
    """
    from app.notifications import email_sender as mod

    _patch_settings(
        monkeypatch, mod,
        smtp_to_daily="yonetici@firma,teknik@firma",
        smtp_to_system="teknik@firma",
    )

    mod.EmailSender().send(_event("FAILED", 1), email_profile="system")

    to = _FakeSMTP.captured[-1]["To"]
    assert "yonetici@firma" not in to
    assert to == "teknik@firma"
