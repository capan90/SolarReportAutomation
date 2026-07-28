"""
Neden: Sprint C — faturalama tutarlarının Excel, e-posta ve chatbot çıktılarına
doğru yansıdığını sabitlemek (ADR-0002).

Ana kural her üç kanalda aynı: hesaplanmamış tutar 0 TL DEĞİL, "Bekleniyor" /
"girilmedi" olarak gösterilir. Sıfır tutarla eksik veri karıştırılmamalı.
"""
import json
from datetime import datetime
from decimal import Decimal

import openpyxl
import pytest

from app.billing import BillingService, MonthlyBillingResult, STATUS_LOCKED, STATUS_PENDING_RATE
from app.chatbot.parser import MetricParser
from app.chatbot.query_engine import QueryEngine
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
def _real_style_header(ws, row_idx, n_cols):
    """
    Neden: Üretimdeki _style_header ile AYNI işi yapar. Önceki testler no-op
    lambda geçtiği için stilin yanlış satıra uygulandığı bug'ı kaçırmıştı.
    """
    from openpyxl.styles import Alignment, Font, PatternFill

    for c in range(1, n_cols + 1):
        cell = ws.cell(row=row_idx, column=c)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="EAEAEA", end_color="EAEAEA", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _build_sheet(monkeypatch, cur, prev, style_header=None):
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
        style_header or (lambda w, r, n: None),
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


def test_billing_header_row_is_actually_styled(monkeypatch):
    """
    Neden (regresyon): header_row `max_row + 1` ile hesaplanıyordu. append([])
    hücre yazmadığı için max_row'u artırmaz — stil boş ara satıra uygulanıyor,
    gerçek FATURALAMA başlığı çıplak kalıyordu. METRİK başlığı bold+gri iken
    FATURALAMA'nın olmamasının sebebi buydu.
    """
    class _FakeService:
        def get_monthly(self, year, month):
            return _locked() if (year, month) == (2026, 7) else None

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())

    wb = openpyxl.Workbook()
    ws = wb.active
    job = MonthlySettlementJob.__new__(MonthlySettlementJob)
    job._append_billing_section(
        ws, datetime(2026, 7, 1), datetime(2026, 6, 1),
        "Temmuz 2026", "Haziran 2026", _real_style_header,
    )

    # FATURALAMA başlığının hangi satırda olduğunu bul
    header_row = None
    for row in ws.iter_rows():
        if row[0].value == "FATURALAMA (TL, KDV HARİÇ)":
            header_row = row[0].row
            break
    assert header_row is not None, "FATURALAMA başlığı yazılmamış"

    # O satırın 4 hücresi de METRİK başlığıyla aynı stilde olmalı
    for col in range(1, 5):
        cell = ws.cell(row=header_row, column=col)
        assert cell.font.bold, f"sütun {col} bold değil"
        assert cell.fill.start_color.rgb.endswith("EAEAEA"), f"sütun {col} dolgusuz"


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
# 2b. "Faturalama Özeti" sayfası
# ----------------------------------------------------------------------
def _build_summary(monkeypatch, cur):
    class _FakeService:
        def get_monthly(self, year, month):
            return cur

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())
    wb = openpyxl.Workbook()
    wb.active.title = "Ay Özeti"
    wb.create_sheet("Haftalık Kırılım")
    job = MonthlySettlementJob.__new__(MonthlySettlementJob)
    job._write_billing_summary_sheet(wb, datetime(2026, 7, 1), "Temmuz 2026", _real_style_header)
    return wb


def test_summary_sheet_is_second(monkeypatch):
    # Neden: kWh kırılımlarını geçip aranmasın diye Ay Özeti'nden hemen sonra.
    wb = _build_summary(monkeypatch, _locked())
    assert wb.sheetnames == ["Ay Özeti", "Faturalama Özeti", "Haftalık Kırılım"]


def test_summary_sheet_rows_locked(monkeypatch):
    wb = _build_summary(monkeypatch, _locked())
    rows = {r[0]: r for r in ([c.value for c in row] for row in wb["Faturalama Özeti"].iter_rows()) if r[0]}

    assert rows["Toplam Üretim"][1] == 10000.0
    assert rows["Toplam Üretim"][2] == "—"          # üretimin TL karşılığı yok
    assert rows["Fazla Satış (Enerjisa'ya)"][1] == 1000.0
    assert rows["Fazla Satış (Enerjisa'ya)"][2] == "2.909,69"
    # OSB'ye kalan = üretim - fazla satış (türetilmiş, yeni hesap değil)
    assert rows["OSB'ye Kalan (Üretim − Fazla Satış)"][1] == 9000.0
    assert rows["OSB'ye Kalan (Üretim − Fazla Satış)"][2] == "13.500,00"
    # TOPLAM = fatura + kesinti
    assert rows["TOPLAM (Enerjisa + OSB Kesintisi)"][2] == "16.409,69"
    assert rows["Kullanılan Katsayılar (Fazla Satış / OSB)"][2] == "2,909687 / 1,500000"
    assert rows["Durum"][2] == "Kilitli"


