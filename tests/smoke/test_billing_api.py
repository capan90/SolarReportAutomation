"""
Neden: Faturalama dashboard uçlarının sözleşmesini sabitlemek (Sprint B, ADR-0002).
Kapsam: yönetici şifresi doğrulaması (+ audit kaydı), domain hatası -> HTTP durum
kodu eşlemesi, ay formatı doğrulaması ve banner'ın bekleyen ayları katlaması.

HTTP sunucusu ayağa kaldırılmaz: handler metotları sahte (fake) self nesnesiyle
çağrılır. Böylece test hızlı kalır ve gerçek DB'ye/porta dokunulmaz.
"""
import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.billing import (
    BillingLockedError,
    BillingMonthNotFoundError,
    BillingRateExistsError,
    BillingValidationError,
    MonthlyBillingResult,
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
)
from app.dashboard.web_server import DashboardRequestHandler

ADMIN_PW = "test-admin-pw"


class _FakeAuth:
    """Neden: audit_log çağrılarını DB'ye yazmadan yakalamak."""

    def __init__(self):
        self.actions = []

    def log_action(self, username, ip, action, details=None, success=True):
        self.actions.append(
            {"username": username, "ip": ip, "action": action, "details": details, "success": success}
        )


class _FakeHandler:
    """Neden: BaseHTTPRequestHandler kurmadan handler metotlarını çağırabilmek."""

    def __init__(self, body=None):
        self._body = body or {}
        self.auth = _FakeAuth()
        self.sent = None

    # --- gerçek handler'dan ödünç alınan davranışlar ---
    _verify_admin_password = DashboardRequestHandler._verify_admin_password
    _send_billing_error = DashboardRequestHandler._send_billing_error
    _handle_billing_set_rate = DashboardRequestHandler._handle_billing_set_rate
    _handle_billing_set_osb_rate = DashboardRequestHandler._handle_billing_set_osb_rate
    _handle_billing_override = DashboardRequestHandler._handle_billing_override
    _handle_settlement_trigger_monthly_date = (
        DashboardRequestHandler._handle_settlement_trigger_monthly_date
    )

    def _read_json_body(self):
        return self._body

    def _get_client_ip(self):
        return "127.0.0.1"

    def _send_json_contract(self, data, error, status_code=200):
        self.sent = {"data": data, "error": error, "status": status_code}


@pytest.fixture(autouse=True)
def admin_password(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ADMIN_PASSWORD", ADMIN_PW)


# ----------------------------------------------------------------------
# 1. Yönetici şifresi
# ----------------------------------------------------------------------
def test_wrong_password_is_rejected_and_audited():
    h = _FakeHandler({"admin_password": "yanlis", "unit_price": "2.9", "valid_from": "2026-08"})
    h._handle_billing_set_rate("murat")

    assert h.sent["error"] and "şifre" in h.sent["error"].lower()
    # Denetim izi: başarısız deneme kaydedilmeli
    assert len(h.auth.actions) == 1
    entry = h.auth.actions[0]
    assert entry["action"] == "billing_rate_change"
    assert entry["success"] is False


def test_wrong_admin_password_must_not_return_401():
    """
    Neden (regresyon): Arayüzdeki global fetch sarmalayıcısı her 401'i "oturum
    düştü" sayıp kullanıcıyı login ekranına atıyor. Yanlış yönetici şifresi
    oturum hatası değildir; kullanıcı formda kalmalı. Dev ortamında bu bug
    gerçekten yaşandı (Sprint B doğrulaması).
    """
    for handler, args in (
        ("_handle_billing_set_rate", ("murat",)),
        ("_handle_billing_set_osb_rate", ("murat", "2026-07")),
    ):
        h = _FakeHandler({"admin_password": "yanlis", "unit_price": "1.5", "valid_from": "2026-08"})
        getattr(h, handler)(*args)
        assert h.sent["status"] != 401, f"{handler} 401 döndürdü — kullanıcı oturumdan atılır"
        assert h.sent["error"]


def test_missing_admin_password_env_blocks_write(monkeypatch):
    # Neden: DASHBOARD_ADMIN_PASSWORD tanımsızsa yazma AÇIK KALMAMALI.
    monkeypatch.delenv("DASHBOARD_ADMIN_PASSWORD", raising=False)
    h = _FakeHandler({"admin_password": "", "unit_price": "2.9", "valid_from": "2026-08"})
    h._handle_billing_set_rate("murat")
    assert h.sent["error"] and h.sent["data"] is None


def test_osb_rate_wrong_password_audited():
    h = _FakeHandler({"admin_password": "yanlis", "unit_price": "1.5"})
    h._handle_billing_set_osb_rate("murat", "2026-07")
    assert h.sent["error"]
    assert h.auth.actions[0]["action"] == "billing_osb_rate_entry"
    assert h.auth.actions[0]["success"] is False


# ----------------------------------------------------------------------
# 2. Girdi doğrulama
# ----------------------------------------------------------------------
@pytest.mark.parametrize("valid_from", ["", "2026", "26-08", "2026/08", "abc"])
def test_invalid_valid_from_rejected(valid_from):
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "2.9", "valid_from": valid_from})
    h._handle_billing_set_rate("murat")
    assert h.sent["status"] == 400


