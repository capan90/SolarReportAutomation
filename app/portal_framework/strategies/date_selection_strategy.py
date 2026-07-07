"""
DateSelectionStrategy - donem/tarih secimi davranisinin sozlesmesi.

Neden: Tarih secimi portaldan portala degisir (takvim widget'i, dropdown,
URL parametresi, form alani). Donem kavrami zaten portal bagimsiz Period
modelinde tanimlidir; bu sozlesme yalnizca 'secilen Period portalda nasil
uygulanir?' sorusunu soyutlar (SRP).
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.period import Period
from app.portal_framework.models.results import StepResult
from app.portal_framework.models.session_context import SessionContext


class DateSelectionStrategy(ABC):
    """
    Neden: Donem uygulama detayini adapter'dan ayirmak; ayni portalin farkli
    rapor tipleri farkli tarih secim mekanizmalari kullanabilir.
    """

    @abstractmethod
    def select_period(self, ctx: SessionContext, period: Period) -> StepResult:
        """
        Verilen donemi (tarih araligi + granularite) portal arayuzunde uygular.

        Period parametre olarak acikca gecirilir; ctx.period'a ortulu bagimlilik
        kurulmaz (test edilebilirlik).
        """
