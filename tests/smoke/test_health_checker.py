"""
Neden: HealthChecker orkestrasyonunu sabitlemek (smoke): durum birleştirme
(severity → overall), timeout koruması ve rapor yazımı.
Ağa çıkan kontroller (SMTP/portal/Playwright) sahte IHealthCheck nesneleriyle
temsil edilir; yalnızca FilesystemCheck gerçek koşulur (yerel disk, ağsız).
Rapor yazımı BASE_DIR monkeypatch'i ile tmp_path'e yönlendirilir.
"""
import time

import pytest

from app.monitoring.health.checks.filesystem_check import FilesystemCheck
from app.monitoring.health.health_checker import HealthChecker
from app.monitoring.health.interface import HealthCheckResult, IHealthCheck


class FakeCheck(IHealthCheck):
    """SMTP/portal/browser gibi dışa bağımlı kontrollerin ağsız temsilcisi."""

    def __init__(self, name="Fake Check", status="SUCCESS", severity="CRITICAL",
                 timeout=5.0, delay=0.0):
        self._name = name
        self._status = status
        self._severity = severity
        self._timeout = timeout
        self._delay = delay

    @property
    def name(self):
        return self._name

    @property
    def timeout_seconds(self):
        return self._timeout

    @property
    def severity(self):
        return self._severity

    def run(self):
        if self._delay:
            time.sleep(self._delay)
        return HealthCheckResult(
            name=self._name, status=self._status, duration_ms=1,
            message="sentetik sonuç", details={},
        )


@pytest.fixture
def checker_factory(monkeypatch, tmp_path):
    """Raporları tmp_path'e yazan HealthChecker üretir (gerçek outputs/health temiz kalır)."""
    monkeypatch.setattr("app.monitoring.health.health_checker.BASE_DIR", tmp_path)

    def _make(checks):
        return HealthChecker(checks=checks)

    return _make, tmp_path


def test_tum_kontroller_basarili_ve_rapor_yazilir(checker_factory):
    make, tmp_path = checker_factory
    report = make([FakeCheck("A"), FakeCheck("B")]).run_all()
    assert report.overall_status == "SUCCESS"
    assert report.errors == 0
    assert len(report.checks) == 2
    # JSON raporu tmp altına yazılmış olmalı
    assert len(list((tmp_path / "outputs" / "health").glob("health_*.json"))) == 1


def test_severity_durum_birlestirme(checker_factory):
    make, _ = checker_factory
    # CRITICAL kontrol FAILED → genel durum FAILED
    report = make([FakeCheck("OK"), FakeCheck("DB", status="FAILED", severity="CRITICAL")]).run_all()
    assert report.overall_status == "FAILED"
    assert report.errors == 1

    # WARNING severity'li kontrol FAILED → genel durum FAILED değil, WARNING
    report = make([FakeCheck("OK"), FakeCheck("SMTP", status="FAILED", severity="WARNING")]).run_all()
    assert report.overall_status == "WARNING"
    assert report.errors == 1


def test_timeout_korumasi(checker_factory):
    make, _ = checker_factory
    # 2 sn uyuyan kontrol 0.2 sn timeout'a takılmalı; run_all bloklanmamalı
    report = make([FakeCheck("Yavas", timeout=0.2, delay=2.0)]).run_all()
    assert report.checks[0].status == "TIMEOUT"
    assert report.overall_status == "FAILED"  # varsayılan severity CRITICAL


def test_filesystem_check_gercek(checker_factory):
    # Tek gerçek kontrol: yerel disk/dizin yazılabilirliği (ağ bağımlılığı yok)
    make, _ = checker_factory
    result = make([FilesystemCheck()]).run_all()
    assert result.checks[0].status == "SUCCESS"


# ----------------------------------------------------------------------
# BrowserCheck — ölçülen şey BAŞLATMA, kapanış değil (2026-07-28 regresyonu)
# ----------------------------------------------------------------------
def _fake_client(startup=0.0, teardown=0.0, enter_error=None, exit_error=None):
    """Neden: Gerçek Chromium başlatmadan başlatma/kapanış fazlarını taklit etmek."""

    class _FakePage:
        def close(self):
            pass

    class _FakeClient:
        def __init__(self, headless=True):
            self.headless = headless

        def __enter__(self):
            if startup:
                time.sleep(startup)
            if enter_error:
                raise RuntimeError(enter_error)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if teardown:
                time.sleep(teardown)
            if exit_error:
                raise RuntimeError(exit_error)

        def create_page(self):
            return _FakePage()

    return _FakeClient


