import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
from datetime import datetime
from app.monitoring.health.interface import HealthCheckResult

class HealthReportJsonEncoder(json.JSONEncoder):
    """
    Neden: Rapor çıktısındaki özel veri tiplerini (örn: datetime) JSON standartlarına dönüştürmek.
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

@dataclass
class HealthReport:
    """
    Neden: Tüm sağlık kontrolü adımlarının sonuçlarını konsolide eden
    ve geriye dönük uyumluluk için versiyon bilgisi taşıyan ana rapor veri modeli.
    """
    schema_version: str = "1.0.0"
    overall_status: str = "SUCCESS"  # SUCCESS, WARNING, FAILED
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    duration_ms: int = 0
    checks: List[HealthCheckResult] = field(default_factory=list)
    warnings: int = 0
    errors: int = 0

    def to_json(self) -> str:
        """
        Neden: Raporu standartlara uygun okunabilir JSON dizesine serileştirmek.
        """
        report_dict = asdict(self)
        return json.dumps(report_dict, cls=HealthReportJsonEncoder, ensure_ascii=False, indent=2)