@pytest.mark.parametrize("month_str", ["2026", "2026-13-01", "temmuz", "26-07"])
def test_invalid_month_format_rejected(month_str):
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "1.5"})
    h._handle_billing_set_osb_rate("murat", month_str)
    assert h.sent["status"] == 400
    # Neden: Format hatası şifre kontrolünden ÖNCE yakalanır; audit kirlenmemeli
    assert h.auth.actions == []


def test_month_picker_value_is_normalized_to_first_day(monkeypatch):
    # Neden: Arayüz <input type="month"> "2026-08" gönderir; ayın 1'ine tamamlanmalı.
    captured = {}

    class _FakeService:
        def get_current_rate(self, as_of=None):
            return None

        def set_rate(self, unit_price_try, valid_from, created_by, note=None):
            captured["valid_from"] = valid_from
            captured["created_by"] = created_by
            return _rate_dto(valid_from)

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "2.909687", "valid_from": "2026-08"})
    h._handle_billing_set_rate("murat")

    assert captured["valid_from"] == date(2026, 8, 1)
    assert captured["created_by"] == "murat"
    assert h.sent["error"] is None


def _rate_dto(valid_from):
    from app.billing import BillingRateDto

    return BillingRateDto(
        id=1,
        rate_type="EXCESS_SALE_UNIT_PRICE",
        unit_price_try=Decimal("2.909687"),
        valid_from=valid_from,
        created_by="murat",
        created_at=datetime(2026, 7, 27, 10, 0, 0),
        note=None,
    )


# ----------------------------------------------------------------------
# 3. Domain hatası -> HTTP durum kodu eşlemesi
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "exc,expected_status",
    [
        (BillingValidationError("negatif"), 400),
        (BillingMonthNotFoundError("kayıt yok"), 404),
        (BillingLockedError("2026-07 ayı kilitli."), 409),
        (BillingRateExistsError("zaten var"), 409),
        (RuntimeError("beklenmedik"), 200),  # genel hata -> sözleşme içinde error mesajı
    ],
)
def test_billing_error_status_mapping(exc, expected_status):
    h = _FakeHandler()
    h._send_billing_error(exc)
    assert h.sent["status"] == expected_status
    assert h.sent["error"]


