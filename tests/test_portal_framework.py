"""
Sprint AD-5 - Portal Framework Foundation unit testleri.

Neden: Cekirdek framework sozlesmelerinin (driver, context, capability, registry,
adapter) gercek tarayici acmadan, deterministik ve hizli sekilde dogrulanmasi.
Pytest bagimliligi YOKTUR; stdlib unittest ile calisir.

Calistirma:
    .venv/Scripts/python.exe -m unittest tests.test_portal_framework -v
    veya
    .venv/Scripts/python.exe tests/test_portal_framework.py
"""

import sys
import unittest
from datetime import date
from pathlib import Path

# Proje kokunu path'e ekle (mevcut test konvansiyonu ile uyumlu).
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.portal_framework import (
    BasePortalAdapter,
    CapabilitySet,
    DateRange,
    ExtractionResult,
    Granularity,
    MockDriver,
    NetworkRecord,
    Period,
    PortalCapability,
    PortalDefinition,
    PortalRegistry,
    PortalRunner,
    SelectorMap,
    SessionContext,
    SessionHealth,
    StepResult,
    TimeoutConfig,
    WaitState,
)
from app.portal_framework.exceptions import (
    PortalRegistrationError,
    SelectorNotFoundError,
    UnknownPortalError,
    UnsupportedCapabilityError,
)


# --- Test yardimcilari ---

def _make_definition(portal_id="testportal", caps=None) -> PortalDefinition:
    if caps is None:
        caps = CapabilitySet.of(
            PortalCapability.SYNC_EXPORT,
            PortalCapability.EXCEL_EXPORT,
            PortalCapability.GENERATION_DATA,
        )
    return PortalDefinition(
        portal_id=portal_id,
        name="Test Portal",
        vendor="TestVendor",
        technology="MockTech",
        base_url="https://example.test",
        login_url="https://example.test/login",
        auth_type="credentials",
        nav_type="direct_url",
        capabilities=caps,
        selectors=SelectorMap({"login_button": "#login", "export": "#export"}),
        timeouts=TimeoutConfig(),
        supported_reports=["generation"],
        supported_exports=["excel"],
        supported_periods=[Granularity.DAILY],
    )


class _OkAdapter(BasePortalAdapter):
    """Tum adimlari varsayilan (no-op basari) birakan minimal adapter."""


class _DrivingAdapter(BasePortalAdapter):
    """Driver'i gercekten kullanan, akisi dogrulanabilir mock adapter."""

    def login(self, ctx: SessionContext) -> StepResult:
        ctx.driver.goto(self.definition.login_url)
        ctx.driver.fill(self.definition.selectors.get("login_button"), "user")
        ctx.authenticated = True
        return StepResult.ok("login")

    def trigger_export(self, ctx: SessionContext) -> StepResult:
        ctx.driver.click(self.definition.selectors.get("export"))
        return StepResult.ok("trigger_export")

    def await_download(self, ctx: SessionContext) -> StepResult:
        path = ctx.driver.wait_for_download()
        return StepResult.ok("await_download", data=str(path))


class _FailingAdapter(BasePortalAdapter):
    """'navigate' adiminda bilincli basarisiz olan adapter."""

    def navigate(self, ctx: SessionContext) -> StepResult:
        return StepResult.fail("navigate", "Rapor sayfasi bulunamadi")

    def trigger_export(self, ctx: SessionContext) -> StepResult:
        # Bu adim hic CALISMAMALI (navigate basarisiz oldugu icin).
        raise AssertionError("trigger_export, navigate basarisizken cagrildi!")


# --- 1. MockDriver ---

