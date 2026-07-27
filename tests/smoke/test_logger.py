"""
Neden: Log rotasyonundaki sessiz kayıt kaybını (2026-07-27) regresyona karşı
sabitlemek. İki garanti test edilir:
  1. Rotasyon başarısız olsa bile kayıt YAZILIR (veri kaybı yok).
  2. Başarısız deneme yedek dosyaları (app.log.1..5) bozmaz.
Ayrıca process bazlı dosya ayrımının (dashboard.log / app.log) doğru çözüldüğü.
"""
import logging
import os

import pytest

from app.core.logger import (
    DASHBOARD_LOG_FILE,
    DEFAULT_LOG_FILE,
    ResilientRotatingFileHandler,
    resolve_log_file_name,
)


def _handler(path, **kwargs):
    h = ResilientRotatingFileHandler(path, encoding="utf-8", maxBytes=200, backupCount=3, **kwargs)
    h.setFormatter(logging.Formatter("%(message)s"))
    return h


def _record(msg):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


# ----------------------------------------------------------------------
# 1. Dosya adı çözümlemesi (process bazlı)
# ----------------------------------------------------------------------
def test_default_process_writes_to_app_log(monkeypatch):
    monkeypatch.delenv("LOG_FILE_NAME", raising=False)
    monkeypatch.setattr("sys.orig_argv", ["python.exe", "main.py", "--health"])
    monkeypatch.setattr("sys.argv", ["main.py"])
    assert resolve_log_file_name() == DEFAULT_LOG_FILE


def test_dashboard_module_run_writes_to_dashboard_log(monkeypatch):
    """
    Neden (regresyon): `python -m app.dashboard.web_server` çalıştırıldığında
    logger, app/dashboard/__init__.py import edilirken kurulur — runpy henüz
    sys.argv[0]'ı yazmamıştır. Bu senaryoda argv[0] hâlâ eski değerdedir ve
    yalnızca ona bakan bir çözümleme dashboard'ı app.log'a yazardı.
    """
    monkeypatch.delenv("LOG_FILE_NAME", raising=False)
    monkeypatch.setattr("sys.orig_argv", ["python.exe", "-m", "app.dashboard.web_server"])
    monkeypatch.setattr("sys.argv", ["-m"])  # runpy henüz yazmadı
    assert resolve_log_file_name() == DASHBOARD_LOG_FILE


def test_dashboard_script_run_writes_to_dashboard_log(monkeypatch):
    # Doğrudan dosya yolu ile çalıştırma da tanınmalı
    monkeypatch.delenv("LOG_FILE_NAME", raising=False)
    monkeypatch.setattr("sys.orig_argv", ["python.exe", r"C:\proj\app\dashboard\web_server.py"])
    monkeypatch.setattr("sys.argv", [r"C:\proj\app\dashboard\web_server.py"])
    assert resolve_log_file_name() == DASHBOARD_LOG_FILE


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("LOG_FILE_NAME", "ozel.log")
    monkeypatch.setattr("sys.orig_argv", ["python.exe", "-m", "app.dashboard.web_server"])
    assert resolve_log_file_name() == "ozel.log"


def test_empty_argv_falls_back_to_app_log(monkeypatch):
    monkeypatch.delenv("LOG_FILE_NAME", raising=False)
    monkeypatch.setattr("sys.orig_argv", [])
    monkeypatch.setattr("sys.argv", [])
    assert resolve_log_file_name() == DEFAULT_LOG_FILE


# ----------------------------------------------------------------------
# 2. Normal rotasyon bozulmadı
# ----------------------------------------------------------------------
def test_rotation_still_works_when_file_is_free(tmp_path):
    log = tmp_path / "app.log"
    h = _handler(log)
    try:
        for i in range(40):
            h.emit(_record(f"satir-{i:03d} " + "x" * 20))
        h.flush()
    finally:
        h.close()

    assert log.exists()
    assert (tmp_path / "app.log.1").exists(), "dosya serbestken rotasyon çalışmalı"


