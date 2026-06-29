import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from app.orchestrator.pipeline_stage import PipelineStage

class PipelineResultJsonEncoder(json.JSONEncoder):
    """
    Neden: PipelineResult nesnelerindeki tarihleri ve diğer standart dışı nesneleri
    düzgün bir şekilde serileştirmek.
    """
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

@dataclass
class PipelineResult:
    """
    Neden: Uçtan uca tüm ETL akışının çıktısını, süresini, üretilen dosyaları,
    veritabanı istatistiklerini ve tüm aşamalardaki detayları bir arada raporlamak.
    """
    status: str  # 'SUCCESS' veya 'FAILED'
    started_at: str
    finished_at: str
    duration_ms: int
    source_file: Optional[str] = None
    profiling_file: Optional[str] = None
    validation_file: Optional[str] = None
    transformed_file: Optional[str] = None
    inserted_records: int = 0
    updated_records: int = 0
    skipped_stage: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    stages: List[PipelineStage] = field(default_factory=list)
    target_date: Optional[str] = None

    def to_json(self) -> str:
        """
        Neden: Pipeline sonuç raporunu standart JSON formatına serileştirmek.
        """
        result_dict = asdict(self)
        return json.dumps(result_dict, cls=PipelineResultJsonEncoder, ensure_ascii=False, indent=2)
