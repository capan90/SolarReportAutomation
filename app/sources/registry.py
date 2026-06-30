import json
import importlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.sources.interface import ISourceExtractor
from app.sources.exceptions import (
    UnknownSourceError,
    DisabledSourceError,
    SourceConfigurationError
)
from app.core.config import BASE_DIR
from app.core.logger import setup_logger

logger = setup_logger("SourceRegistry")

class SourceRegistry:
    """
    Neden: config/sources.json dosyasından konfigürasyonu okuyarak dinamik sınıf 
    yükleme (reflection) yöntemiyle kaynak adaptörleri (extractors) oluşturmak ve yönetmek (SOLID - OCP).
    """
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (BASE_DIR / "config" / "sources.json")
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Yapılandırma dosyasını okur veya güvenli hata yönetimli boş fallback sağlar."""
        if not self.config_path.exists():
            logger.warning(f"Yapılandırma dosyası bulunamadı: {self.config_path}. Boş yapılandırma yükleniyor.")
            self._config = {"sources": {}}
            return
        try:
            self._config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise SourceConfigurationError(f"sources.json dosyası parse edilemedi: {e}")

    def list_sources(self) -> List[str]:
        """Tüm kayıtlı kaynak isimlerini döner."""
        return list(self._config.get("sources", {}).keys())

    def default_source(self) -> str:
        """Geriye dönük uyumluluk için varsayılan kaynağı döner."""
        sources = self.list_sources()
        if "isolarcloud" in sources:
            return "isolarcloud"
        return sources[0] if sources else ""

    def validate_source(self, name: str) -> bool:
        """Kaynağın varlığını ve aktiflik durumunu doğrular."""
        sources_cfg = self._config.get("sources", {})
        if name not in sources_cfg:
            return False
        return sources_cfg[name].get("enabled", False)

    def source_capabilities(self, name: str) -> Dict[str, bool]:
        """İlgili kaynağın desteklediği yetenekleri döner."""
        sources_cfg = self._config.get("sources", {})
        if name not in sources_cfg:
            raise UnknownSourceError(name)
        return sources_cfg[name].get("capabilities", {})

    def get_source(self, name: str) -> ISourceExtractor:
        """İsme karşılık gelen kaynak adaptörü sınıfını dinamik olarak yükler ve döner."""
        sources_cfg = self._config.get("sources", {})
        if name not in sources_cfg:
            raise UnknownSourceError(name)

        cfg = sources_cfg[name]
        if not cfg.get("enabled", False):
            raise DisabledSourceError(name)

        class_path = cfg.get("extractor_class")
        if not class_path:
            raise SourceConfigurationError(f"'{name}' kaynağı için 'extractor_class' tanımlanmamış.")

        try:
            # Örn: app.sources.isolarcloud.extractor.IsolarCloudExtractor -> Module & Class
            module_name, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            extractor_class = getattr(module, class_name)
            return extractor_class()
        except (ImportError, AttributeError) as e:
            raise SourceConfigurationError(f"Sınıf yükleme hatası ({class_path}): {e}")
