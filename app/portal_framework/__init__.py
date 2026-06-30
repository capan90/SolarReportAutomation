"""
Portal Framework Foundation (Sprint AD-5)

Neden: iSolarCloud, GAOSB, SMA ve gelecekteki portallar (Huawei, Growatt, Fronius,
GoodWe) icin surdurulebilir, test edilebilir bir extraction framework cekirdegi saglamak.

Bu paket yalnizca framework seviyesindeki sozlesmeleri (interface + model) icerir.
Gercek portal adapter implementasyonlari (login, export) bu sprint kapsaminda DEGILDIR.

Mevcut app/sources/ ETL pipeline'i bu paketten bagimsizdir ve degistirilmemistir.
"""

from app.portal_framework.models import (
    Granularity,
    DateRange,
    Period,
    PortalCapability,
    CapabilitySet,
    StepResult,
    StepRecord,
    DownloadRecord,
    ExtractionResult,
    SelectorMap,
    TimeoutConfig,
    PortalDefinition,
    SessionContext,
    SessionHealth,
)
from app.portal_framework.driver import BrowserDriver, MockDriver, NetworkRecord, WaitState
from app.portal_framework.registry import PortalRegistry
from app.portal_framework.adapter import BasePortalAdapter, PortalRunner
from app.portal_framework.exceptions import (
    PortalFrameworkError,
    UnknownPortalError,
    PortalRegistrationError,
    UnsupportedCapabilityError,
    SelectorNotFoundError,
    DriverOperationError,
)

__all__ = [
    "Granularity",
    "DateRange",
    "Period",
    "PortalCapability",
    "CapabilitySet",
    "StepResult",
    "StepRecord",
    "DownloadRecord",
    "ExtractionResult",
    "SelectorMap",
    "TimeoutConfig",
    "PortalDefinition",
    "SessionContext",
    "SessionHealth",
    "BrowserDriver",
    "MockDriver",
    "NetworkRecord",
    "WaitState",
    "PortalRegistry",
    "BasePortalAdapter",
    "PortalRunner",
    "PortalFrameworkError",
    "UnknownPortalError",
    "PortalRegistrationError",
    "UnsupportedCapabilityError",
    "SelectorNotFoundError",
    "DriverOperationError",
]
