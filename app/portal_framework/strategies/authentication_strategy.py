"""
AuthenticationStrategy - portal oturum acma davranisinin sozlesmesi.

Neden: Login akisi portaldan portala degisir (form login, OAuth2, captcha,
oturum yeniden kullanimi). Bu farkliliklari adapter icine gommek yerine
degistirilebilir bir Strategy sozlesmesinin arkasina almak (OCP, DIP).

Bu modul yalnizca sozlesme icerir; portala ozgu URL, selector veya kimlik
bilgisi (credential/secret) detayi BARINDIRMAZ. Implementasyonlar bu
detaylari kendi konfigurasyon kaynagindan alir.
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.results import StepResult
from app.portal_framework.models.session_context import SessionContext


class AuthenticationStrategy(ABC):
    """
    Neden: 'Nasil oturum acilir?' sorusunu portal bagimsiz tek bir yontem
    arkasina toplamak; adapter yalnizca sozlesmeyi bilir (DIP).
    """

    @abstractmethod
    def authenticate(self, ctx: SessionContext) -> StepResult:
        """
        Oturum acmayi dener.

        Basari durumunda implementasyon ctx.authenticated bayragini
        guncellemekten sorumludur. Hata exception yerine StepResult.fail
        ile raporlanir (ADR-006 ile tutarli).
        """
