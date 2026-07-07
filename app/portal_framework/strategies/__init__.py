"""
Portal davranis stratejisi sozlesmeleri (Sprint AD-5A).

Neden: Login, gezinme, tarih secimi, export, polling, indirme ve ayristirma
davranislarini portal bagimsiz Strategy sozlesmeleri olarak tanimlamak.
Bu paket yalnizca abstract sozlesmeler ve StrategySet tasiyicisini icerir;
gercek portal implementasyonu (iSolar, GAOSB vb.) kapsam DISIDIR.
"""

from app.portal_framework.strategies.authentication_strategy import AuthenticationStrategy
from app.portal_framework.strategies.navigation_strategy import NavigationStrategy
from app.portal_framework.strategies.date_selection_strategy import DateSelectionStrategy
from app.portal_framework.strategies.export_strategy import ExportStrategy
from app.portal_framework.strategies.polling_strategy import PollingStrategy
from app.portal_framework.strategies.download_strategy import DownloadStrategy
from app.portal_framework.strategies.parsing_strategy import ParsingStrategy
from app.portal_framework.strategies.strategy_set import StrategySet

__all__ = [
    "AuthenticationStrategy",
    "NavigationStrategy",
    "DateSelectionStrategy",
    "ExportStrategy",
    "PollingStrategy",
    "DownloadStrategy",
    "ParsingStrategy",
    "StrategySet",
]
