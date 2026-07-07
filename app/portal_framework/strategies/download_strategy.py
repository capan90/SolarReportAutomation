"""
DownloadStrategy - hazir dosyanin indirilmesi davranisinin sozlesmesi.

Neden: Indirme mekanizmasi portala gore degisir (dogrudan link, indirme ikonu,
tarayici download event'i). Indirme detayini adapter'dan ayirip dosya
provenance kaydini (DownloadRecord) standartlastirmak (SRP).
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.results import StepResult
from app.portal_framework.models.session_context import SessionContext


class DownloadStrategy(ABC):
    """
    Neden: 'Dosya nasil indirilir?' sorusunu portal bagimsiz tek bir yontem
    arkasina almak.
    """

    @abstractmethod
    def download(self, ctx: SessionContext) -> StepResult:
        """
        Hazir durumdaki export dosyasini indirir.

        Basarili implementasyon, indirilen dosyanin meta verisini
        DownloadRecord olarak ctx.add_download(...) ile kaydetmeli ve
        StepResult.data icinde tasiyabilmelidir.
        """
