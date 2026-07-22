"""
Neden: S2 dayanıklılık garantilerini sabitlemek (smoke):
(1) zamanlanmış işlerin çıktı yolları cwd'den bağımsız (System32 hata sınıfı),
(2) sessiz ölüm uyarısının konu/gövdesi marka standardına uygun ve escape'li,
(3) main.py except yolları uyarıyı çağırıyor,
(4) GES durum maili geçici hatada yeniden deniyor.
Tümü ağsız çalışır (smtplib monkeypatch / saf metin üretimi).
"""
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_job_cikti_yollari_mutlak():
    from app.jobs import daily_settlement_job, monthly_settlement_job
    from app.extractors.isolar import extractor as isolar_extractor

    assert daily_settlement_job.PROJECT_ROOT == PROJECT_ROOT
    assert monthly_settlement_job.PROJECT_ROOT == PROJECT_ROOT
    assert isolar_extractor.PROJECT_ROOT == PROJECT_ROOT
    # Göreli Path("outputs/...") kalıbı job'lara geri dönmesin
    for mod_path in ("app/jobs/daily_settlement_job.py", "app/jobs/monthly_settlement_job.py"):
        icerik = (PROJECT_ROOT / mod_path).read_text(encoding="utf-8")
        assert 'Path("outputs' not in icerik


def test_uyari_konusu_marka_standardina_uyar():
    from app.notifications.system_alert import build_subject

    konu = build_subject("Günlük Mahsup", datetime(2026, 7, 22, 9, 0))
    assert konu.startswith("🔴 Erdemsoft GES — Günlük Mahsup Başarısız")
    assert "22.07.2026 09:00" in konu
    assert len(konu) <= 60


def test_uyari_govdesi_hata_ve_log_icerir():
    from app.notifications.system_alert import build_body

    govde = build_body(
        "Günlük Mahsup İşi",
        "[WinError 5] Access is denied: '<outputs>'",
        datetime(2026, 7, 22, 9, 0),
        log_tail="[ERROR] deneme <satiri>",
    )
    assert "Günlük Mahsup İşi" in govde
    assert "&lt;outputs&gt;" in govde  # hata metni escape'li
    assert "Son log kayıtları" in govde
    assert "&lt;satiri&gt;" in govde
    assert "otomatik olarak oluşturulmuştur" in govde


def test_main_except_yollari_uyari_cagiriyor():
    icerik = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert icerik.count("send_job_failure_alert") >= 2  # günlük + aylık dalları


def test_ges_durum_maili_gecici_hatada_yeniden_dener(monkeypatch):
    from types import SimpleNamespace

    from app.jobs import plant_status_job

    # Gerçek .env/ortamdan bağımsız, SMTP açık sentetik ayar
    monkeypatch.setattr(plant_status_job, "settings", SimpleNamespace(
        smtp_enabled=True, smtp_host="smtp.test.local", smtp_port=587,
        smtp_username="u@test.local", smtp_password="pw",  # kisa: pre-commit secret desenine takilmasin
        smtp_from="u@test.local", smtp_to_plant_alert="alici@test.local",
        smtp_use_tls=True,
    ))

    denemeler = []

    class SahteSMTP:
        def __init__(self, *a, **k):
            denemeler.append(1)
            if len(denemeler) < 2:
                raise ConnectionError("getaddrinfo failed (sentetik)")

        def ehlo(self):
            pass

        def has_extn(self, name):
            return False

        def login(self, u, p):
            pass

        def send_message(self, msg):
            pass

        def quit(self):
            pass

    monkeypatch.setattr(plant_status_job.smtplib, "SMTP", SahteSMTP)
    monkeypatch.setattr(plant_status_job.smtplib, "SMTP_SSL", SahteSMTP)
    monkeypatch.setattr(plant_status_job.time, "sleep", lambda s: None)

    sonuc = plant_status_job.send_status_email("Test", "<p>t</p>")
    # settings.smtp_enabled dev .env'de true; ilk deneme düşer, ikincisi başarır
    assert sonuc is True
    assert len(denemeler) == 2