# ----------------------------------------------------------------------
# 3. Rotasyon engelliyken kayıt KAYBOLMAZ
# ----------------------------------------------------------------------
def test_record_is_written_even_when_rotation_blocked(tmp_path, monkeypatch):
    log = tmp_path / "app.log"
    h = _handler(log)
    try:
        h.emit(_record("ilk kayit " + "x" * 200))  # sınırı aş
        h.flush()

        # Neden: Başka bir process dosyayı açık tutuyormuş gibi rename'i engelle.
        monkeypatch.setattr(
            ResilientRotatingFileHandler, "_rename_available", lambda self: False
        )
        h.emit(_record("ROTASYON-ENGELLIYKEN-YAZILAN"))
        h.flush()
    finally:
        h.close()

    content = log.read_text(encoding="utf-8")
    assert "ROTASYON-ENGELLIYKEN-YAZILAN" in content, "engelli rotasyonda kayıt kaybolmamalı"


def test_blocked_rotation_does_not_destroy_backups(tmp_path, monkeypatch):
    """
    Neden: Standart doRollover, asıl rename'den ÖNCE yedekleri kaydırır ve
    .1'i siler. Ön kontrol olmasaydı her başarısız deneme bir yedeği yok ederdi.
    """
    log = tmp_path / "app.log"
    backup = tmp_path / "app.log.1"
    backup.write_text("ONEMLI-ESKI-KAYIT", encoding="utf-8")

    h = _handler(log)
    try:
        h.emit(_record("dolgu " + "x" * 200))
        h.flush()
        monkeypatch.setattr(
            ResilientRotatingFileHandler, "_rename_available", lambda self: False
        )
        for i in range(6):  # backupCount'tan fazla deneme
            h.emit(_record(f"engelli-{i}"))
        h.flush()
    finally:
        h.close()

    assert backup.exists(), "başarısız rotasyon denemesi yedeği silmemeli"
    assert backup.read_text(encoding="utf-8") == "ONEMLI-ESKI-KAYIT"


def test_handler_error_is_not_triggered_when_blocked(tmp_path, monkeypatch):
    # Neden: handleError'a düşmek = kaydın yazılmaması. Hiç çağrılmamalı.
    log = tmp_path / "app.log"
    h = _handler(log)
    calls = []
    monkeypatch.setattr(type(h), "handleError", lambda self, record: calls.append(record))
    try:
        h.emit(_record("dolgu " + "x" * 200))
        monkeypatch.setattr(
            ResilientRotatingFileHandler, "_rename_available", lambda self: False
        )
        h.emit(_record("ikinci"))
        h.flush()
    finally:
        h.close()

    assert calls == [], "engelli rotasyonda handleError çağrılmamalı"


# ----------------------------------------------------------------------
# 4. Ön kontrolün kendisi yan etki bırakmaz
# ----------------------------------------------------------------------
def test_rename_probe_leaves_no_residue(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("veri", encoding="utf-8")
    h = _handler(log, delay=True)
    try:
        assert h._rename_available() is True
    finally:
        h.close()

    assert log.exists() and log.read_text(encoding="utf-8") == "veri"
    assert not (tmp_path / "app.log.rotcheck").exists()


def test_rename_probe_returns_false_for_missing_file(tmp_path):
    h = _handler(tmp_path / "app.log", delay=True)
    try:
        os.remove(h.baseFilename) if os.path.exists(h.baseFilename) else None
        assert h._rename_available() is False
    finally:
        h.close()


@pytest.mark.parametrize("blocked", [True, False])
def test_stream_is_usable_after_rollover_attempt(tmp_path, monkeypatch, blocked):
    log = tmp_path / "app.log"
    h = _handler(log)
    try:
        if blocked:
            monkeypatch.setattr(
                ResilientRotatingFileHandler, "_rename_available", lambda self: False
            )
        h.emit(_record("dolgu " + "x" * 200))
        h.emit(_record("SONRAKI-KAYIT"))
        h.flush()
        assert h.stream is not None and not h.stream.closed
    finally:
        h.close()

    written = log.read_text(encoding="utf-8")
    assert "SONRAKI-KAYIT" in written
