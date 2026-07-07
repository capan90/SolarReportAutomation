import re

from app.canonical.canonical_models import MappingField, WorkbookMapping

isolar_curve_mapping = WorkbookMapping(
    key="isolar_curve_v1",
    name="Isolar Hourly Curve Canonical Mapping",
    version="1.0.0",
    description="iSolarCloud Curve (saatlik üretim) raporu başlık eşleme kuralları.",
    mappings=[
        MappingField(
            source_column="Time",
            source_aliases=["Time", "Zaman", "Date/Time"],
            canonical_field="timestamp",
            entity="hourly_generation",
            target_db_column="timestamp",
            expected_type="datetime",
            unit="",
            nullable=False,
            required=True,
            transform_rule="parse_datetime",
            description="Saatlik ölçüm zaman damgası.",
            display_name_tr="Zaman",
        ),
    ],
)

# Neden: Curve raporundaki santral sütunları dinamiktir
# ("ERDEMSOFT-GES-8(97678)/Plant daily yield(kWh)" gibi); santral adı+ID kısmı
# değişken olduğundan sabit mapping yerine regex deseniyle çevrilir.
CURVE_HEADER_PATTERNS = [
    (
        re.compile(r"^(?P<plant>.+?)\s*/\s*Plant daily yield\s*\(kWh\)\s*$", re.IGNORECASE),
        lambda m: f"{m.group('plant').strip()} Günlük Üretim (kWh)",
    ),
]
