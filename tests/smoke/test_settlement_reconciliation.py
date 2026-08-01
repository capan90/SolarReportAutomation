"""
Neden: ADR-0003 Faz 1 (Karşılaştır-ve-Uyar). Aylık iş, günlük işin yazdığı veriyi
üzerine yazıyor ve iki yolun aynı sayıyı üretip üretmediği hiç ölçülmedi. Bu faz
DB'ye yazmadan ÖNCE karşılaştırma yapar ve kaydeder — ama HİÇBİR davranışı
değiştirmez: ezme sürer, rapor ve e-posta akışı etkilenmez.

Testlerin koruduğu asıl sözleşme: karşılaştırma katmanı patlarsa bile upsert'ler
çalışmaya devam eder (izole try/except).
"""

import pytest

from app.jobs.monthly_settlement_job import MonthlySettlementJob
from app.settlement.models import HourlySettlement

METRICS = ["production_kwh", "consumption_kwh", "settled_kwh",
           "grid_import_kwh", "grid_export_kwh"]


def _hours(day: str, count: int = 24, production: float = 1000.0,
           consumption: float = 800.0) -> list:
    """Bir güne ait `count` saatlik kayıt üretir."""
    out = []
    for h in range(count):
        out.append(HourlySettlement(
            timestamp=f"{day} {h:02d}:00:00",
            production_kwh=production,
            consumption_kwh=consumption,
            settled_kwh=min(production, consumption),
            grid_export_kwh=max(0.0, production - consumption),
            grid_import_kwh=max(0.0, consumption - production),
        ))
    return out


def _snapshot_from(settlements: list) -> dict:
    """Aynı verinin DB'de duruyormuş gibi snapshot karşılığını üretir."""
    snap: dict = {}
    for s in settlements:
        day = str(s.timestamp)[:10]
        entry = snap.setdefault(day, {m: 0.0 for m in METRICS} | {"hours": 0})
        for m in METRICS:
            entry[m] += float(getattr(s, m))
        entry["hours"] += 1
    return snap


def _problems(comparisons):
    return [c for c in comparisons if not c["within_tolerance"]]


def test_identical_data_produces_no_difference():
    settlements = _hours("2026-07-01") + _hours("2026-07-02")
    result = MonthlySettlementJob._compare_month_with_db(
        settlements, _snapshot_from(settlements)
    )

    assert len(result) == 2 * len(METRICS)          # eşleşen günler de kaydedilir
    assert _problems(result) == []
    assert all(c["diff"] == 0.0 for c in result)


def test_real_difference_is_detected_with_values():
    settlements = _hours("2026-07-01", production=1000.0)
    db = _snapshot_from(_hours("2026-07-01", production=900.0))

    result = MonthlySettlementJob._compare_month_with_db(settlements, db)
    prod = next(c for c in result if c["metric"] == "production_kwh")

    assert not prod["within_tolerance"]
    assert prod["db_value"] == pytest.approx(24 * 900.0)
    assert prod["scrape_value"] == pytest.approx(24 * 1000.0)
    assert prod["diff"] == pytest.approx(24 * 100.0)
    assert prod["diff_pct"] == pytest.approx(100 / 900 * 100)


def test_tiny_difference_stays_within_tolerance():
    """%0,1'in altındaki fark gürültü sayılır (iki eşik birden aşılmalı)."""
    settlements = _hours("2026-07-01", production=1000.0)
    db = _snapshot_from(_hours("2026-07-01", production=1000.001))

    result = MonthlySettlementJob._compare_month_with_db(settlements, db)
    assert _problems(result) == []


def test_absolute_floor_suppresses_noise_on_near_zero_values():
    """0'a yakın değerde 1 kWh altı fark, oransal olarak devasa görünse de uyarı değil."""
    settlements = _hours("2026-07-01", production=800.0, consumption=800.0)   # export = 0
    db_hours = _hours("2026-07-01", production=800.0, consumption=800.0)
    db = _snapshot_from(db_hours)
    db["2026-07-01"]["grid_export_kwh"] = 0.02      # 24 saatte toplam 0,02 kWh

    result = MonthlySettlementJob._compare_month_with_db(settlements, db)
    export = next(c for c in result if c["metric"] == "grid_export_kwh")

    assert export["within_tolerance"], "1 kWh altı mutlak fark uyarı üretmemeli"


