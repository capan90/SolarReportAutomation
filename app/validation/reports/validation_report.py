import json
from dataclasses import dataclass, field, asdict
from typing import List
from datetime import datetime
from app.validation.reports.validation_issue import ValidationIssue
from app.validation.reports.validation_summary import ValidationSummary
from app.validation.reports.severity import Severity

class ReportJsonEncoder(json.JSONEncoder):
    """
    Neden: ValidationReport ve alt dataclass'larındaki Severity Enum, datetime
    ve diğer standart dışı tipleri JSON formatına düzgünce serileştirmek.
    """
    def default(self, obj):
        if isinstance(obj, Severity):
            return obj.name
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

@dataclass(frozen=True)
class ValidationReport:
    """
    Neden: Bir Excel dosyasının şema doğrulama sonuçlarını tutan, durumunu (status),
    kullanılan şemayı, genel özeti ve tespit edilen tüm kuralsal ihlalleri içeren
    ve JSON formatına dönüştürülebilen resmi rapor modeli.
    """
    status: str
    schema_name: str
    schema_version: str
    file_name: str
    generated_at: str
    summary: ValidationSummary
    issues: List[ValidationIssue] = field(default_factory=list)
    profiling_reference: str = ""

    def to_json(self) -> str:
        """
        Neden: Rapor nesnesini JSON formatına serileştirmek.
        """
        report_dict = asdict(self)
        return json.dumps(report_dict, cls=ReportJsonEncoder, ensure_ascii=False, indent=2)
