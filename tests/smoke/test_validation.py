"""
Neden: SchemaValidator'ın profil↔şema karşılaştırma davranışını sabitlemek (smoke).
Tüm profil/şema nesneleri in-memory sentetiktir — Excel dosyası bile gerekmez.
validate() sonunda JSON raporu diske yazar; gerçek outputs/ dizini kirlenmesin
diye validator.reports_dir tmp_path'e yönlendirilir (kod değişmeden).
"""
import json

import pytest

from app.profiling.profile_models import ColumnProfile, SheetProfile, WorkbookProfile
from app.validation.engine.schema_validator import SchemaValidator
from app.validation.reports.severity import Severity
from app.validation.schemas.schema_models import (
    ColumnSchema, SchemaVersion, SheetSchema, WorkbookSchema,
)


def kolon_profili(name, inferred_type="float", null_count=0, non_null=10, unique=10):
    toplam = non_null + null_count
    return ColumnProfile(
        name=name, index=0, inferred_type=inferred_type,
        null_ratio=null_count / toplam if toplam else 0.0,
        non_null_count=non_null, null_count=null_count,
        unique_count=unique, sample_values=[],
    )


def sayfa_profili(columns, name="Veri", rows=10):
    return SheetProfile(
        name=name, total_rows=rows, total_columns=len(columns),
        header=[c.name for c in columns], used_range="A1:Z99",
        sheet_role="data", header_row_index=1, data_start_row_index=2,
        columns=columns,
    )


def profil(sheets):
    return WorkbookProfile(
        file_name="test.xlsx", file_path="test.xlsx", file_size_bytes=1,
        created_at="", modified_at="", total_sheets=len(sheets),
        sheet_names=[s.name for s in sheets], sheets=sheets,
    )


def kolon_semasi(name, aliases=None, required=True, expected_type="float",
                 nullable=True, unique=False):
    return ColumnSchema(
        name=name, aliases=aliases or [name], required=required,
        expected_type=expected_type, nullable=nullable, unique=unique,
        unit="", description="", example_value=None,
    )


def sema(columns, sheet_name="Veri", minimum_rows=1):
    return WorkbookSchema(
        name="test_schema",
        version_info=SchemaVersion(version="1.0.0", created_at="", author="", description=""),
        sheets=[SheetSchema(
            name=sheet_name, expected_role="data", minimum_rows=minimum_rows,
            minimum_columns=1, header_row=1, data_start_row=2, columns=columns,
        )],
    )


@pytest.fixture
def validator(tmp_path):
    v = SchemaValidator()
    v.reports_dir = tmp_path / "validation_reports"
    return v


def test_uyumlu_profil_success(validator):
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Uretim")])]),
        sema([kolon_semasi("Uretim")]),
    )
    assert report.status == "SUCCESS"
    assert report.summary.failed == 0
    assert report.summary.critical == 0


def test_eksik_sayfa_critical(validator):
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Uretim")], name="BaskaSayfa")]),
        sema([kolon_semasi("Uretim")], sheet_name="Veri"),
    )
    assert report.status == "FAILED"
    assert any(i.rule == "sheet_existence" and i.severity == Severity.CRITICAL
               for i in report.issues)


def test_eksik_kolon_severity_ayrimi(validator):
    # Zorunlu kolon eksik → CRITICAL, status FAILED
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Baska")])]),
        sema([kolon_semasi("Uretim", required=True)]),
    )
    assert report.status == "FAILED"
    assert any(i.rule == "required_column_missing" for i in report.issues)

    # Opsiyonel kolon eksik → INFO, status bozulmaz
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Uretim")])]),
        sema([kolon_semasi("Uretim"), kolon_semasi("Gelir", required=False)]),
    )
    assert report.status == "SUCCESS"
    assert any(i.rule == "optional_column_missing" and i.severity == Severity.INFO
               for i in report.issues)


def test_alias_eslesme_warning(validator):
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Toplam Üretim")])]),
        sema([kolon_semasi("Total yield(kWh)", aliases=["Total yield(kWh)", "Toplam Üretim"])]),
    )
    # Alias eşleşmesi WARNING üretir ama statüyü FAILED yapmaz
    assert report.status == "SUCCESS"
    assert any(i.rule == "column_matched_by_alias" and i.severity == Severity.WARNING
               for i in report.issues)


def test_tip_uyumlulugu(validator):
    assert validator._is_type_compatible("float", "float") is True
    assert validator._is_type_compatible("integer", "float") is True
    assert validator._is_type_compatible("integer", "decimal") is True
    assert validator._is_type_compatible("empty", "float") is True
    assert validator._is_type_compatible("text", "float") is False

    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Uretim", inferred_type="text")])]),
        sema([kolon_semasi("Uretim", expected_type="float")]),
    )
    assert report.status == "FAILED"
    assert any(i.rule == "column_type_mismatch" and i.severity == Severity.ERROR
               for i in report.issues)


def test_nullable_ve_unique_ihlalleri(validator):
    # non-nullable kolonda null → ERROR
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("Uretim", null_count=2, non_null=8)])]),
        sema([kolon_semasi("Uretim", nullable=False)]),
    )
    assert report.status == "FAILED"
    assert any(i.rule == "column_not_nullable_violation" for i in report.issues)

    # unique kolonda duplicate → ERROR
    report = validator.validate(
        profil([sayfa_profili([kolon_profili("SeriNo", non_null=10, unique=7)])]),
        sema([kolon_semasi("SeriNo", unique=True)]),
    )
    assert report.status == "FAILED"
    assert any(i.rule == "column_unique_violation" for i in report.issues)


def test_json_rapor_yazilir(validator):
    validator.validate(
        profil([sayfa_profili([kolon_profili("Uretim")])]),
        sema([kolon_semasi("Uretim")]),
    )
    rapor_dosyalari = list(validator.reports_dir.glob("validation_*.json"))
    assert len(rapor_dosyalari) == 1
    data = json.loads(rapor_dosyalari[0].read_text(encoding="utf-8"))
    assert data["status"] == "SUCCESS"
    assert data["schema_name"] == "test_schema"
