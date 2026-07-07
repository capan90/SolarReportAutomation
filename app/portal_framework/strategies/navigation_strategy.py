"""
NavigationStrategy - hedef rapor/veri sayfasina gitme davranisinin sozlesmesi.

Neden: Kimi portal dogrudan URL ile, kimi menu tiklamalariyla, kimi SPA hash
routing ile gezinir. Gezinme bicimini adapter'dan ayirip degistirilebilir
bir sozlesmeye tasimak (SRP, OCP). Portala ozgu URL/selector icermez.
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.results import StepResult
from app.portal_framework.models.session_context import SessionContext


class NavigationStrategy(ABC):
    """
    Neden: 'Rapor ekranina nasil ulasilir?' sorusunu tek bir portal bagimsiz
    yontem arkasina almak.
    """

    @abstractmethod
    def navigate(self, ctx: SessionContext) -> StepResult:
        """
        Oturum acilmis bir baglamda hedef rapor/veri sayfasina gider.

        Implementasyon ctx.current_url gibi durum alanlarini guncelleyebilir;
        hata StepResult.fail ile raporlanir.
        """