def test_locked_error_mentions_override_flow():
    # Neden: Kullanıcı "neden değiştiremiyorum" sorusunun cevabını mesajda görmeli.
    # Override akışı eklenmeden önce mesaj "henüz mevcut değil" diyordu; artık somut
    # bir eyleme yönlendiriyor — asıl iddia "çıkış yolu gösteriliyor mu".
    h = _FakeHandler()
    h._send_billing_error(BillingLockedError("2026-07 ayı kilitli."))
    mesaj = h.sent["error"].lower()
    assert "düzelt" in mesaj, "kilit mesajı kullanıcıya çıkış yolunu göstermeli"
    assert "henüz mevcut değil" not in mesaj, "override artık mevcut"


def test_unexpected_error_does_not_leak_details():
    h = _FakeHandler()
    h._send_billing_error(RuntimeError("psycopg2: password=secret host=10.0.0.169"))
    assert "secret" not in h.sent["error"]
    assert "sistem yöneticinizle" in h.sent["error"].lower()


# ----------------------------------------------------------------------
# 4. Başarılı akışlar ve audit içeriği
# ----------------------------------------------------------------------
def test_rate_change_audit_records_old_and_new(monkeypatch):
    class _FakeService:
        def get_current_rate(self, as_of=None):
            from app.billing import BillingRateDto

            return BillingRateDto(
                id=1, rate_type="EXCESS_SALE_UNIT_PRICE",
                unit_price_try=Decimal("2.000000"), valid_from=date(2026, 6, 1),
                created_by="eski", created_at=None, note=None,
            )

        def set_rate(self, unit_price_try, valid_from, created_by, note=None):
            return _rate_dto(valid_from)

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "2.909687", "valid_from": "2026-08"})
    h._handle_billing_set_rate("murat")

    details = h.auth.actions[0]["details"]
    assert "2.000000" in details and "2.909687" in details
    assert h.auth.actions[0]["success"] is True


def test_rate_change_response_says_no_restart_needed(monkeypatch):
    class _FakeService:
        def get_current_rate(self, as_of=None):
            return None

        def set_rate(self, unit_price_try, valid_from, created_by, note=None):
            return _rate_dto(valid_from)

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "2.909687", "valid_from": "2026-08"})
    h._handle_billing_set_rate("murat")

    # Neden: SMTP akışından farkı (restart gerekmemesi) kullanıcıya söylenmeli.
    assert "yeniden başlat" in h.sent["data"]["note"].lower()


def test_osb_rate_success_returns_regenerate_url(monkeypatch):
    class _FakeService:
        def set_osb_unit_price(self, year, month, unit_price_try, entered_by):
            return MonthlyBillingResult(
                year=year, month=month, status=STATUS_LOCKED,
                osb_unit_price_try=Decimal("1.500000"),
                osb_deduction_try=Decimal("13500.00"),
                locked_at=datetime(2026, 7, 27, 12, 0, 0),
            )

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "1.5"})
    h._handle_billing_set_osb_rate("murat", "2026-07")

    assert h.sent["error"] is None
    assert h.sent["data"]["regenerate_url"] == "/api/settlement/trigger/monthly-date"
    assert h.sent["data"]["month"] == "2026-07"
    assert h.sent["data"]["billing"]["status"] == STATUS_LOCKED
    assert h.auth.actions[0]["success"] is True


def test_osb_rate_locked_month_returns_409_and_audits_failure(monkeypatch):
    class _FakeService:
        def set_osb_unit_price(self, year, month, unit_price_try, entered_by):
            raise BillingLockedError("2026-07 ayı kilitli; OSB birim fiyatı değiştirilemez.")

    monkeypatch.setattr("app.billing.BillingService", lambda: _FakeService())
    h = _FakeHandler({"admin_password": ADMIN_PW, "unit_price": "9.9"})
    h._handle_billing_set_osb_rate("murat", "2026-07")

    assert h.sent["status"] == 409
    assert h.auth.actions[-1]["success"] is False


# ----------------------------------------------------------------------
# 5. Banner: bekleyen ayların katlanması
# ----------------------------------------------------------------------
def _pending(year, month):
    return MonthlyBillingResult(year=year, month=month, status=STATUS_PENDING_RATE)


