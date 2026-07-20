"""
Neden: Canonical Layer'ın kayıt/sorgu davranışını ve mapping veri bütünlüğünü
sabitlemek (smoke). CLAUDE.md gereği Canonical koduna dokunulmaz — bu testler
yalnızca mevcut davranışı korur; bir değişiklik bu kuralları bozarsa hook'ta
yakalanır.
"""
import dataclasses
import json

import pytest

from app.canonical.canonical_models import MappingField, WorkbookMapping
from app.canonical.isolar.yield_report_mapping import isolar_yield_report_mapping
from app.canonical.mapping_registry import MappingRegistry

GECERLI_ENTITYLER = {"solar_plant", "daily_generation"}


@pytest.fixture
def registry():
    return MappingRegistry()


def alias_ile_bul(mapping: WorkbookMapping, alias: str) -> MappingField:
    """Alias'tan MappingField çözümü — adapter'ların yaptığı lookup'ın sadeleşmiş hali."""
    for field in mapping.mappings:
        if alias in field.source_aliases:
            return field
    raise AssertionError(f"Alias hiçbir mapping'e çözülemedi: {alias}")


def test_registry_varsayilan_mappingler(registry):
    assert set(registry.list_mappings()) == {"isolar_yield_report_v1", "isolar_curve_v1"}
    yield_mapping = registry.get_mapping("isolar_yield_report_v1")
    assert yield_mapping is isolar_yield_report_mapping
    assert yield_mapping.version == "1.0.0"


def test_registry_cift_kayit_hatasi(registry):
    # Canonical tanımının kazara ezilmesine karşı koruma
    with pytest.raises(ValueError):
        registry.register_mapping("isolar_yield_report_v1", isolar_yield_report_mapping)


def test_registry_bilinmeyen_key(registry):
    assert registry.get_mapping("olmayan_mapping") is None
    with pytest.raises(KeyError):
        registry.export_mapping_to_json("olmayan_mapping")


def test_export_json_yapisi(registry):
    raw = registry.export_mapping_to_json("isolar_yield_report_v1")
    data = json.loads(raw)
    assert data["key"] == "isolar_yield_report_v1"
    assert data["version"] == "1.0.0"
    assert len(data["mappings"]) == len(isolar_yield_report_mapping.mappings)
    # ensure_ascii=False: Türkçe karakterler escape'lenmeden korunur
    assert "Santral Adı" in raw
    assert "\\u" not in raw


@pytest.mark.parametrize(
    "alias,canonical_field",
    [
        ("Toplam Üretim", "total_yield_kwh"),
        ("Tesis Adı", "plant_name"),
        ("Kurulu Güç", "installed_power_kwp"),
        ("Günlük Üretim", "yield_today_kwh"),
    ],
)
def test_alias_esleme_lookup(alias, canonical_field):
    field = alias_ile_bul(isolar_yield_report_mapping, alias)
    assert field.canonical_field == canonical_field


def test_source_column_kendi_aliaslarinda():
    # Her alanın ana kolon adı kendi alias listesinde olmalı (birincil eşleşme garantisi)
    for field in isolar_yield_report_mapping.mappings:
        assert field.source_column in field.source_aliases, field.canonical_field


def test_mapping_veri_butunlugu():
    fields = isolar_yield_report_mapping.mappings
    canonical_adlari = [f.canonical_field for f in fields]
    assert len(canonical_adlari) == len(set(canonical_adlari)), "canonical_field tekrar ediyor"
    for field in fields:
        assert field.entity in GECERLI_ENTITYLER, field.canonical_field
        if field.required:
            assert field.nullable is False, f"required alan nullable olamaz: {field.canonical_field}"
    # Frozen dataclass: Canonical tanımı çalışma anında değiştirilemez
    with pytest.raises(dataclasses.FrozenInstanceError):
        fields[0].canonical_field = "degistirilemez"
