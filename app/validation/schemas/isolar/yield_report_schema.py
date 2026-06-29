from datetime import datetime
from app.validation.schemas.schema_models import (
    ColumnSchema,
    SheetSchema,
    SchemaVersion,
    WorkbookSchema
)

# 1. Versiyon Bilgisi
yield_report_version = SchemaVersion(
    version="1.0.0",
    created_at="2026-06-29T12:00:00",
    author="ETL Data Architect",
    description="İsOlar Cloud Yield Report standard validation schema."
)

# 2. Kolon Şemaları
yield_report_columns = [
    ColumnSchema(
        name="Plant name",
        aliases=["Plant name", "Tesis Adı", "Station Name", "station name", "Plant name "],
        required=True,
        expected_type="text",
        nullable=False,
        unique=True,
        unit="",
        description="Güneş enerjisi tesisinin benzersiz adı.",
        example_value="ERDEMSOFT-GES-8"
    ),
    ColumnSchema(
        name="Installed power(kWp)",
        aliases=["Installed power(kWp)", "Installed power", "Kurulu Güç", "Güç"],
        required=True,
        expected_type="float",
        nullable=False,
        unique=False,
        unit="kWp",
        description="Tesisin kurulu DC panel gücü.",
        example_value=3900.0
    ),
    ColumnSchema(
        name="Grid connection date",
        aliases=["Grid connection date", "Şebeke Bağlantı Tarihi", "Kabul Tarihi"],
        required=True,
        expected_type="datetime",
        nullable=False,
        unique=False,
        unit="",
        description="Tesisin devreye alınma/kabul tarihi.",
        example_value="2026-06-04"
    ),
    ColumnSchema(
        name="Yield today (kWh)",
        aliases=["Yield today (kWh)", "Daily Yield", "Günlük Üretim", "Yield today(kWh)"],
        required=True,
        expected_type="float",
        nullable=False,
        unique=False,
        unit="kWh",
        description="Tesisin günlük toplam AC üretim miktarı.",
        example_value=23555.7
    ),
    ColumnSchema(
        name="Total yield(kWh)",
        aliases=["Total yield(kWh)", "Total Yield", "Toplam Üretim", "Total yield(kWh) "],
        required=True,
        expected_type="float",
        nullable=False,
        unique=False,
        unit="kWh",
        description="Devreye alındığından beri yapılan toplam kümülatif AC üretim.",
        example_value=624441.4
    ),
    ColumnSchema(
        name="Equivalent hours(h)",
        aliases=["Equivalent hours(h)", "Equivalent Hours", "Eşdeğer Çalışma Saati"],
        required=True,
        expected_type="float",
        nullable=False,
        unique=False,
        unit="h",
        description="Tesisin nominal güçte çalışarak bu üretimi yapması için gereken eşdeğer saat.",
        example_value=6.04
    ),
    ColumnSchema(
        name="Revenue today",
        aliases=["Revenue today", "Günlük Gelir", "Revenue"],
        required=False,
        expected_type="text",
        nullable=True,
        unique=False,
        unit="TRY",
        description="Tesisin günlük ürettiği enerjinin parasal karşılığı (para birimiyle birlikte).",
        example_value="23555.70(TRY)"
    ),
    ColumnSchema(
        name="Total CO₂ reduction(kg)",
        aliases=["Total CO₂ reduction(kg)", "CO2 Reduction", "Karbon Azaltımı"],
        required=True,
        expected_type="float",
        nullable=False,
        unique=False,
        unit="kg",
        description="Önlenen kümülatif CO2 salınım miktarı.",
        example_value=23485.03
    ),
    ColumnSchema(
        name="Plant address",
        aliases=["Plant address", "Tesis Adresi", "Address"],
        required=False,
        expected_type="text",
        nullable=True,
        unique=False,
        unit="",
        description="Tesisin fiziksel adresi/coğrafi konumu.",
        example_value="Elbeyli"
    ),
    ColumnSchema(
        name="Inverter S/N",
        aliases=["Inverter S/N", "Inverter Serial Number", "İnvertör Seri No"],
        required=False,
        expected_type="text",
        nullable=True,
        unique=False,
        unit="",
        description="Tesiste kullanılan invertörlerin seri numarası.",
        example_value="Inverter-12345"
    )
]

# 3. Sayfa Şeması
yield_report_sheet = SheetSchema(
    name="Yield report",
    expected_role="data",
    minimum_rows=3,
    minimum_columns=8,
    header_row=2,
    data_start_row=3,
    columns=yield_report_columns
)

# 4. Workbook Şeması
yield_report_workbook_schema = WorkbookSchema(
    name="Isolar Yield Report Schema",
    version_info=yield_report_version,
    sheets=[yield_report_sheet]
)