@pytest.fixture
def patch_client(monkeypatch):
    def _patch(**kwargs):
        monkeypatch.setattr(
            "app.monitoring.health.checks.browser_check.PlaywrightClient",
            _fake_client(**kwargs),
        )

    return _patch


def test_browser_check_normal_basarili(patch_client):
    from app.monitoring.health.checks.browser_check import BrowserCheck

    patch_client()
    result = BrowserCheck().run()

    assert result.status == "SUCCESS"
    assert result.details["startup_ms"] is not None
    assert result.details["teardown_ms"] is not None


def test_browser_check_suresi_kapanisi_ICERMEZ(patch_client):
    """
    Neden (asıl iddia): Kontrolün süresi başlatmayı ölçmeli. Eskiden launch +
    sayfa + kapanış tek pencerede ölçülüyordu ve yavaş kapanış TIMEOUT üretip
    commit'i blokluyordu.
    """
    from app.monitoring.health.checks.browser_check import BrowserCheck

    patch_client(teardown=0.4)
    result = BrowserCheck().run()

    assert result.duration_ms < 200, "süre kapanışı içeriyor"
    assert result.details["teardown_ms"] >= 350


def test_browser_check_yavas_kapanis_FAILED_degil_WARNING(patch_client, monkeypatch):
    from app.monitoring.health.checks.browser_check import BrowserCheck

    # Neden: 22 sn'lik gerçek kapanışı testte beklemek yerine eşik düşürülür.
    monkeypatch.setattr(BrowserCheck, "SLOW_TEARDOWN_MS", 200)
    patch_client(teardown=0.4)
    result = BrowserCheck().run()

    assert result.status == "WARNING"
    assert result.status != "FAILED"
    assert "kapanış" in result.message


def test_browser_check_yavas_kapanis_commiti_BLOKLAMAZ(patch_client, monkeypatch, checker_factory):
    """
    Neden: main.py yalnızca overall_status == FAILED iken sıfırdan farklı çıkış
    kodu verir; pre-commit hook da buna bakar. Yavaş kapanış görünür olmalı ama
    commit'i/ETL'i engellememeli.
    """
    from app.monitoring.health.checks.browser_check import BrowserCheck

    monkeypatch.setattr(BrowserCheck, "SLOW_TEARDOWN_MS", 200)
    patch_client(teardown=0.4)
    make, _ = checker_factory

    report = make([BrowserCheck()]).run_all()

    assert report.overall_status == "WARNING"
    assert report.errors == 0
    assert report.warnings == 1


def test_browser_check_baslatma_hatasi_FAILED(patch_client):
    from app.monitoring.health.checks.browser_check import BrowserCheck

    patch_client(enter_error="chromium bulunamadı")
    result = BrowserCheck().run()

    assert result.status == "FAILED"
    assert "chromium bulunamadı" in result.message


def test_browser_check_kapanis_hatasi_WARNING(patch_client):
    # Neden: Kapanış patlasa bile tarayıcı KULLANILABİLİR; kontrol FAILED olmamalı.
    from app.monitoring.health.checks.browser_check import BrowserCheck

    patch_client(exit_error="pipe kapandı")
    result = BrowserCheck().run()

    assert result.status == "WARNING"
    assert result.details["teardown_error"] == "pipe kapandı"


def test_browser_check_timeout_penceresi_yavas_kapanisa_dayanikli():
    """
    Neden: Emniyet supabı, "yavaş ama biten" kapanıştan önce devreye girmemeli.
    Yapısal iddia — pencere, yavaş sayılan eşikten belirgin şekilde geniş olmalı.
    """
    from app.monitoring.health.checks.browser_check import BrowserCheck

    check = BrowserCheck()
    assert check.timeout_seconds * 1000 >= check.SLOW_TEARDOWN_MS * 4
