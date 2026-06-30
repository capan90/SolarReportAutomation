"""
BasePortalAdapter - portal extraction akisinin sablon yontemi (Template Method).

Neden: Tum portallarda degismez olan adim sirasini (consent -> login -> navigate ->
configure -> export -> download -> validate -> post) merkezi olarak garanti etmek;
her adimin NASIL yapildigini alt sinifa/stratejiye birakmak (ADR-003).

Bu sprint kapsaminda gercek portal adapteri YAZILMAZ. Base adapter, varsayilan olarak
basarili (no-op) adimlar sunar; boylece MockDriver ile uctan uca akis dogrulanabilir.
"""

import time
from abc import ABC
from typing import Callable, List, Tuple

from app.portal_framework.models.portal_definition import PortalDefinition
from app.portal_framework.models.results import ExtractionResult, StepResult
from app.portal_framework.models.session_context import SessionContext


class BasePortalAdapter(ABC):
    """
    Neden: Adim sirasini sabitleyen, her adimi olcup SessionContext'e kaydeden ve
    ilk basarisizlikta akisi durduran cekirdek orkestrasyon.
    """

    # Adim sirasi: (adim_adi, metod_referansi_adi). Tek noktadan tanimli (DRY).
    _STEP_NAMES: Tuple[str, ...] = (
        "consent",
        "login",
        "navigate",
        "configure_period",
        "trigger_export",
        "await_download",
        "validate",
        "post_run",
    )

    def __init__(self, definition: PortalDefinition):
        self.definition = definition

    # --- Sablon yontemi (degistirilmemeli) ---

    def run(self, ctx: SessionContext) -> ExtractionResult:
        """
        Neden: Sabit adim sirasini calistirmak. Her adim olculur, ctx'e kaydedilir;
        bir adim basarisiz olursa kalan adimlar atlanir ve failure sonucu donulur.
        """
        steps: List[Tuple[str, Callable[[SessionContext], StepResult]]] = [
            ("consent", self.consent),
            ("login", self.login),
            ("navigate", self.navigate),
            ("configure_period", self.configure_period),
            ("trigger_export", self.trigger_export),
            ("await_download", self.await_download),
            ("validate", self.validate),
            ("post_run", self.post_run),
        ]

        for step_name, step_fn in steps:
            start = time.perf_counter()
            try:
                result = step_fn(ctx)
            except Exception as exc:  # Beklenmeyen hata: adim sinirinda yakalanir.
                duration_ms = int((time.perf_counter() - start) * 1000)
                result = StepResult.fail(step_name, f"{type(exc).__name__}: {exc}", duration_ms)

            # Adim adi tutarliligi: alt sinif yanlis isim donderse normalize et.
            if result.step_name != step_name:
                result = StepResult(
                    step_name=step_name,
                    success=result.success,
                    data=result.data,
                    error=result.error,
                    duration_ms=result.duration_ms,
                )

            ctx.record_step(result)
            if not result.success:
                return ExtractionResult.failure_result(
                    portal_id=ctx.portal_id,
                    run_id=ctx.run_id,
                    failed_at=step_name,
                    errors=list(ctx.errors),
                    steps=list(ctx.steps),
                )

        return ExtractionResult.success_result(
            portal_id=ctx.portal_id,
            run_id=ctx.run_id,
            downloads=list(ctx.downloads),
            steps=list(ctx.steps),
        )

    # --- Adim kancalari (hook) - alt sinif/stratejiler override eder ---
    # Neden: Varsayilanlar no-op basari; boylece minimal bir adapter MockDriver ile
    # uctan uca calisabilir ve gercek davranislar adim adim eklenebilir (Open/Closed).

    def consent(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("consent")

    def login(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("login")

    def navigate(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("navigate")

    def configure_period(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("configure_period")

    def trigger_export(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("trigger_export")

    def await_download(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("await_download")

    def validate(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("validate")

    def post_run(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("post_run")
