"""
Neden: 2026-08-03 09:00 koşusu tarayıcı kapanışında asıldı; süreç yaşadığı için istisna
oluşmadı ve hiçbir alarm tetiklenmedi — 2 Ağustos verisi sessizce eksik kaldı. Veri-eksik
kontrolü mekanizmaya değil SONUCA bakarak bu sınıfın tamamını yakalar.

Bu testler üç seviyenin de doğru ayrıldığını ve normal günün mail üretmediğini doğrular;
gerçek DB veya SMTP'ye çıkılmaz.
"""

import datetime

import pytest

from app.jobs.data_freshness_job import (
    DataFreshnessJob,
    LEVEL_MISSING,
    LEVEL_OK,
    LEVEL_PARTIAL,
)


class FakeRepository:
    """settlement_daily/settlement_hourly cevaplarını sabitleyen sahte repository."""

    def __init__(self, has_daily: bool, hours: int):
        self._has_daily = has_daily
        self._hours = hours
        self.asked_dates = []

    def has_daily_data(self, date):
        self.asked_dates.append(date)
        return self._has_daily

    def count_hourly(self, date):
        return self._hours


class FakeAlertSender:
    def __init__(self):
        self.calls = []

    def __call__(self, job_name, error, headline="", explanation=""):
        self.calls.append({
            "job_name": job_name,
            "error": error,
            "headline": headline,
            "explanation": explanation,
        })
        return True


def _run(has_daily, hours, target_date="2026-08-02"):
    alerts = FakeAlertSender()
    job = DataFreshnessJob(repository=FakeRepository(has_daily, hours), alert_sender=alerts)
    return job.run(target_date=target_date), alerts


def test_missing_day_raises_alarm():
    """2026-08-02'nin imzası: gün hiç yazılmamış — mail gitmeli."""
    result, alerts = _run(has_daily=False, hours=0)

    assert result.level == LEVEL_MISSING
    assert result.is_problem
    assert len(alerts.calls) == 1
    assert "2026-08-02" in alerts.calls[0]["headline"]


def test_partial_day_raises_warning():
    """2026-07-13 vakası: satır var ama 12 saat — yalnızca varlığa bakan kontrol kaçırırdı."""
    result, alerts = _run(has_daily=True, hours=12)

    assert result.level == LEVEL_PARTIAL
    assert result.hours == 12
    assert len(alerts.calls) == 1
    assert "12" in alerts.calls[0]["error"]


def test_complete_day_is_silent():
    """Normal gün mail üretmemeli — her sabah gürültü alarmı işe yaramaz hale getirir."""
    result, alerts = _run(has_daily=True, hours=24)

    assert result.level == LEVEL_OK
    assert not result.is_problem
    assert alerts.calls == []


def test_partial_boundary_at_23_hours():
    """23 saat de eksiktir; sınır 24'ün altında herhangi bir değerde çalışmalı."""
    result, _ = _run(has_daily=True, hours=23)
    assert result.level == LEVEL_PARTIAL


def test_missing_day_reports_orphan_hours():
    """
    Saatlik veri yazılmış ama günlük satır yoksa (iş gün ortasında öldü) mesaj bu ayrımı
    taşımalı — 'hiç koşmadı' ile 'yarıda kaldı' teşhisi farklı yerlere bakmayı gerektirir.
    """
    result, alerts = _run(has_daily=False, hours=18)

    assert result.level == LEVEL_MISSING
    assert "18" in result.message
    assert "18" in alerts.calls[0]["error"]


def test_defaults_to_yesterday():
    """Tarih verilmezse dün kontrol edilmeli (zamanlanmış koşunun varsayılanı)."""
    repo = FakeRepository(has_daily=True, hours=24)
    DataFreshnessJob(repository=repo, alert_sender=FakeAlertSender()).run()

    expected = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    assert repo.asked_dates == [expected]


def test_alert_explanation_is_not_the_uncaught_exception_text():
    """
    Neden: system_alert'in varsayılan gövdesi 'yakalanmamış istisna' diyor. Veri eksikliği
    o değil; yanlış açıklama teşhisi yanlış yere yönlendirir.
    """
    _, alerts = _run(has_daily=False, hours=0)

    explanation = alerts.calls[0]["explanation"]
    assert explanation
    assert "istisna" not in explanation.lower()


def test_invalid_date_is_not_reported_as_missing_data():
    """
    Bozuk tarih biçimi veri eksikliği DEĞİL çağıran hatasıdır; sahte 'veri yok' alarmı
    üretmemeli. Repository ValueError fırlatır ve dışarı çıkar.
    """
    class ExplodingRepository(FakeRepository):
        def count_hourly(self, date):
            raise ValueError("Geçersiz tarih biçimi")

    alerts = FakeAlertSender()
    job = DataFreshnessJob(repository=ExplodingRepository(True, 0), alert_sender=alerts)

    with pytest.raises(ValueError):
        job.run(target_date="02-08-2026")

    assert alerts.calls == []
