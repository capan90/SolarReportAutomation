from abc import ABC, abstractmethod
from pathlib import Path
from app.sources.models import SourceMetadata

class ISourceExtractor(ABC):
    """
    Neden: Farklı güneş paneli portallarından (isolarcloud, huawei, sma vb.) 
    rapor indirme adımlarını tekilleştiren temel arayüz tanımı (SOLID - DIP).
    """
    
    @property
    @abstractmethod
    def metadata(self) -> SourceMetadata:
        """Kaynağa ait değişmez üst verileri (name, capabilities vb.) döner."""
        pass

    @abstractmethod
    def download_report(self, output_dir: Path, **kwargs) -> Path:
        """
        Neden: Portaldan veya API'den günlük üretim raporunu indirerek
        lokal raw archive dosya yolunu dönmek.
        """
        pass
