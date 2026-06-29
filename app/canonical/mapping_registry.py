import json
from dataclasses import asdict
from typing import Dict, List, Optional
from app.canonical.canonical_models import WorkbookMapping
from app.canonical.isolar.yield_report_mapping import isolar_yield_report_mapping

class MappingRegistry:
    """
    Neden: Farklı dosya veya API şablonlarına ait Canonical Mapping tanımlarını
    merkezi bir yerde kaydetmek, sorgulamak ve serileştirilmesini sağlamak.
    """
    def __init__(self):
        self._registry: Dict[str, WorkbookMapping] = {}
        # Varsayılan İsOlar Mapping Tanımını Yükle
        self.register_mapping("isolar_yield_report_v1", isolar_yield_report_mapping)

    def register_mapping(self, key: str, mapping: WorkbookMapping) -> None:
        """
        Neden: Kayıt defterine yeni bir mapping tanımı eklemek.
        """
        if key in self._registry:
            raise ValueError(f"Mapping zaten kayıtlı: {key}")
        self._registry[key] = mapping

    def get_mapping(self, key: str) -> Optional[WorkbookMapping]:
        """
        Neden: Verilen anahtara ait mapping tanımını getirmek.
        """
        return self._registry.get(key)

    def list_mappings(self) -> List[str]:
        """
        Neden: Kayıtlı tüm mapping anahtarlarını listelemek.
        """
        return list(self._registry.keys())

    def export_mapping_to_json(self, key: str) -> str:
        """
        Neden: Eşleme kural tanımını JSON olarak dışarı aktarmak.
        """
        mapping = self.get_mapping(key)
        if not mapping:
            raise KeyError(f"Kayıtlı mapping bulunamadı: {key}")
        
        mapping_dict = asdict(mapping)
        return json.dumps(mapping_dict, ensure_ascii=False, indent=2)