@pytest.mark.parametrize(
    "count,expected_visible,expected_hidden",
    [(0, 0, 0), (1, 1, 0), (3, 3, 0), (5, 3, 2)],
)
def test_pending_months_are_folded_after_three(monkeypatch, count, expected_visible, expected_hidden):
    from app.dashboard.service import DashboardService

    months = [_pending(2026, m) for m in range(1, count + 1)]

    class _FakeBilling:
        def list_pending_months(self, limit=24):
            return months

    service = DashboardService.__new__(DashboardService)
    service._billing_service = _FakeBilling()
    monkeypatch.setattr(DashboardService, "_billing", lambda self: self._billing_service)

    result = service.get_pending_billing_months()
    assert result["total"] == count
    assert len(result["visible"]) == expected_visible
    assert result["hidden_count"] == expected_hidden


# ----------------------------------------------------------------------
# 6. Sözleşme serileştirmesi — Decimal tüm ucu düşürmemeli (2026-07-28)
# ----------------------------------------------------------------------
class _WireHandler:
    """
    Neden: Gerçek _send_json_contract'ı (içindeki json.dumps dahil) soket
    kurmadan koşturmak. Savunma katmanının GERÇEKTEN bağlı olduğunu doğrular;
    testin kendi json.dumps'ını çağırmak bunu kanıtlamazdı.
    """

    _json_default = staticmethod(DashboardRequestHandler._json_default)
    _send_json_contract = DashboardRequestHandler._send_json_contract

    def __init__(self):
        self.status = None
        self.headers_sent = {}
        self.wfile = io.BytesIO()

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.headers_sent[key] = value

    def end_headers(self):
        pass

    def payload(self):
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def test_contract_serializes_decimal_instead_of_failing():
    """
    Neden (regresyon): json.dumps'ta default= yoktu; bir uçtan sızan tek bir
    Decimal TypeError verip handler'ın genel except'ine düşüyor ve TÜM ucu
    çalışmaz hâle getiriyordu (chatbot: "Sistem şu anda yanıt veremiyor.").
    """
    h = _WireHandler()
    h._send_json_contract({"tutar": Decimal("10748030.54")}, None)

    body = h.payload()
    assert h.status == 200
    assert body["success"] is True
    assert body["data"]["tutar"] == 10748030.54


def test_contract_serializes_dates():
    h = _WireHandler()
    h._send_json_contract({"gun": date(2026, 6, 30), "an": datetime(2026, 6, 30, 12, 0)}, None)

    body = h.payload()
    assert body["data"]["gun"] == "2026-06-30"
    assert body["data"]["an"].startswith("2026-06-30T12:00")


def test_contract_still_rejects_unknown_types():
    # Neden: Savunma katmanı "her şeyi str'e çevir" DEĞİL — bilinmeyen tip
    # sessizce bozuk veriye dönüşmemeli, hata vermeli.
    with pytest.raises(TypeError):
        DashboardRequestHandler._json_default(object())


# ----------------------------------------------------------------------
# 7. "Raporu Yeniden Üret" — force cache'i atlamalı (2026-07-28)
# ----------------------------------------------------------------------
def _prev_month_str():
    """Neden: Uç 'bu aydan önce' ve 'en fazla 2 yıl geriye' doğrulaması yapıyor;
    sabit ay yazmak testi zamanla çürütürdü."""
    first_of_this_month = date.today().replace(day=1)
    prev = first_of_this_month - timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


class _RecordingJob:
    """Neden: Job'un GERÇEKTEN koşup koşmadığını kaydetmek (asıl iddia bu)."""

    calls = []

    def run(self, target_month=None):
        _RecordingJob.calls.append(target_month)
        return {"status": "SUCCESS", "report_path": "outputs/reports/x.xlsx"}