def test_missing_day_in_db_is_flagged():
    settlements = _hours("2026-07-01") + _hours("2026-07-02")
    db = _snapshot_from(_hours("2026-07-01"))       # 2 Temmuz DB'de hiç yok

    result = MonthlySettlementJob._compare_month_with_db(settlements, db)
    day2 = [c for c in result if c["date"] == "2026-07-02"]

    assert len(day2) == len(METRICS)
    assert all(not c["within_tolerance"] for c in day2)
    assert all(c["db_hours"] == 0 and c["scrape_hours"] == 24 for c in day2)


def test_partial_day_is_flagged_even_when_metrics_match():
    """
    Kapsam uyuşmazlığı eşikten BAĞIMSIZ uyarı üretir: metrik değeri tesadüfen
    tolerans içinde kalsa bile eksik saatli gün işaretlenmeli.
    """
    settlements = _hours("2026-07-13", count=24, production=0.0, consumption=0.0)
    db = _snapshot_from(_hours("2026-07-13", count=12, production=0.0, consumption=0.0))

    result = MonthlySettlementJob._compare_month_with_db(settlements, db)

    assert all(c["diff"] == 0.0 for c in result), "değerler eşit olmalı (kurgu)"
    assert all(not c["within_tolerance"] for c in result), "kapsam farkı yine de işaretlenmeli"
    assert result[0]["db_hours"] == 12 and result[0]["scrape_hours"] == 24


def test_diff_pct_is_none_when_db_value_is_zero():
    """Sıfıra bölme yerine NULL — 'yüzde hesaplanamaz' ile '%0 fark' karıştırılmasın."""
    settlements = _hours("2026-07-01", production=1000.0)
    db = _snapshot_from(_hours("2026-07-01", production=0.0))

    result = MonthlySettlementJob._compare_month_with_db(settlements, db)
    prod = next(c for c in result if c["metric"] == "production_kwh")

    assert prod["db_value"] == 0.0
    assert prod["diff_pct"] is None


def test_empty_db_snapshot_flags_every_day_without_crashing():
    """İlk koşuda DB boş olabilir — hata değil, tümü kapsam farkı olarak işaretlenir."""
    settlements = _hours("2026-07-01") + _hours("2026-07-02")

    result = MonthlySettlementJob._compare_month_with_db(settlements, {})

    assert len(result) == 2 * len(METRICS)
    assert all(not c["within_tolerance"] for c in result)


class _FakeRepo:
    """Yazma akışını taklit eder; karşılaştırma çağrılarında istenirse patlar."""

    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.saved = None
        self.upserted = []

    def get_hourly_month_snapshot(self, year, month):
        if self.fail_on == "snapshot":
            raise RuntimeError("DB down")
        return {}

    def save_reconciliation(self, run_id, target_month, comparisons):
        if self.fail_on == "save":
            raise RuntimeError("tablo yok")
        self.saved = (run_id, target_month, comparisons)
        return len(comparisons)

    def upsert_hourly(self, settlements):
        self.upserted.append(len(settlements))
        return len(settlements)


@pytest.mark.parametrize("fail_on", [None, "snapshot", "save"])
def test_reconciliation_never_raises_so_upserts_still_run(fail_on):
    """
    Asıl sözleşme: gözlem katmanı ne olursa olsun yazma akışını bozmamalı.
    _reconcile_best_effort fırlatırsa, çağıran taraftaki upsert atlanırdı.
    """
    repo = _FakeRepo(fail_on=fail_on)
    settlements = _hours("2026-07-01")

    MonthlySettlementJob._reconcile_best_effort(
        repo, "run-1", "2026-07", 2026, 7, settlements
    )
    repo.upsert_hourly(settlements)   # çağıranın bir sonraki adımı

    assert repo.upserted == [24], "upsert her durumda çalışmalı"


def test_reconciliation_saves_rows_on_happy_path():
    repo = _FakeRepo()
    settlements = _hours("2026-07-01")

    MonthlySettlementJob._reconcile_best_effort(
        repo, "run-1", "2026-07", 2026, 7, settlements
    )

    run_id, month, comparisons = repo.saved
    assert run_id == "run-1" and month == "2026-07"
    assert len(comparisons) == len(METRICS)   # tek gün × beş metrik


def test_logging_does_not_raise_on_either_branch(caplog):
    same = _hours("2026-07-01")
    clean = MonthlySettlementJob._compare_month_with_db(same, _snapshot_from(same))
    dirty = MonthlySettlementJob._compare_month_with_db(same, {})

    MonthlySettlementJob._log_reconciliation("2026-07", clean)
    MonthlySettlementJob._log_reconciliation("2026-07", dirty)
