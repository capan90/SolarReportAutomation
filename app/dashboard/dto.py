from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class ExecutiveSummaryDto:
    """
    Neden: Dashboard ana ekranındaki genel performans göstergelerini (KPI) 
    temsil eden veri transfer nesnesi (DTO).
    """
    success_rate: float
    failed_runs_count: int
    avg_duration_ms: float
    total_retries: int
    health_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class PipelineRunDto:
    """
    Neden: Geçmiş pipeline çalışmalarının özet bilgilerini temsil eden DTO.
    """
    run_id: str
    started_at: str
    duration_ms: int
    status: str
    exit_code: int
    issues_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class HealthStatusDto:
    """
    Neden: Sistem bileşenlerinin son sağlık durumlarını temsil eden DTO.
    """
    overall_status: str
    checks: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class MetricSeriesDto:
    """
    Neden: Zaman serisi grafiklerinde gösterilecek verileri temsil eden DTO.
    """
    metric_name: str
    timestamps: List[str]
    values: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class NotificationDto:
    """
    Neden: Bildirim geçmişi denetim kayıtlarını temsil eden DTO.
    """
    run_id: str
    sent_at: str
    status: str
    attempt_count: int
    recipient: str
    error_message: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
