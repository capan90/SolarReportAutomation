from dataclasses import dataclass, field
from typing import List, Dict

@dataclass(frozen=True)
class SourceMetadata:
    """
    Neden: Bir veri kaynağını (iSolarCloud, Huawei vb.) ve onun 
    desteklediği yetenekleri (capabilities) tanımlayan değişmez (immutable) veri sınıfı.
    """
    source_name: str
    vendor: str
    version: str
    supported_report_types: List[str]
    authentication_type: str  # credentials, api_key, OAuth2
    capabilities: Dict[str, bool] = field(default_factory=dict)

@dataclass(frozen=True)
class SourceContext:
    """
    Neden: Pipeline veya veri sorguları boyunca hangi kaynaktan veri 
    akışı sağlandığı bilgisini (Context) taşımak.
    """
    source_name: str
    vendor: str
    version: str
    report_type: str
