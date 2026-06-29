from dataclasses import dataclass, field
from typing import List, Any

@dataclass(frozen=True)
class ColumnProfile:
    """
    Neden: Her bir kolonun veri kalitesi, dağılımı ve veri tipi tahminlerini
    ayrı ayrı saklamak ve analiz etmek.
    """
    name: str
    index: int
    inferred_type: str
    null_ratio: float
    non_null_count: int
    null_count: int
    unique_count: int
    sample_values: List[Any]

@dataclass(frozen=True)
class DatasetSummary:
    """
    Neden: Tablo (sheet) düzeyinde genel veri yoğunluğu ve satır bazlı
    çoğulluk istatistiklerini temsil etmek.
    """
    total_rows: int
    total_columns: int
    estimated_size_bytes: int
    completely_empty_columns: List[str]
    completely_empty_rows: List[int]
    duplicate_rows_count: int

@dataclass(frozen=True)
class SheetProfile:
    """
    Neden: Tek bir sayfa (sheet) için yapısal bilgileri, başlık satırını,
    kullanılan hücre aralığını ve kolon bazlı profilleri saklamak.
    """
    name: str
    total_rows: int
    total_columns: int
    header: List[str]
    used_range: str
    sheet_role: str = "unknown"
    header_row_index: int = 1
    metadata_rows: List[List[Any]] = field(default_factory=list)
    data_start_row_index: int = 2
    columns: List[ColumnProfile] = field(default_factory=list)
    dataset_summary: DatasetSummary = None

@dataclass(frozen=True)
class WorkbookProfile:
    """
    Neden: Excel dosyasının (workbook) tamamına ait üst bilgileri,
    tüm sayfaları ve süreç boyunca tespit edilen şüpheli bulguları tutmak.
    """
    file_name: str
    file_path: str
    file_size_bytes: int
    created_at: str
    modified_at: str
    total_sheets: int
    sheet_names: List[str]
    sheets: List[SheetProfile] = field(default_factory=list)
    suspicious_findings: List[str] = field(default_factory=list)
