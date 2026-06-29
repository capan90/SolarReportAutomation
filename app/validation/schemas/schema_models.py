from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class ColumnSchema:
    """
    Neden: Her bir kolon için beklenen veri tipi, isim alternatifleri (aliases),
    zorunluluk durumları, null olabilirlik ve iş mantığı açıklamalarını tutmak.
    """
    name: str
    aliases: List[str]
    required: bool
    expected_type: str
    nullable: bool
    unique: bool
    unit: str
    description: str
    example_value: Any

@dataclass(frozen=True)
class SheetSchema:
    """
    Neden: Sayfa (sheet) bazında beklenen rolü, minimum satır/kolon sınırlarını
    ve kolon şema tanımlarını tutmak.
    """
    name: str
    expected_role: str
    minimum_rows: int
    minimum_columns: int
    header_row: int
    data_start_row: int
    columns: List[ColumnSchema] = field(default_factory=list)

@dataclass(frozen=True)
class SchemaVersion:
    """
    Neden: Şemanın versiyon numarasını, oluşturulma tarihini ve yazarını
    izleyerek geriye dönük uyumluluk yönetimi sağlamak.
    """
    version: str
    created_at: str
    author: str
    description: str

@dataclass(frozen=True)
class WorkbookSchema:
    """
    Neden: Excel dosyasının (workbook) tamamı için şema versiyonunu,
    sayfa şemalarını ve genel açıklamaları bir arada tutmak.
    """
    name: str
    version_info: SchemaVersion
    sheets: List[SheetSchema] = field(default_factory=list)
