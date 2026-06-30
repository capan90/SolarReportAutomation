from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

class MetricType(Enum):
    """
    Neden: Gözlemlenebilirlik standartlarında (Prometheus vb.) kabul edilen 
    farklı metrik türlerini sınıflandırmak.
    """
    COUNTER = "COUNTER"
    GAUGE = "GAUGE"
    HISTOGRAM = "HISTOGRAM"
    TIMER = "TIMER"

@dataclass
class Metric:
    """
    Neden: Bir metrik değerini, türünü, zaman damgasını ve zengin boyutlarını (tag/label/dimension) 
    tekilleştiren ve taşıyan immutable veri modeli.
    """
    name: str
    value: float
    metric_type: MetricType
    category: str  # system, application, business, operational
    stage_name: Optional[str] = None
    dimensions: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

class IMetricExporter(ABC):
    """
    Neden: Toplanan metriklerin farklı ortamlara (Console, JSON, Database vb.) 
    aktarılması işlemlerini soyutlamak (SOLID - OCP & DIP).
    """
    @abstractmethod
    def export(self, metrics: List[Metric]) -> None:
        pass