def test_summary_sheet_pending_shows_bekleniyor(monkeypatch):
    wb = _build_summary(monkeypatch, _pending())
    rows = {r[0]: r for r in ([c.value for c in row] for row in wb["Faturalama Özeti"].iter_rows()) if r[0]}

    # Neden: OSB fiyatı girilmemişse kesinti de TOPLAM da 0 DEĞİL, "Bekleniyor".
    assert rows["OSB'ye Kalan (Üretim − Fazla Satış)"][2] == "Bekleniyor"
    assert rows["TOPLAM (Enerjisa + OSB Kesintisi)"][2] == "Bekleniyor"
    assert rows["Fazla Satış (Enerjisa'ya)"][2] == "2.909,69"   # bu hesaplanmıştı
    assert rows["Kullanılan Katsayılar (Fazla Satış / OSB)"][2] == "2,909687 / —"
    assert rows["Durum"][2] == "OSB birim fiyatı bekleniyor"


def test_summary_sheet_header_is_styled(monkeypatch):
    wb = _build_summary(monkeypatch, _locked())
    ws = wb["Faturalama Özeti"]
    header_row = next(r[0].row for r in ws.iter_rows() if r[0].value == "KALEM")
    for col in range(1, 4):
        cell = ws.cell(row=header_row, column=col)
        assert cell.font.bold
        assert cell.fill.start_color.rgb.endswith("EAEAEA")


def test_summary_sheet_skipped_without_billing_row(monkeypatch):
    wb = _build_summary(monkeypatch, None)
    assert "Faturalama Özeti" not in wb.sheetnames


def test_summary_sheet_survives_billing_failure(monkeypatch):
    def _boom():
        raise RuntimeError("DB down")

    monkeypatch.setattr("app.billing.BillingService", _boom)
    wb = openpyxl.Workbook()
    job = MonthlySettlementJob.__new__(MonthlySettlementJob)
    job._write_billing_summary_sheet(wb, datetime(2026, 7, 1), "Temmuz 2026", _real_style_header)
    assert "Faturalama Özeti" not in wb.sheetnames  # exception dışarı sızmadı


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


# ----------------------------------------------------------------------
# 5. Chatbot — yanıt JSON'a çevrilebilmeli (2026-07-28 regresyonu)
# ----------------------------------------------------------------------
def test_billing_fields_are_json_serializable(monkeypatch):
    """
    Neden (regresyon): _billing_fields ham Decimal döndürüyordu ve bu sözlük
    doğrudan /api/chat yanıtının "data" alanına konuyor. json.dumps Decimal'i
    serileştiremediği için faturalama kaydı olan bir ayın SORULARININ TAMAMI
    (yalnızca TL soruları değil) "Sistem şu anda yanıt veremiyor." veriyordu.
    Cevap metni doğru üretiliyordu; patlayan yalnızca serileştirmeydi — bu
    yüzden mevcut testler bugı göremedi, hepsi metne bakıyordu.
    """
    monkeypatch.setattr(BillingService, "get_monthly", lambda self, y, m: _locked(2026, 6))

    fields = QueryEngine()._billing_fields(2026, 6)

    json.dumps(fields)  # ham Decimal ile TypeError verirdi
    assert isinstance(fields["excess_sale_invoice"], float)
    assert isinstance(fields["osb_deduction"], float)
    assert fields["excess_sale_invoice"] == 2909.69
    assert fields["osb_deduction"] == 13500.00


def test_billing_fields_keep_none_instead_of_zero(monkeypatch):
    # Neden: Tip dönüşümü None'ı 0.0'a çevirmemeli — "Bekleniyor" ile "sıfır TL"
    # ayrımı ADR-0002 §6'nın çekirdeği.
    monkeypatch.setattr(BillingService, "get_monthly", lambda self, y, m: _pending(2026, 7))

    fields = QueryEngine()._billing_fields(2026, 7)

    assert fields["osb_deduction"] is None
    assert isinstance(fields["excess_sale_invoice"], float)


def test_billing_fields_empty_when_no_record(monkeypatch):
    monkeypatch.setattr(BillingService, "get_monthly", lambda self, y, m: None)
    assert QueryEngine()._billing_fields(2026, 6) == {}


def test_chatbot_amount_text_unchanged_with_float_values():
    # Neden: Decimal -> float dönüşümü gösterilen tutarı değiştirmemeli.
    out = _answer("fazla satış faturası ne kadar", {"excess_sale_invoice": 2909.69})
    assert "2.909,69 TL" in out
