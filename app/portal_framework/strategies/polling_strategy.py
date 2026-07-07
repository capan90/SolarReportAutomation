"""
PollingStrategy - asenkron export'un hazir olmasini bekleme sozlesmesi.

Neden: Asenkron export sunan portallarda (POLLING_REQUIRED) isin tamamlanmasi
kuyruk/status ekranindan izlenir. Bekleme politikasini (neyin 'hazir' sayildigi)
adapter'dan ayirmak; senkron portallarda bu strateji hic kullanilmayabilir.

Bu modul yalnizca sozlesme icerir; somut bir polling dongusu/backoff
implementasyonu icermez.
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.results import StepResult
from app.portal_framework.models.session_context import SessionContext


class PollingStrategy(ABC):
    """
    Neden: 'Export ne zaman hazir?' sorusunu portal bagimsiz tek bir yontem
    arkasina almak. Zamanlama sinirlari PortalDefinition.timeouts uzerinden
    implementasyona saglanir; sozlesmeye gomulmez.
    """

    @abstractmethod
    def poll_until_ready(self, ctx: SessionContext) -> StepResult:
        """
        Tetiklenmis export isinin indirilebilir duruma gelmesini bekler.

        Zaman asimi veya kalici hata StepResult.fail ile raporlanir;
        exception firlatilmaz (ADR-006 ile tutarli).
        """
