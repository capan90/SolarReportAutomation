from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class DailyProductionSummaryDto:
    date: str
    yield_kwh: float
    co2_reduction_kg: float
    revenue: float
    plant_name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class WeeklyProductionSummaryDto:
    week_number: int
    year: int
    yield_kwh: float
    plant_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class MonthlyProductionSummaryDto:
    year_month: str
    yield_kwh: float
    plant_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class MissingDayDto:
    date: str
    plant_name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class ProductionTrendDto:
    labels: List[str]
    values: List[float]
    direction: str  # INCREASING, DECREASING, FLAT
    change_percent: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class AnalyticsOverviewDto:
    total_yield_kwh: float
    avg_daily_yield_kwh: float
    peak_production_day: Optional[str]
    peak_production_kwh: float
    lowest_production_day: Optional[str]
    lowest_production_kwh: float
    missing_days_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
