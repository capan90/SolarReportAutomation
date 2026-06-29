from dataclasses import dataclass
from typing import Optional

@dataclass
class PipelineStage:
    """
    Neden: ETL boru hattındaki her bir adımın (Login, Download, Profiling vb.)
    başlangıç/bitiş zamanlarını, durumunu ve varsa oluşan istisnaları takip etmek.
    """
    name: str
    status: str = "PENDING"  # 'SUCCESS', 'FAILED', 'SKIPPED', 'PENDING'
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: int = 0
    exception: Optional[str] = None
    log: Optional[str] = None