@pytest.fixture
def existing_report(monkeypatch):
    """Neden: Hem DB satırı hem rapor dosyası VAR — cache dalının tetiklendiği durum."""
    import app.database.settlement_repository as repo_mod
    import app.jobs.monthly_settlement_job as job_mod

    class _FakeRepo:
        def has_monthly_data(self, year, month):
            return True

        def get_monthly_report_path(self, year, month):
            return f"outputs/reports/{year:04d}-{month:02d}/mahsup_{year:04d}{month:02d}_aylik.xlsx"

    _RecordingJob.calls = []
    monkeypatch.setattr(repo_mod, "SettlementRepository", _FakeRepo)
    monkeypatch.setattr(job_mod, "MonthlySettlementJob", _RecordingJob)
    return _RecordingJob


def test_force_regenerates_even_when_report_exists(existing_report):
    """
    Neden (regresyon): Faturalama akışındaki "Raporu Yeniden Üret" butonu tam da
    raporun ZATEN var olduğu durumda basılır (OSB birim fiyatı girildikten
    sonra). Cache dalı yüzünden job hiç koşmuyor, uç success=true dönüyor ve
    arayüz "✓ Rapor yeniden üretildi." diyordu — tutarlar Excel'e hiç
    yansımıyordu.
    """
    month = _prev_month_str()
    h = _FakeHandler({"month": month, "force": True})
    h._handle_settlement_trigger_monthly_date()

    assert existing_report.calls == [month], "force=true iken job koşmalıydı"
    assert h.sent["error"] is None
    assert h.sent["data"]["status"] == "SUCCESS"
    assert h.sent["data"]["download_url"].endswith(month)


def test_without_force_cache_behaviour_is_preserved(existing_report):
    # Neden: "Geçmiş ay raporu üret" formu aynı ucu kullanıyor; oradaki cache
    # davranışı bilinçli ve korunmalı.
    month = _prev_month_str()
    h = _FakeHandler({"month": month})
    h._handle_settlement_trigger_monthly_date()

    assert existing_report.calls == [], "force yokken job koşmamalıydı"
    assert h.sent["data"]["status"] == "cached"


def test_force_runs_job_when_nothing_cached(monkeypatch):
    import app.database.settlement_repository as repo_mod
    import app.jobs.monthly_settlement_job as job_mod

    class _EmptyRepo:
        def has_monthly_data(self, year, month):
            return False

        def get_monthly_report_path(self, year, month):
            return None

    _RecordingJob.calls = []
    monkeypatch.setattr(repo_mod, "SettlementRepository", _EmptyRepo)
    monkeypatch.setattr(job_mod, "MonthlySettlementJob", _RecordingJob)

    month = _prev_month_str()
    h = _FakeHandler({"month": month, "force": True})
    h._handle_settlement_trigger_monthly_date()

    assert _RecordingJob.calls == [month]


def test_force_does_not_bypass_month_validation(existing_report):
    # Neden: force bir yetki/doğrulama kaçamağı değil, yalnızca cache'i atlar.
    h = _FakeHandler({"month": "gecersiz", "force": True})
    h._handle_settlement_trigger_monthly_date()

    assert h.sent["error"] is not None
    assert existing_report.calls == []


# ----------------------------------------------------------------------
# 5. Kilitli ay override (ADR-0002 kapsam dışıydı, ROADMAP açık maddesi)
# ----------------------------------------------------------------------
class _FakeOverrideService:
    """Neden: Endpoint sözleşmesini DB'siz sınamak; iş kuralı ayrı test ediliyor."""

    def __init__(self):
        self.calls = []

    def override_billing_month(self, **kw):
        self.calls.append(kw)
        return {
            "kind": "osb_unit_price_try",
            "old_value": "1.452381", "new_value": "1.380000",
            "previous_rate_id": 5,
            "old_invoice_try": "10748030.54", "new_invoice_try": "10748030.54",
            "old_deduction_try": "5162245.86", "new_deduction_try": "4904979.68",
            "reason": kw["reason"],
            "month_after": {"year": 2026, "month": 6, "status": STATUS_LOCKED},
        }


