from dataclasses import dataclass, field
from typing import List, Any

@dataclass(frozen=True)
class MappingField:
    """
    Neden: Ham kaynaktaki bir kolonun canonical alana, veritabanı kolonuna ve
    uygulanacak dönüşüm kurallarına (transformation rules) ait eşleme detaylarını saklamak.
    """
    source_column: str
    source_aliases: List[str]
    canonical_field: str
    entity: str  # 'solar_plant' veya 'daily_generation'
    target_db_column: str
    expected_type: str
    unit: str
    nullable: bool
    required: bool
    transform_rule: str
    description: str

@dataclass(frozen=True)
class WorkbookMapping:
    """
    Neden: Bir Excel dosyasının (workbook) tamamına ait eşleme tanımlarını,
    versiyonunu ve ilişkili MappingField listesini bir arada tutmak.
    """
    key: str
    name: str
    version: str
    description: str
    mappings: List[MappingField] = field(default_factory=list)
