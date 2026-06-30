"""
Portal Framework istisna hiyerarsisi.

Neden: Framework seviyesindeki hatalari, programlama hatalarindan (AssertionError vb.)
ayri, yakalanabilir bir hiyerarsi altinda toplamak (Clean Architecture - acik hata sozlesmesi).
"""


class PortalFrameworkError(Exception):
    """Tum portal framework istisnalarinin temel sinifi."""


class UnknownPortalError(PortalFrameworkError):
    """Registry'de kayitli olmayan bir portal_id istendiginde firlatilir."""

    def __init__(self, portal_id: str):
        self.portal_id = portal_id
        super().__init__(f"Bilinmeyen portal: '{portal_id}'. Registry'de kayitli degil.")


class PortalRegistrationError(PortalFrameworkError):
    """Hatali veya cakisan portal kaydi yapildiginda firlatilir."""


class UnsupportedCapabilityError(PortalFrameworkError):
    """Bir portalin desteklemedigi bir yetenek talep edildiginde firlatilir."""

    def __init__(self, portal_id: str, capability: str):
        self.portal_id = portal_id
        self.capability = capability
        super().__init__(
            f"'{portal_id}' portali '{capability}' yetenegini desteklemiyor."
        )


class SelectorNotFoundError(PortalFrameworkError):
    """SelectorMap icinde tanimli olmayan bir selector anahtari istendiginde firlatilir."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Selector tanimli degil: '{key}'.")


class DriverOperationError(PortalFrameworkError):
    """Driver seviyesinde bir islem basarisiz oldugunda firlatilir."""
