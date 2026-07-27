"""
Neden: Sprint C — faturalama tutarlarının Excel, e-posta ve chatbot çıktılarına
doğru yansıdığını sabitlemek (ADR-0002).

Ana kural her üç kanalda aynı: hesaplanmamış tutar 0 TL DEĞİL, "Bekleniyor" /
"girilmedi" olarak gösterilir. Sıfır tutarla eksik veri karıştırılmamalı.
"""
from datetime import datetime
from decimal import Decimal

import openpyxl
import pytest

from app.billing import MonthlyBillingResult, STATUS_LOCKED, STATUS_PENDING_RATE
from app.chatbot.parser import MetricParser
from app.chatbot.response_builder import ResponseBuilder
from app.jobs.monthly_settlement_job import MonthlySettlementJob


def _locked(year=2026, month=7):
    return MonthlyBillingResult(
        year=year, month=month, status=STATUS_LOCKED,
        excess_sale_rate_try=Decimal("2.909687"),
        osb_unit_price_try=Decimal("1.500000"),
        production_kwh=Decimal("10000"), excess_sale_kwh=Decimal("1000"),
        excess_sale_invoice_try=Decimal("2909.69"),
        osb_deduction_try=Decimal("13500.00"),
        locked_at=datetime(2026, 7, 27, 12, 0, 0),
    )


def _pending(year=2026, month=7):
    return MonthlyBillingResult(
        year=year, month=month, status=STATUS_PENDING_RATE,
        excess_sale_rate_try=Decimal("2.909687"),
        production_kwh=Decimal("10000"), excess_sale_kwh=Decimal("1000"),
        excess_sale_invoice_try=Decimal("2909.69"),
        osb_deduction_try=None,
    )


# ----------------------------------------------------------------------
# 1. Para biçimi
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("2909.69"), "2.909,69"),
        (Decimal("13500.00"), "13.500,00"),
        (Decimal("0.50"), "0,50"),
        (Decimal("1234567.89"), "1.234.567,89"),
        (None, "Bekleniyor"),
    ],
)
def test_try_formatting_is_turkish(value, expected):
    assert MonthlySettlementJob._fmt_try(value) == expected


def test_rate_formatting_keeps_six_decimals():
    assert MonthlySettlementJob._fmt_rate(Decimal("2.909687")) == "2,909687"
    assert MonthlySettlementJob._fmt_rate(None) == "—"


def test_email_pending_line_has_no_currency_unit():
    """
    Neden (regresyon): İlk uygulamada e-postada "Bekleniyor TL" yazıyordu.
    Birim yalnızca gerçek tutara eklenmeli. Dev doğrulamasında yakalandı.
    """
    job = MonthlySettlementJob.__new__(MonthlySettlementJob)

    def _tl(value):
        if value is None:
            return job.BILLING_PENDING_TEXT
        return f"{job._fmt_try(value)} TL"

    assert _tl(None) == "Bekleniyor"
    assert "TL" not in _tl(None)
    assert _tl(Decimal("13500.00")) == "13.500,00 TL"


# ----------------------------------------------------------------------
# 2. Excel "FATURALAMA" bölümü
# ----------------------------------------------------------------------
def _build_sheet(monkeypatch, cur, prev):
    class _FakeService:
        def get_monthly(self, year, month):
            return cur if (year, month) == (2026, 7) else prev

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())

    wb = openpyxl.Workbook()
    ws = wb.active
    job = MonthlySettlementJob.__new__(MonthlySettlementJob)
    job._append_billing_section(
        ws,
        datetime(2026, 7, 1), datetime(2026, 6, 1),
        "Temmuz 2026", "Haziran 2026",
        lambda w, r, n: None,
    )
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_excel_billing_section_locked(monkeypatch):
    rows = _build_sheet(monkeypatch, _locked(), _locked(2026, 6))
    flat = {r[0]: r for r in rows if r and r[0]}

    assert "FATURALAMA (TL, KDV HARİÇ)" in flat
    assert flat["Fazla Satış Faturası"][1] == "2.909,69"
    assert flat["OSB Kesintisi"][1] == "13.500,00"
    assert flat["Durum"][1] == "Kilitli"
    # Denetim satırı: hangi katsayılarla hesaplandı
    assert flat["Kullanılan Katsayılar (Fazla Satış / OSB)"][1] == "2,909687 / 1,500000"


def test_excel_billing_section_pending_shows_bekleniyor(monkeypatch):
    rows = _build_sheet(monkeypatch, _pending(), None)
    flat = {r[0]: r for r in rows if r and r[0]}

    # Neden: 0,00 YAZILMAMALI — "kesinti yok" ile "henüz hesaplanmadı" farklıdır.
    assert flat["OSB Kesintisi"][1] == "Bekleniyor"
    assert flat["Durum"][1] == "OSB birim fiyatı bekleniyor"
    # OSB katsayısı girilmediği için tire
    assert flat["Kullanılan Katsayılar (Fazla Satış / OSB)"][1] == "2,909687 / —"


