"""
PortalRegistry - portal tanim ve adapter kayit defteri.

Neden: Yeni portal eklemeyi framework kodu degistirmeden mumkun kilmak (ADR-007).
Bir PortalDefinition ve onu calistiracak adapter fabrikasi (factory) kaydedilir;
resolve() ile portal_id'den calistirilabilir adapter uretilir.
"""

from typing import Callable, Dict, List

from app.portal_framework.exceptions import (
    PortalRegistrationError,
    UnknownPortalError,
)
from app.portal_framework.models.capability import PortalCapability
from app.portal_framework.models.portal_definition import PortalDefinition

# Adapter fabrikasi: bir PortalDefinition alir, calistirilabilir adapter ornegi doner.
# (BasePortalAdapter'a dongusel import olmamasi icin tip ipucu genel tutuldu.)
AdapterFactory = Callable[[PortalDefinition], object]


class _Registration:
    """Tek bir portal kaydini (tanim + fabrika) tutan ic yapi."""

    __slots__ = ("definition", "factory")

    def __init__(self, definition: PortalDefinition, factory: AdapterFactory):
        self.definition = definition
        self.factory = factory


class PortalRegistry:
    """
    Neden: Kayitli portallari merkezi olarak yonetmek ve portal_id'den dogru
    adapteri cozumlemek (Registry pattern).
    """

    def __init__(self) -> None:
        self._registrations: Dict[str, _Registration] = {}

    def register(
        self,
        definition: PortalDefinition,
        factory: AdapterFactory,
    ) -> None:
        """
        Neden: Bir portali kayit etmek. Ayni portal_id iki kez kaydedilemez
        (sessiz uzerine yazmayi engelle - fail-fast).
        """
        portal_id = definition.portal_id
        if not portal_id:
            raise PortalRegistrationError("PortalDefinition.portal_id bos olamaz.")
        if portal_id in self._registrations:
            raise PortalRegistrationError(
                f"'{portal_id}' zaten kayitli. Mukerrer kayit engellendi."
            )
        if not callable(factory):
            raise PortalRegistrationError(
                f"'{portal_id}' icin adapter fabrikasi cagirilabilir olmalidir."
            )
        self._registrations[portal_id] = _Registration(definition, factory)

    def is_registered(self, portal_id: str) -> bool:
        return portal_id in self._registrations

    def get_definition(self, portal_id: str) -> PortalDefinition:
        """portal_id'ye karsilik gelen tanimi doner; yoksa UnknownPortalError."""
        if portal_id not in self._registrations:
            raise UnknownPortalError(portal_id)
        return self._registrations[portal_id].definition

    def resolve(self, portal_id: str) -> object:
        """
        Neden: portal_id'den calistirilabilir adapter ornegi uretmek. Adapter,
        kayitli fabrikaya tanim enjekte edilerek olusturulur (Dependency Injection).
        """
        if portal_id not in self._registrations:
            raise UnknownPortalError(portal_id)
        reg = self._registrations[portal_id]
        return reg.factory(reg.definition)

    def list_portals(self) -> List[str]:
        """Kayitli tum portal_id'leri doner (deterministik sirali)."""
        return sorted(self._registrations.keys())

    def list_by_capability(self, capability: PortalCapability) -> List[str]:
        """Belirli bir yetenegi destekleyen portallari doner."""
        return sorted(
            portal_id
            for portal_id, reg in self._registrations.items()
            if reg.definition.capabilities.supports(capability)
        )
