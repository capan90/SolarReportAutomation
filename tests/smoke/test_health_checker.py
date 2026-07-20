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
