"""Portal Framework domain modelleri (deger nesneleri ve durum tasiyici)."""

from app.portal_framework.models.period import Granularity, DateRange, Period
from app.portal_framework.models.capability import PortalCapability, CapabilitySet
from app.portal_framework.models.results import (
    StepResult,
    StepRecord,
    DownloadRecord,
    ExtractionResult,
)
from app.portal_framework.models.portal_definition import (
    SelectorMap,
    TimeoutConfig,
    PortalDefinition,
)
from app.portal_framework.models.session_context import SessionContext, SessionHealth

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
]
