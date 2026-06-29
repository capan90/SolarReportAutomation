import json
from dataclasses import asdict
from typing import Dict, List, Optional
from app.validation.schemas.schema_models import WorkbookSchema
from app.validation.schemas.isolar.yield_report_schema import yield_report_workbook_schema

class SchemaRegistry:
    """
    Neden: Sistemde geçerli olan tüm veri şemalarını (Yield Report, Alarm Report vb.)
    merkezi bir noktada kaydetmek, sorgulamak ve yönetimini kolaylaştırmak.
    """
    def __init__(self):
        # Neden: Varsayılan şemaları başlangıçta otomatik olarak kaydetmek
        self._registry: Dict[str, WorkbookSchema] = {}
        self.register_schema("isolar_yield_report", yield_report_workbook_schema)

    def register_schema(self, key: str, schema: WorkbookSchema) -> None:
        """
        Neden: Kayıt defterine dinamik olarak yeni şemalar eklemek.
        """
        if key in self._registry:
            raise ValueError(f"Şema zaten kayıtlı: {key}")
        self._registry[key] = schema

    def get_schema(self, key: str) -> Optional[WorkbookSchema]:
        """
        Neden: Anahtara göre ilgili şema tanımını sorgulamak.
        """
        return self._registry.get(key)

    def list_schemas(self) -> List[str]:
        """
        Neden: Kayıtlı tüm şema anahtarlarını listelemek.
        """
        return list(self._registry.keys())

    def export_schema_to_json(self, key: str) -> str:
        """
        Neden: Belirtilen şemayı JSON formatına serileştirerek dış ortamlara
        (örn. validation, konfigurasyon servisleri) sunmak.
        """
        schema = self.get_schema(key)
        if not schema:
            raise KeyError(f"Kayıtlı şema bulunamadı: {key}")
        
        # dataclasses.asdict ile dictionary'e çevirip JSON olarak dön
        schema_dict = asdict(schema)
        return json.dumps(schema_dict, ensure_ascii=False, indent=2)
