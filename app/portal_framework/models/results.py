"""
Sonuc (Result) ve kayit (Record) modelleri.

Neden: Pipeline'in her adiminin sonucunu (basari/hata) exception yerine acik deger
nesnesi olarak tasimak (ADR-006). Hangi adimda durulduguni kaybetmeden raporlamak.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional


@dataclass(frozen=True)
class StepResult:
    """
    Neden: Tek bir framework adiminin (login, navigate, export...) sonucunu
    standart ve degismez bir bicimde temsil etmek.
    """

    step_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: int = 0

    @classmethod
    def ok(cls, step_name: str, data: Any = None, duration_ms: int = 0) -> "StepResult":
        return cls(step_name=step_name, success=True, data=data, duration_ms=duration_ms)

    @classmethod
    def fail(cls, step_name: str, error: str, duration_ms: int = 0) -> "StepResult":
        return cls(step_name=step_name, success=False, error=error, duration_ms=duration_ms)


@dataclass(frozen=True)
class StepRecord:
    """
    Neden: SessionContext icinde calismis adimlarin denetim izini (audit trail)
    tutmak. StepResult'in zaman damgali, kalici kaydi.
    """

    step_name: str
    success: bool
    duration_ms: int
    occurred_at: datetime
    error: Optional[str] = None


@dataclass(frozen=True)
class DownloadRecord:
    """
    Neden: Indirilen her ham dosyanin kanitlanabilir meta verisini (provenance)
    tutmak. Dosya icerigi degil, yalnizca tanimlayici bilgiler.
    """

    file_path: Path
    original_name: str
    portal_id: str
    report_type: str
    downloaded_at: datetime
    size_bytes: int = 0
    file_format: Optional[str] = None


@dataclass(frozen=True)
class ExtractionResult:
    """
    Neden: Tum extraction workflow'unun nihai sonucunu, hangi adimda basarisiz
    oldugunu ve uretilen ciktilari tek bir nesnede toplamak.
    """

    success: bool
    portal_id: str
    run_id: str
    downloads: List[DownloadRecord] = field(default_factory=list)
    steps: List[StepRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    failed_at: Optional[str] = None

    @classmethod
    def success_result(
        cls,
        portal_id: str,
        run_id: str,
        downloads: Optional[List[DownloadRecord]] = None,
        steps: Optional[List[StepRecord]] = None,
    ) -> "ExtractionResult":
        return cls(
            success=True,
            portal_id=portal_id,
            run_id=run_id,
            downloads=list(downloads or []),
            steps=list(steps or []),
        )

    @classmethod
    def failure_result(
        cls,
        portal_id: str,
        run_id: str,
        failed_at: str,
        errors: Optional[List[str]] = None,
        steps: Optional[List[StepRecord]] = None,
    ) -> "ExtractionResult":
        return cls(
            success=False,
            portal_id=portal_id,
            run_id=run_id,
            failed_at=failed_at,
            errors=list(errors or []),
            steps=list(steps or []),
        )
