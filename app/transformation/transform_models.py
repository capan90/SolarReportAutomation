import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, date

class TransformJsonEncoder(json.JSONEncoder):
    """
    Neden: TransformResult ve alt dataclass'larındaki datetime, date ve diğer
    standart dışı tipleri JSON formatına düzgünce serileştirmek.
    """
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

@dataclass(frozen=True)
class TransformIssue:
    """
    Neden: Dönüşüm sırasında karşılaşılan kuralsal/tip bazlı hataları
    satır, kolon ve alan bilgisiyle birlikte raporlamak.
    """
    row: Optional[int]
    column: Optional[str]
    field: Optional[str]
    rule: str
    message: str
    raw_value: Any

@dataclass(frozen=True)
class TransformedRecord:
    """
    Neden: Dönüştürülen her bir satırı veritabanı varlığına (entity) uygun
    şekilde canonical veri ve Excel kaynak satır numarası ile temsil etmek.
    """
    entity: str  # 'solar_plant' veya 'daily_generation'
    data: Dict[str, Any]
    source_row_number: int

@dataclass(frozen=True)
class TransformResult:
    """
    Neden: Dönüşüm sürecinin genel durumunu, istatistiklerini, üretilen kayıtları
    ve karşılaşılan tüm dönüşüm hatalarını tutan ana çıktı modeli.
    """
    status: str  # 'SUCCESS' veya 'FAILED'
    source_file: str
    mapping_key: str
    generated_at: str
    total_rows: int
    transformed_rows: int
    failed_rows: int
    records: List[TransformedRecord] = field(default_factory=list)
    issues: List[TransformIssue] = field(default_factory=list)

    def to_json(self) -> str:
        """
        Neden: Dönüşüm sonuç raporunu JSON formatında serileştirmek.
        """
        result_dict = asdict(self)
        return json.dumps(result_dict, cls=TransformJsonEncoder, ensure_ascii=False, indent=2)
