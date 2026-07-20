"""
Neden: EmailSender'ın konu/gövde üretim davranışını sabitlemek (smoke).
scratch/verify_email_redesign.py'deki manuel kontrollerin pytest'e taşınmış hali.
SMTP'ye asla bağlanılmaz: render/subject saf fonksiyonlardır, gönderim testi ise
conftest'in zorladığı SMTP_ENABLED=false kapısının çalıştığını doğrular.
"""
import datetime

import pytest

from app.notifications.email_sender import AY_ADLARI, EmailSender
from app.notifications.notification_models import NotificationEvent

BUGUN = datetime.date.today().strftime("%d.%m.%Y")

PLACEHOLDERS = [
    "$STAGE_SUMMARY", "$TECH_DETAILS", "$REPORT_TITLE", "$PERIOD_LABEL",
    "$REPORT_PERIOD", "$REPORT_KIND", "$ATTACHMENT_NOTE", "$ERROR_SUMMARY",
    "$VALIDATION_SUMMARY", "$DASHBOARD_URL",
]

DAILY_SUMMARY = (
    "20 Temmuz 2026 tarihine ait günlük mahsuplaşma raporu otomatik olarak hazırlanmıştır.\n\n"
    "Toplam Üretim: 12.345,6 kWh\n"
    "Toplam Tüketim: 8.901,2 kWh\n"
    "Toplam Mahsup: 7.500,0 kWh\n"
    "Şebekeden Çekiş: 1.401,2 kWh\n"
    "Fazla Satış: 4.845,6 kWh"
)


def make_event(event_type, attachment=None, stage_summary="", validation_summary=None):
    return NotificationEvent(
        run_id="test-run-id-1234",
        event_type=event_type,
        exit_code=0 if event_type == "SUCCESS" else 1,
        duration_ms=45210,
        machine_name="TEST-SRV",
        git_commit="abc1234",
        stage_summary=stage_summary,
        validation_summary=validation_summary,
        attachment_path=attachment,
    )


@pytest.fixture
def sender():
    return EmailSender()


def test_gunluk_konu_formati(sender):
    event = make_event("SUCCESS", "outputs/reports/mahsup_20260720.xlsx")
    assert sender._build_subject(event, "daily") == (
        "✅ Erdemsoft GES — Günlük Mahsuplaşma Raporu (20.07.2026)"
    )


def test_aylik_konu_ay_adi_icerir(sender):
    event = make_event("SUCCESS", "outputs/reports/mahsup_202607_aylik.xlsx")
    subject = sender._build_subject(event, "monthly")
    assert "Aylık" in subject
    assert "Temmuz 2026" in subject


@pytest.mark.parametrize("ay", range(1, 13))
def test_aylik_donem_yyyymm_cozumu(sender, ay):
    event = make_event("SUCCESS", f"outputs/reports/mahsup_2025{ay:02d}_aylik.xlsx")
    assert sender._extract_report_month(event) == f"{AY_ADLARI[ay - 1]} 2025"


@pytest.mark.parametrize("event_type", ["FAILED", "LOGIN_FAILED", "DOWNLOAD_FAILED", "VALIDATION_FAILED"])
def test_hata_tipleri_tek_konu_formatina_iner(sender, event_type):
    subject = sender._build_subject(make_event(event_type), "daily")
    assert subject == f"❌ Erdemsoft GES — Rapor Oluşturulamadı ({BUGUN})"


def test_captcha_konu(sender):
    subject = sender._build_subject(make_event("CAPTCHA_REQUIRED"), "system")
    assert subject == f"🔐 Erdemsoft GES — Doğrulama Gerekiyor ({BUGUN})"


@pytest.mark.parametrize("ay", range(1, 13))
def test_konu_60_karakteri_asmaz_tum_aylar(sender, ay):
    # En uzun senaryo aylık başarı konusudur; 12 ayın tamamı sınanır.
    event = make_event("SUCCESS", f"outputs/reports/mahsup_2026{ay:02d}_aylik.xlsx")
    assert len(sender._build_subject(event, "monthly")) <= 60