GECERLI_GEREKCE = "OSB Nisan faturasi revize edildi, birim fiyat dustu"


def _override_handler(body):
    h = _FakeHandler(body)
    h.service = _FakeOverrideService()
    return h


def test_override_yanlis_sifrede_401_dondurmez():
    """Yanlış yönetici şifresi oturum hatası değildir; kullanıcı formda kalmalı."""
    h = _override_handler({
        "admin_password": "yanlis", "osb_unit_price_try": "1.38",
        "reason": GECERLI_GEREKCE,
    })
    h._handle_billing_override("murat", "2026-06")

    assert h.sent["status"] != 401
    assert h.sent["error"] and "şifre" in h.sent["error"].lower()
    assert h.service.calls == [], "şifre geçmeden iş kuralına ulaşılmamalı"
    assert h.auth.actions[0]["action"] == "billing_override"
    assert h.auth.actions[0]["success"] is False


@pytest.mark.parametrize("osb,rate", [
    (None, None),           # hiçbiri
    ("1.38", "3.10"),       # ikisi birden
    ("", ""),               # boş string de "verilmemiş" sayılmalı
])
def test_override_tam_olarak_bir_katsayi_ister(osb, rate):
    h = _override_handler({
        "admin_password": ADMIN_PW, "osb_unit_price_try": osb,
        "excess_sale_rate_try": rate, "reason": GECERLI_GEREKCE,
    })
    h._handle_billing_override("murat", "2026-06")

    assert h.sent["status"] == 400
    assert "tam olarak bir" in h.sent["error"].lower()
    assert h.service.calls == []


def test_override_gecersiz_ay_formati_reddedilir():
    h = _override_handler({"admin_password": ADMIN_PW, "osb_unit_price_try": "1.38",
                           "reason": GECERLI_GEREKCE})
    h._handle_billing_override("murat", "2026/06")

    assert h.sent["status"] == 400
    assert h.service.calls == []


def test_override_basarili_akis_audit_json_yazar():
    """Rozet ve geçmiş bu JSON'dan türetiliyor; alan adları sabit kalmalı."""
    h = _override_handler({
        "admin_password": ADMIN_PW, "osb_unit_price_try": "1.380000",
        "reason": GECERLI_GEREKCE,
    })
    h._handle_billing_override("murat", "2026-06")

    assert h.sent["error"] is None
    assert h.sent["data"]["new_value"] == "1.380000"
    assert h.service.calls[0]["reason"] == GECERLI_GEREKCE
    assert h.service.calls[0]["changed_by"] == "murat"

    kayit = [a for a in h.auth.actions if a["action"] == "billing_override"]
    assert len(kayit) == 1 and kayit[0]["success"] is True
    detay = json.loads(kayit[0]["details"])
    for alan in ("year", "month", "kind", "old_value", "new_value", "reason"):
        assert alan in detay, f"audit JSON'unda {alan} yok — rozet bunu okuyor"
    assert detay["year"] == 2026 and detay["month"] == 6


def test_override_domain_hatasi_audit_ve_http_koduna_donusur():
    class _Exploding(_FakeOverrideService):
        def override_billing_month(self, **kw):
            raise BillingValidationError("Düzeltme gerekçesi en az 15 karakter olmalıdır")

    h = _FakeHandler({"admin_password": ADMIN_PW, "osb_unit_price_try": "1.38",
                      "reason": "kisa"})
    h.service = _Exploding()
    h._handle_billing_override("murat", "2026-06")

    assert h.sent["status"] == 400
    basarisiz = [a for a in h.auth.actions if a["success"] is False]
    assert basarisiz, "reddedilen override denetim izine yazılmalı"
