"""
SessionContext - calisma durumu tasiyici (state carrier).

Neden: Tek bir extraction calismasinin tum runtime durumunu (kimlik, donem, adimlar,
indirmeler, hatalar, network log) global degisken yerine acikca dolasan tek bir nesnede
toplamak (ADR-005). Boylece test edilebilir ve paralel-guvenli olur.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from app.portal_framework.driver.browser_driver import BrowserDriver, NetworkRecord
from app.portal_framework.models.period import Period
from app.portal_framework.models.results import DownloadRecord, StepRecord, StepResult


class SessionHealth(str, Enum):
    """Calismanin genel saglik durumu."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


def _utcnow() -> datetime:
    """Neden: UTC zaman damgasini tek noktadan uretmek (tutarlilik)."""
    return datetime.now(timezone.utc)


@dataclass
class SessionContext:
    """
    Neden: Adapter ve stratejiler arasinda gezen, degisebilir (mutable) calisma durumu.
    Frozen DEGILDIR; cunku adimlar ilerledikce state guncellenir.
    """

    run_id: str
    portal_id: str
    driver: BrowserDriver
    period: Optional[Period] = None
    plant_id: Optional[str] = None
    plant_name: Optional[str] = None
    report_type: Optional[str] = None
    timezone: str = "Europe/Istanbul"
    locale: str = "tr-TR"

    authenticated: bool = False
    current_url: str = ""

    steps: List[StepRecord] = field(default_factory=list)
    downloads: List[DownloadRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    network_log: List[NetworkRecord] = field(default_factory=list)
    screenshots: List[Path] = field(default_factory=list)

    health: SessionHealth = SessionHealth.OK
    started_at: datetime = field(default_factory=_utcnow)

    def record_step(self, result: StepResult) -> None:
        """
        Neden: Calistirilan bir adimi denetim izine eklemek ve basarisizlikta
        saglik durumunu dusurmek.
        """
        self.steps.append(
            StepRecord(
                step_name=result.step_name,
                success=result.success,
                duration_ms=result.duration_ms,
                occurred_at=_utcnow(),
                error=result.error,
            )
        )
        if not result.success:
            self.health = SessionHealth.FAILED
            if result.error:
                self.errors.append(f"{result.step_name}: {result.error}")

    def add_download(self, record: DownloadRecord) -> None:
        self.downloads.append(record)

    def add_screenshot(self, path: Path) -> None:
        self.screenshots.append(path)

    def add_network_record(self, record: NetworkRecord) -> None:
        self.network_log.append(record)

    def last_step(self) -> Optional[StepRecord]:
        return self.steps[-1] if self.steps else None