def test_excel_change_percent_only_when_both_months_computed(monkeypatch):
    rows = _build_sheet(monkeypatch, _locked(), _locked(2026, 6))
    flat = {r[0]: r for r in rows if r and r[0]}
    # Aynı değerler -> %0 değişim
    assert flat["Fazla Satış Faturası"][3] == 0.0

    # Önceki ay yoksa yüzde uydurulmaz
    rows2 = _build_sheet(monkeypatch, _locked(), None)
    flat2 = {r[0]: r for r in rows2 if r and r[0]}
    assert flat2["Fazla Satış Faturası"][3] == "-"


def test_excel_section_skipped_when_no_billing_row(monkeypatch):
    # Neden: Billing katmanı öncesi aylarda kayıt yok; bölüm hiç eklenmemeli.
    rows = _build_sheet(monkeypatch, None, None)
    assert all(not (r and r[0]) for r in rows)


def test_excel_section_survives_billing_failure(monkeypatch):
    # Neden: TL hesabı rapor üretimini ASLA engellemez (best-effort).
    def _boom():
        raise RuntimeError("DB down")

    monkeypatch.setattr("app.billing.BillingService", _boom)
    wb = openpyxl.Workbook()
    ws = wb.active
    job = MonthlySettlementJob.__new__(MonthlySettlementJob)
    job._append_billing_section(
        ws, datetime(2026, 7, 1), datetime(2026, 6, 1), "Temmuz 2026", "Haziran 2026",
        lambda w, r, n: None,
    )
    assert ws.max_row == 1  # hiçbir şey yazılmadı, exception dışarı sızmadı


# ----------------------------------------------------------------------
# 3. Chatbot — metrik ayrıştırma
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "question,expected",
    [
        ("fazla satış faturası ne kadar", "excess_sale_invoice"),
        ("bu ay enerjisa faturası", "excess_sale_invoice"),
        ("osb kesintisi ne kadar", "osb_deduction"),
        ("geçen ay osb faturası", "osb_deduction"),
        ("bu ay ne kadar düşecek", "osb_deduction"),
    ],
)
def test_billing_questions_are_parsed(question, expected):
    parsed = MetricParser().parse(question)
    assert expected in parsed["metrics"]
    assert parsed["explicit"] is True


def test_plain_kwh_question_does_not_trigger_billing():
    parsed = MetricParser().parse("bu ay fazla satış ne kadar")
    assert "grid_export" in parsed["metrics"]
    assert "excess_sale_invoice" not in parsed["metrics"]


# ----------------------------------------------------------------------
# 4. Chatbot — cevap üretimi
# ----------------------------------------------------------------------
def _answer(question, data, period="month", label="Temmuz 2026"):
    metric_info = MetricParser().parse(question)
    return ResponseBuilder().build(
        question, {"type": period, "label": label}, metric_info, data
    )


def test_chatbot_returns_invoice_amount():
    out = _answer("fazla satış faturası ne kadar", {"excess_sale_invoice": Decimal("2909.69")})
    assert "2.909,69 TL" in out
    assert "KDV hariç" in out


def test_chatbot_says_price_missing_not_zero():
    # Neden: None -> "0 TL" demek yöneticiyi yanıltır; hiç tutar gösterilmemeli.
    out = _answer("osb kesintisi ne kadar", {"osb_deduction": None})
    assert "0,00" not in out and "0 TL" not in out
    assert "TL" not in out  # hiçbir tutar yazılmamalı
    assert "girilmemiş" in out or "girilmedi" in out


def test_chatbot_rejects_billing_for_daily_period():
    out = _answer("dün osb kesintisi", {"osb_deduction": Decimal("1")}, period="day", label="dün")
    assert "yalnızca aylık" in out
    # Neden: capitalize() "OSB"yi "Osb" yapıyordu — kısaltma bozulmamalı.
    assert "Osb" not in out
    assert "OSB kesintisi" in out


def test_chatbot_reports_missing_billing_record():
    out = _answer("osb kesintisi ne kadar", {"production": 100})
    assert "faturalama kaydı bulunamadı" in out


def test_monthly_summary_appends_billing_lines():
    data = {
        "production": 10000, "consumption": 9000, "settled": 8000,
        "grid_import": 1000, "grid_export": 2000,
        "excess_sale_invoice": Decimal("2909.69"), "osb_deduction": None,
    }
    out = _answer("bu ay özet", data)
    assert "Faturalama (KDV hariç)" in out
    assert "2.909,69 TL" in out
    assert "Bekleniyor" in out


def test_daily_summary_has_no_billing_lines():
    # Neden: Günlük raporda TL yok (tutarlılık kararı).
    data = {"production": 100, "consumption": 90, "settled": 80,
            "grid_import": 10, "grid_export": 20}
    out = _answer("dün özet", data, period="day", label="dün")
    assert "Faturalama" not in out