@pytest.mark.parametrize(
    "event_type,profile",
    [("SUCCESS", "daily"), ("SUCCESS", "monthly"), ("FAILED", "daily"),
     ("CAPTCHA_REQUIRED", "system"), ("VALIDATION_FAILED", "default")],
)
def test_govde_placeholder_birakmaz(sender, event_type, profile):
    event = make_event(event_type, stage_summary=DAILY_SUMMARY, validation_summary="test uyarısı")
    body = sender.render_body(event, email_profile=profile)
    kalan = [p for p in PLACEHOLDERS if p in body]
    assert not kalan, f"Doldurulmayan placeholder: {kalan}"


@pytest.mark.parametrize(
    "event_type,profile",
    [("SUCCESS", "daily"), ("FAILED", "daily"), ("CAPTCHA_REQUIRED", "system"), ("VALIDATION_FAILED", "default")],
)
def test_footer_tekil_marka_metni(sender, event_type, profile):
    body = sender.render_body(make_event(event_type), email_profile=profile)
    assert "Erdemsoft GES Yönetim Sistemi tarafından otomatik olarak oluşturulmuştur" in body
    assert "SolarReportAutomation sistemi" not in body
    assert "GES Enerji Yönetim Sistemi" not in body


def test_istatistik_tablosu_render(sender):
    event = make_event("SUCCESS", "outputs/reports/mahsup_20260720.xlsx", DAILY_SUMMARY)
    body = sender.render_body(event, email_profile="daily")
    assert "#f1f8e9" in body  # açık yeşil arkaplan bloğu
    assert "font-weight: bold" in body  # kalın etiketler
    for etiket in ["Toplam Üretim", "Toplam Tüketim", "Toplam Mahsup", "Şebekeden Çekiş", "Fazla Satış"]:
        assert etiket in body
    assert "12.345,6 kWh" in body
    # Giriş cümlesi tablo dışında paragraf olarak kalmalı
    assert "hazırlanmıştır" in body


def test_teknik_detaylar_govdede(sender):
    body = sender.render_body(make_event("SUCCESS"), email_profile="daily")
    assert "Teknik Detaylar" in body
    assert "test-run-id-1234" in body
    assert "TEST-SRV" in body
    assert "abc1234" in body


def test_aylik_govde_baslik_ve_donem(sender):
    event = make_event("SUCCESS", "outputs/reports/mahsup_202607_aylik.xlsx", DAILY_SUMMARY)
    body = sender.render_body(event, email_profile="monthly")
    assert "Aylık Mahsuplaşma Raporu Hazır" in body
    assert "Dönem" in body
    assert "Temmuz 2026" in body
    assert "Aylık mahsuplaşma raporu ekte sunulmaktadır" in body


def test_gunluk_govde_baslik_ve_tarih(sender):
    event = make_event("SUCCESS", "outputs/reports/mahsup_20260720.xlsx", DAILY_SUMMARY)
    body = sender.render_body(event, email_profile="daily")
    assert "Günlük Mahsuplaşma Raporu Hazır" in body
    assert "20.07.2026" in body
    assert "Günlük mahsuplaşma raporu ekte sunulmaktadır" in body


@pytest.mark.parametrize(
    "event_type,summary,beklenen",
    [
        ("FAILED", "GAOSB raporu indirme aşaması başarısız", "GAOSB portalından rapor alınamadı"),
        ("FAILED", "iSolar Curve indirme aşaması başarısız", "iSolar portalından üretim verisi alınamadı"),
        ("LOGIN_FAILED", "login timeout", "Portala giriş yapılamadı"),
        ("DOWNLOAD_FAILED", "timeout", "Rapor dosyası indirilemedi"),
        ("DATABASE_FAILED", "db locked", "Veriler veritabanına kaydedilemedi"),
        ("FAILED", "bilinmeyen", "Veri işleme sırasında hata oluştu"),
    ],
)
def test_hata_ozeti_insan_dili(sender, event_type, summary, beklenen):
    event = make_event(event_type, stage_summary=summary)
    assert beklenen in sender._friendly_error_summary(event)


def test_smtp_kapali_gonderim_engellenir(sender):
    # conftest SMTP_ENABLED=false zorlar; send() ağa çıkmadan reddetmelidir.
    success, attempts, err = sender.send(make_event("SUCCESS"), email_profile="daily")
    assert success is False
    assert attempts == 0
    assert "SMTP_ENABLED" in err
