"""
ExportStrategy - rapor export'unu tetikleme davranisinin sozlesmesi.

Neden: Kimi portal senkron indirme sunar (SYNC_EXPORT), kimi export kuyruguna
is birakir (ASYNC_EXPORT). Tetikleme bicimini adapter'dan ayirip capability
modeliyle uyumlu, degistirilebilir bir sozlesmeye tasimak (OCP).
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.results import StepResult
from app.portal_framework.models.session_context import SessionContext


class ExportStrategy(ABC):
    """
    Neden: 'Export nasil baslatilir?' sorusunu portal bagimsiz tek bir yontem
    arkasina almak. Bekleme/indirme AYRI sozlesmelerdedir (SRP):
    PollingStrategy ve DownloadStrategy.
    """

    @abstractmethod
    def trigger_export(self, ctx: SessionContext) -> StepResult:
        """
        Secili rapor/donem icin export islemini baslatir.

        Asenkron portallarda yalnizca isi kuyruklar; hazir olmasini beklemek
        PollingStrategy'nin sorumlulugudur.
        """
