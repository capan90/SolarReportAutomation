"""
Neden: "Kaydet ve Yeniden Başlat" akışının güvenlik ağı — gerçek restart
tetiklemeden (timer mock'lanarak / iptal edilerek) şu davranışları sabitler:
- _schedule_restart doğru exit kodu ve daemon timer ile kurulur.
- /api/settings/restart yanlış yönetici şifresini reddeder, audit'e "denied" yazar.
- Doğru şifrede restart planlanır, audit'e "dashboard_restart" yazar.
- DASHBOARD_ADMIN_PASSWORD tanımsızken boş şifreyle bile restart yapılamaz.
"""
import os

from app.dashboard import web_server


class _StubAuth:
    """Neden: Gerçek DB'ye audit yazmadan log_action çağrılarını kaydetmek."""

    def __init__(self):
        self.actions = []

    def log_action(self, username, ip, action, details=None):
        self.actions.append((username, action, details))


def _make_handler(body, monkeypatch, schedule_calls):
    """Neden: Socket kurmadan sadece _handle_restart mantığını test etmek."""
    handler = object.__new__(web_server.DashboardRequestHandler)
    handler.auth = _StubAuth()
    handler._read_json_body = lambda: body
    handler._get_client_ip = lambda: "127.0.0.1"
    handler.responses = []
    handler._send_json_contract = (
        lambda data, error, status_code=200: handler.responses.append((data, error, status_code))
    )
    monkeypatch.setattr(web_server, "_schedule_restart", lambda: schedule_calls.append(True))
    return handler


def test_schedule_restart_timer_yapisi():
    """Timer daemon olmalı, os._exit'i RESTART_EXIT_CODE ile çağırmalı."""
    timer = web_server._schedule_restart(delay_seconds=60)
    try:
        assert timer.daemon is True
        assert timer.function is os._exit
        assert timer.args == (web_server.RESTART_EXIT_CODE,)
        assert web_server.RESTART_EXIT_CODE != 0  # 0, VBS döngüsünde temiz kapanış sayılır — restart tetiklemez
    finally:
        timer.cancel()  # Gerçek restart asla tetiklenmemeli


def test_restart_yanlis_sifre_reddedilir(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ADMIN_PASSWORD", "dogru-sifre")
    calls = []
    handler = _make_handler({"admin_password": "yanlis"}, monkeypatch, calls)

    handler._handle_restart("test_admin")

    assert calls == [], "Yanlış şifrede restart planlanmamalı"
    data, error, _ = handler.responses[0]
    assert data is None and error == "Yönetici şifresi hatalı."
    assert ("test_admin", "dashboard_restart_denied", "Yönetici şifresi hatalı") in handler.auth.actions


def test_restart_dogru_sifre_planlanir(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ADMIN_PASSWORD", "dogru-sifre")
    calls = []
    handler = _make_handler({"admin_password": "dogru-sifre"}, monkeypatch, calls)

    handler._handle_restart("test_admin")

    assert calls == [True], "Doğru şifrede restart tam bir kez planlanmalı"
    data, error, _ = handler.responses[0]
    assert error is None and data["restarting"] is True
    actions = [a for (_, a, _) in handler.auth.actions]
    assert "dashboard_restart" in actions and "dashboard_restart_denied" not in actions


def test_restart_admin_sifresi_tanimsizken_kapali(monkeypatch):
    """DASHBOARD_ADMIN_PASSWORD boşsa boş şifre eşleşmesi bile kabul edilmemeli."""
    monkeypatch.setenv("DASHBOARD_ADMIN_PASSWORD", "")
    calls = []
    handler = _make_handler({"admin_password": ""}, monkeypatch, calls)

    handler._handle_restart("test_admin")

    assert calls == []
    data, error, _ = handler.responses[0]
    assert data is None and error == "Yönetici şifresi hatalı."
