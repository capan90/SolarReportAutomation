import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.sources import SourceRegistry, UnknownSourceError, DisabledSourceError
from app.database import create_tables, SessionLocal, EtlRun
from app.cli import CliArgs
from app.orchestrator.etl_orchestrator import ETLOrchestrator

def test_multi_source_framework():
    print("===== Multi Source Integration Architecture Testleri Başlatılıyor =====")
    
    # 1. Tabloların oluşturulduğundan emin ol
    create_tables()
    
    # 2. Registry testi
    print("\n[TEST 1] SourceRegistry Metotlarının Doğrulanması...")
    registry = SourceRegistry()
    
    # list_sources()
    sources = registry.list_sources()
    print(f"  - Kayıtlı Kaynaklar: {sources}")
    assert "isolarcloud" in sources, "isolarcloud kaynaklar arasında bulunmalı."
    
    # default_source()
    default_src = registry.default_source()
    print(f"  - Varsayılan Kaynak: {default_src}")
    assert default_src == "isolarcloud", "Varsayılan kaynak isolarcloud olmalı."
    
    # validate_source()
    assert registry.validate_source("isolarcloud") is True, "isolarcloud aktif olmalı."
    assert registry.validate_source("non-existent-source") is False, "Bilinmeyen kaynak pasif dönmeli."
    
    # source_capabilities()
    caps = registry.source_capabilities("isolarcloud")
    print(f"  - isolarcloud capabilities: {caps}")
    assert caps.get("supports_excel_export") is True, "Excel export yeteneği doğru okunmalı."
    
    print("  - [SUCCESS] SourceRegistry metotları başarıyla doğrulandı.")

    # 3. Hata Yönetimi (Exception Strategy)
    print("\n[TEST 2] Hata Yönetimi ve İstisna Fırlatma Testi...")
    
    # UnknownSourceError
    try:
        registry.get_source("non-existent-source")
        assert False, "UnknownSourceError fırlatılmalıydı."
    except UnknownSourceError as e:
        print(f"  - UnknownSourceError yakalandı (Başarılı): {e}")
        
    # DisabledSourceError (Yapay olarak devre dışı kaynak oluşturup çağır)
    mock_config_path = Path("config/sources.json").parent / "sources_test.json"
    mock_config = {
        "sources": {
            "disabled-test": {
                "extractor_class": "app.sources.isolarcloud.extractor.IsolarCloudExtractor",
                "enabled": False,
                "capabilities": {}
            }
        }
    }
    mock_config_path.write_text(json.dumps(mock_config), encoding="utf-8")
    
    test_registry = SourceRegistry(config_path=mock_config_path)
    try:
        test_registry.get_source("disabled-test")
        assert False, "DisabledSourceError fırlatılmalıydı."
    except DisabledSourceError as e:
        print(f"  - DisabledSourceError yakalandı (Başarılı): {e}")
    finally:
        if mock_config_path.exists():
            mock_config_path.unlink()
            
    print("  - [SUCCESS] İstisna hiyerarşisi başarıyla doğrulandı.")

    # 4. Pipeline Koşusu ve Audit Tablosu Entegrasyonu
    print("\n[TEST 3] Pipeline dry-run çalıştırma ve audit veritabanı source_name doğrulaması...")
    
    # Dry-run çalıştır (skip-download ile Playwright mocklanır)
    orchestrator = ETLOrchestrator()
    args = CliArgs(
        mode="dry-run",
        date=None,
        skip_download=True,
        skip_db_load=True,
        headless=True,
        source="isolarcloud"
    )
    result = orchestrator.run(args)
    print(f"  - Pipeline Sonucu: {result.status} (Run ID: {result.run_id})")
    
    # Audit repository'yi elle tetikleyip veritabanına yazalım
    from app.database.audit_repository import AuditRepository
    AuditRepository().save_pipeline_result(result, args, 0)
    
    # Veritabanından check edelim
    db = SessionLocal()
    try:
        run_record = db.query(EtlRun).filter(EtlRun.run_id == result.run_id).first()
        print(f"  - Veritabanına Yazılan source_name: '{run_record.source_name}'")
        assert run_record.source_name == "isolarcloud", "Veritabanındaki source_name 'isolarcloud' olmalı."
        print("  - [SUCCESS] Audit veritabanı source_name doğrulaması başarıyla tamamlandı.")
    finally:
        db.close()

    print("\n===== Tüm Multi Source Integration Testleri Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    test_multi_source_framework()
