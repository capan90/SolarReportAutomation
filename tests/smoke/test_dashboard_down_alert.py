"""
Neden: Dashboard kapalı-kalma uyarı zincirini sabitlemek (smoke):
(1) sunucu portu paylaşımsız bağlar — ikinci instance sessizce yanaşamaz
    (2026-07-21 çift dinleyici olayı),
(2) VBS başlatıcı pes ettiğinde uyarı scriptini çağırır,
(3) uyarı e-postasının konu/gövdesi marka standardına uyar.
Gönderim testi yapılmaz — build_* fonksiyonları saf metin üretir, ağsız çalışır.
"""
import importlib.util
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALERT_SCRIPT = PROJECT_ROOT / "scripts" / "send_dashboard_down_alert.py"
VBS_LAUNCHER = PROJECT_ROOT / "scripts" / "run_dashboard_hidden.vbs"

_spec = importlib.util.spec_from_file_location("send_dashboard_down_alert", ALERT_SCRIPT)
alert_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alert_mod)


def test_sunucu_portu_paylasimsiz_baglar():
    from app.dashboard.web_server import _ExclusiveHTTPServer

    assert _ExclusiveHTTPServer.allow_reuse_address is False


def test_vbs_pes_ederken_uyari_scriptini_cagirir():
    icerik = VBS_LAUNCHER.read_text(encoding="utf-8")
    assert "send_dashboard_down_alert.py" in icerik
    assert "attempts > 3" in icerik


def test_uyari_konusu_marka_standardina_uyar():
    now = datetime(2026, 7, 21, 16, 30)
    konu = alert_mod.build_subject(now)
    assert konu.startswith("🔴 Erdemsoft GES — Dashboard Kapalı")
    assert "21.07.2026 16:30" in konu
    assert len(konu) <= 60


def test_uyari_govdesi_aksiyon_icerir():
    now = datetime(2026, 7, 21, 16, 30)
    govde = alert_mod.build_body(now, "APPS")
    assert "APPS" in govde
    assert "Start-ScheduledTask SolarReportAutomation_Dashboard" in govde
    assert "otomatik olarak oluşturulmuştur" in govde


def test_uyari_govdesi_log_kuyrugu_icerir_ve_escape_eder():
    now = datetime(2026, 7, 21, 16, 30)
    govde = alert_mod.build_body(now, "APPS", log_tail="[ERROR] port <8081> kullanımda")
    assert "Son log kayıtları" in govde
    assert "&lt;8081&gt;" in govde  # HTML injection'a karşı escape


def test_log_kuyrugu_gercek_logdan_okunur():
    kuyruk = alert_mod.collect_log_tail(lines=5)
    # Dev ortamında logs/ dolu — içerik gelmeli; boş ortamda da crash değil açıklama döner
    assert isinstance(kuyruk, str) and len(kuyruk) > 0


def test_ayarlar_sayfasi_kilitli():
    icerik = (PROJECT_ROOT / "app" / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="settings-lock-view"' in icerik
    assert 'id="settings-content" style="display:none;"' in icerik
    # Kilit kontrolü loadSettingsPage'in ilk işi olmalı
    assert 'if (!_devToken) { showSettingsLockView(); return; }' in icerik
    # Çıkışta dev token düşürülüp ana sayfaya dönülmeli (oturum mirası engeli)
    logout_govde = icerik.split("async function logout()")[1][:600]
    assert "devLogout();" in logout_govde
    assert "goToHomePage();" in logout_govde
