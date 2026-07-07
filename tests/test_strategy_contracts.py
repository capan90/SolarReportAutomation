"""
Sprint AD-5A - Portal Strategy Contracts smoke testleri.

Neden: Strategy sozlesmelerinin ve StrategySet'in import edilebildigini,
bos veya mock stratejilerle olusturulabildigini dogrulamak. Gercek portal
davranisi test edilmez (bu sprintte implementasyon yoktur).

Calistirma:
    .venv/Scripts/python.exe -m unittest tests.test_strategy_contracts -v
    veya
    .venv/Scripts/python.exe tests/test_strategy_contracts.py
"""

import sys
import unittest
from pathlib import Path

# Proje kokunu path'e ekle (mevcut test konvansiyonu ile uyumlu).
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.portal_framework import (
    AuthenticationStrategy,
    DateSelectionStrategy,
    DownloadStrategy,
    ExportStrategy,
    NavigationStrategy,
    ParsingStrategy,
    PollingStrategy,
    StepResult,
    StrategySet,
)
from app.portal_framework.models.results import DownloadRecord
from app.portal_framework.models.period import Period
from app.portal_framework.models.session_context import SessionContext


# --- Mock stratejiler: yalnizca sozlesmeyi dolduran minimal implementasyonlar ---

class _MockAuth(AuthenticationStrategy):
    def authenticate(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("login")


class _MockNav(NavigationStrategy):
    def navigate(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("navigate")


class _MockDateSelection(DateSelectionStrategy):
    def select_period(self, ctx: SessionContext, period: Period) -> StepResult:
        return StepResult.ok("configure_period")


class _MockExport(ExportStrategy):
    def trigger_export(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("trigger_export")


class _MockPolling(PollingStrategy):
    def poll_until_ready(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("await_download")


class _MockDownload(DownloadStrategy):
    def download(self, ctx: SessionContext) -> StepResult:
        return StepResult.ok("await_download")


class _MockParsing(ParsingStrategy):
    def parse(self, ctx: SessionContext, download: DownloadRecord) -> StepResult:
        return StepResult.ok("validate")


class StrategySetTests(unittest.TestCase):
    def test_empty_strategy_set_construction(self):
        """Bos StrategySet olusturulabilmeli; tum alanlar eksik raporlanmali."""
        strategy_set = StrategySet()
        self.assertFalse(strategy_set.is_complete())
        self.assertEqual(
            strategy_set.missing(),
            (
                "authentication",
                "navigation",
                "date_selection",
                "export",
                "polling",
                "download",
                "parsing",
            ),
        )

    def test_full_strategy_set_with_mock_strategies(self):
        """Mock stratejilerle dolu StrategySet olusturulabilmeli ve tam sayilmali."""
        strategy_set = StrategySet(
            authentication=_MockAuth(),
            navigation=_MockNav(),
            date_selection=_MockDateSelection(),
            export=_MockExport(),
            polling=_MockPolling(),
            download=_MockDownload(),
            parsing=_MockParsing(),
        )
        self.assertTrue(strategy_set.is_complete())
        self.assertEqual(strategy_set.missing(), ())

    def test_abstract_contracts_cannot_be_instantiated(self):
        """Sozlesmeler abstract'tir; dogrudan ornek olusturma TypeError vermeli."""
        for contract in (
            AuthenticationStrategy,
            NavigationStrategy,
            DateSelectionStrategy,
            ExportStrategy,
            PollingStrategy,
            DownloadStrategy,
            ParsingStrategy,
        ):
            with self.assertRaises(TypeError, msg=contract.__name__):
                contract()  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main(verbosity=2)