class TestMockDriver(unittest.TestCase):
    def test_records_calls(self):
        driver = MockDriver(current_url="https://start.test")
        driver.goto("https://a.test")
        driver.fill("#user", "deger")
        driver.click("#submit")
        self.assertEqual(driver.goto_urls, ["https://a.test"])
        self.assertEqual(driver.fills, [("#user", "deger")])
        self.assertEqual(driver.clicks, ["#submit"])
        self.assertTrue(driver.was_called("goto"))

    def test_current_url_follows_goto(self):
        driver = MockDriver(current_url="https://start.test")
        self.assertEqual(driver.current_url(), "https://start.test")
        driver.goto("https://next.test")
        self.assertEqual(driver.current_url(), "https://next.test")

    def test_wait_for_download_returns_fixture(self):
        driver = MockDriver(download_path=Path("rapor.xlsx"))
        self.assertEqual(driver.wait_for_download(), Path("rapor.xlsx"))

    def test_selector_fixture(self):
        driver = MockDriver(selector_results={"#yok": False})
        self.assertFalse(driver.wait_for_selector("#yok"))
        self.assertTrue(driver.wait_for_selector("#var", WaitState.VISIBLE))

    def test_fail_on_raises(self):
        from app.portal_framework.exceptions import DriverOperationError
        driver = MockDriver(fail_on=["click"])
        with self.assertRaises(DriverOperationError):
            driver.click("#x")

    def test_response_handler_observer(self):
        driver = MockDriver()
        seen = []
        driver.on_response(lambda rec: seen.append(rec))
        rec = NetworkRecord(url="https://api.test/v1", method="POST", status=200,
                            request_body_len=128, response_keys=["result_code"])
        driver.emit_response(rec)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].url, "https://api.test/v1")

    def test_close(self):
        driver = MockDriver()
        driver.close()
        self.assertTrue(driver.closed)


# --- 2. SessionContext step kaydi ---

class TestSessionContext(unittest.TestCase):
    def _ctx(self):
        return SessionContext(run_id="r1", portal_id="testportal", driver=MockDriver())

    def test_records_step(self):
        ctx = self._ctx()
        ctx.record_step(StepResult.ok("login", duration_ms=12))
        self.assertEqual(len(ctx.steps), 1)
        self.assertEqual(ctx.steps[0].step_name, "login")
        self.assertTrue(ctx.steps[0].success)
        self.assertEqual(ctx.steps[0].duration_ms, 12)
        self.assertIsNotNone(ctx.steps[0].occurred_at)

    def test_failed_step_degrades_health_and_collects_error(self):
        ctx = self._ctx()
        self.assertEqual(ctx.health, SessionHealth.OK)
        ctx.record_step(StepResult.fail("export", "buton yok"))
        self.assertEqual(ctx.health, SessionHealth.FAILED)
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("export", ctx.errors[0])

    def test_last_step(self):
        ctx = self._ctx()
        self.assertIsNone(ctx.last_step())
        ctx.record_step(StepResult.ok("a"))
        ctx.record_step(StepResult.ok("b"))
        self.assertEqual(ctx.last_step().step_name, "b")

    def test_network_log_helper(self):
        ctx = self._ctx()
        ctx.add_network_record(NetworkRecord(url="u", method="GET", status=200))
        self.assertEqual(len(ctx.network_log), 1)


# --- 3. CapabilitySet ---

class TestCapabilitySet(unittest.TestCase):
    def setUp(self):
        self.caps = CapabilitySet.of(
            PortalCapability.ASYNC_EXPORT,
            PortalCapability.EXCEL_EXPORT,
        )

    def test_supports(self):
        self.assertTrue(self.caps.supports(PortalCapability.ASYNC_EXPORT))
        self.assertFalse(self.caps.supports(PortalCapability.OBIS_CODES))

    def test_supports_all_any(self):
        self.assertTrue(self.caps.supports_all(
            PortalCapability.ASYNC_EXPORT, PortalCapability.EXCEL_EXPORT))
        self.assertFalse(self.caps.supports_all(
            PortalCapability.ASYNC_EXPORT, PortalCapability.OBIS_CODES))
        self.assertTrue(self.caps.supports_any(
            PortalCapability.OBIS_CODES, PortalCapability.EXCEL_EXPORT))

    def test_require_raises_on_missing(self):
        with self.assertRaises(UnsupportedCapabilityError):
            self.caps.require(PortalCapability.OBIS_CODES, "testportal")

    def test_require_passes_when_present(self):
        try:
            self.caps.require(PortalCapability.EXCEL_EXPORT, "testportal")
        except UnsupportedCapabilityError:
            self.fail("Desteklenen yetenek icin hata firlatilmamali.")

    def test_immutable(self):
        # frozen dataclass -> alan atamasi engellenmeli
        with self.assertRaises(Exception):
            self.caps.capabilities = frozenset()


# --- 4. PortalRegistry resolve ---

class TestPortalRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = PortalRegistry()
        self.definition = _make_definition("testportal")
        self.registry.register(self.definition, lambda d: _OkAdapter(d))

    def test_resolve_returns_adapter(self):
        adapter = self.registry.resolve("testportal")
        self.assertIsInstance(adapter, BasePortalAdapter)
        self.assertEqual(adapter.definition.portal_id, "testportal")

    def test_unknown_portal_raises(self):
        with self.assertRaises(UnknownPortalError):
            self.registry.resolve("yok")
        with self.assertRaises(UnknownPortalError):
            self.registry.get_definition("yok")

    def test_duplicate_registration_raises(self):
        with self.assertRaises(PortalRegistrationError):
            self.registry.register(self.definition, lambda d: _OkAdapter(d))

    def test_list_portals(self):
        self.registry.register(_make_definition("alpha"), lambda d: _OkAdapter(d))
        self.assertEqual(self.registry.list_portals(), ["alpha", "testportal"])

    def test_list_by_capability(self):
        obis_def = _make_definition(
            "gaosblike",
            caps=CapabilitySet.of(PortalCapability.OBIS_CODES, PortalCapability.METER_DATA),
        )
        self.registry.register(obis_def, lambda d: _OkAdapter(d))
        result = self.registry.list_by_capability(PortalCapability.OBIS_CODES)
        self.assertEqual(result, ["gaosblike"])
        result2 = self.registry.list_by_capability(PortalCapability.EXCEL_EXPORT)
        self.assertEqual(result2, ["testportal"])


# --- 5. BasePortalAdapter run + PortalRunner ---

class TestAdapterRun(unittest.TestCase):
    def _run(self, adapter_cls, portal_id="testportal", driver=None):
        registry = PortalRegistry()
        registry.register(_make_definition(portal_id), lambda d: adapter_cls(d))
        runner = PortalRunner(registry)
        driver = driver or MockDriver()
        period = Period(DateRange(date(2026, 6, 1), date(2026, 6, 30)), Granularity.DAILY)
        return runner.execute(portal_id, run_id="run-1", driver=driver, period=period), driver

    def test_ok_adapter_runs_all_steps(self):
        result, _ = self._run(_OkAdapter)
        self.assertIsInstance(result, ExtractionResult)
        self.assertTrue(result.success)
        self.assertIsNone(result.failed_at)
        # 8 adimin tamami kaydedilmis olmali
        self.assertEqual(len(result.steps), 8)
        self.assertTrue(all(s.success for s in result.steps))

    def test_driving_adapter_uses_driver(self):
        result, driver = self._run(_DrivingAdapter)
        self.assertTrue(result.success)
        # Driver gercekten cagrilmis mi?
        self.assertIn("https://example.test/login", driver.goto_urls)
        self.assertIn("#export", driver.clicks)
        self.assertTrue(driver.was_called("wait_for_download"))

    def test_failing_adapter_stops_pipeline(self):
        result, _ = self._run(_FailingAdapter)
        self.assertFalse(result.success)
        self.assertEqual(result.failed_at, "navigate")
        # navigate'e kadar 3 adim kaydedilmis (consent, login, navigate); sonrasi atlanmis
        recorded = [s.step_name for s in result.steps]
        self.assertEqual(recorded, ["consent", "login", "navigate"])
        self.assertTrue(len(result.errors) >= 1)

    def test_exception_in_step_is_caught(self):
        class _BoomAdapter(BasePortalAdapter):
            def login(self, ctx):
                raise RuntimeError("beklenmedik cokme")

        result, _ = self._run(_BoomAdapter)
        self.assertFalse(result.success)
        self.assertEqual(result.failed_at, "login")
        self.assertTrue(any("RuntimeError" in e for e in result.errors))


# --- 6. Deger nesnesi dogrulamalari ---

class TestValueObjects(unittest.TestCase):
    def test_daterange_rejects_inverted(self):
        with self.assertRaises(ValueError):
            DateRange(date(2026, 6, 30), date(2026, 6, 1))

    def test_daterange_days(self):
        dr = DateRange(date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual(dr.days, 30)

    def test_period_convenience_props(self):
        p = Period(DateRange(date(2026, 6, 1), date(2026, 6, 30)), Granularity.MONTHLY)
        self.assertEqual(p.start, date(2026, 6, 1))
        self.assertEqual(p.end, date(2026, 6, 30))

    def test_selectormap_missing_raises(self):
        sm = SelectorMap({"a": "#a"})
        self.assertEqual(sm.get("a"), "#a")
        self.assertTrue(sm.has("a"))
        with self.assertRaises(SelectorNotFoundError):
            sm.get("yok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
