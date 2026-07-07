"""
StrategySet - bir portalin davranis stratejilerini bir arada tasiyan deger nesnesi.

Neden: Bir portal adapter'inin ihtiyac duydugu davranislari (login, gezinme,
tarih secimi, export, polling, indirme, ayristirma) tek tek parametre gecirmek
yerine tip-guvenli tek bir pakette toplamak (composition over inheritance).

Alanlar bilincli olarak Optional'dir: her portal her stratejiye ihtiyac duymaz
(or. senkron export sunan portalda polling gerekmez). Hangi stratejilerin
zorunlu oldugu, kullanan tarafin (ileriki sprintlerde adapter entegrasyonu)
kararidir; bu sprint yalnizca sozlesmeleri tanimlar.
"""

from dataclasses import dataclass, fields
from typing import Optional, Tuple

from app.portal_framework.strategies.authentication_strategy import AuthenticationStrategy
from app.portal_framework.strategies.date_selection_strategy import DateSelectionStrategy
from app.portal_framework.strategies.download_strategy import DownloadStrategy
from app.portal_framework.strategies.export_strategy import ExportStrategy
from app.portal_framework.strategies.navigation_strategy import NavigationStrategy
from app.portal_framework.strategies.parsing_strategy import ParsingStrategy
from app.portal_framework.strategies.polling_strategy import PollingStrategy


@dataclass(frozen=True)
class StrategySet:
    """
    Neden: Strateji kombinasyonunu degismez (immutable) bir deger nesnesi olarak
    tasimak; adapter'a tek noktadan enjekte edilebilir (DIP).
    """

    authentication: Optional[AuthenticationStrategy] = None
    navigation: Optional[NavigationStrategy] = None
    date_selection: Optional[DateSelectionStrategy] = None
    export: Optional[ExportStrategy] = None
    polling: Optional[PollingStrategy] = None
    download: Optional[DownloadStrategy] = None
    parsing: Optional[ParsingStrategy] = None

    def missing(self) -> Tuple[str, ...]:
        """
        Neden: Atanmamis strateji alanlarini deterministik sirayla raporlamak;
        kullanan taraf zorunluluk kararini bu bilgiyle verebilir (fail-fast).
        """
        return tuple(f.name for f in fields(self) if getattr(self, f.name) is None)

    def is_complete(self) -> bool:
        """Tum strateji alanlari atanmis mi?"""
        return not self.missing()
