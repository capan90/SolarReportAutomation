import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.monitoring.metrics import get_default_registry, MetricsCollector, MetricType
from app.database import create_tables, SessionLocal, PerformanceMetric

def test_metrics_framework():
    print("===== Metrics & Observability Framework Testleri Başlatılıyor =====")
    
    # 1. Tabloların oluşturulduğundan emin ol
    create_tables()
    
    # 2. Registry ve Exporters yükle
    registry = get_default_registry()
    collector = MetricsCollector(registry)
    run_id = "test-metrics-uuid-777"
    
    # 3. Metrik Topla (Sistem, Aşamalar, İş kuralları, Operasyonel)
    print("\n[TEST 1] Metriklerin toplanması ve registry'ye kaydedilmesi...")
    
    # 3.1. Süreleri kaydet
    collector.record_pipeline_duration(run_id, 4500)
    collector.record_stage_duration(run_id, "Login", 1200)
    collector.record_stage_duration(run_id, "Download", 2300)
    
    # 3.2. Sistem metriklerini topla (cpu, mem, disk)
    collector.collect_system_metrics(run_id, "Post-Download")
    
    # 3.3. İş metriklerini kaydet
    collector.record_business_metrics(
        run_id=run_id,
        plant_count=3,
        imported_rows=150,
        validation_errors=2,
        duplicate_records=1
    )
    
    # 3.4. Operasyonel metrikleri kaydet
    collector.record_operational_metrics(run_id, is_failed=False)
    
    # 4. Flush ve Export
    print("\n[TEST 2] Exporter pipeline çalıştırma (Console, DB, JSON)...")
    registry.flush_and_export()
    
    # 5. Database kaydı sorgula
    print("\n[TEST 3] Veritabanından metriklerin doğrulanması...")
    db = SessionLocal()
    try:
        metrics = db.query(PerformanceMetric).filter(PerformanceMetric.run_id == run_id).all()
        print(f"  - Veritabanındaki Metrik Kaydı Sayısı: {len(metrics)}")
        
        # Temel metrik isimlerini eşleştir
        names = [m.metric_name for m in metrics]
        print(f"  - Kaydedilen Metrik İsimleri: {', '.join(names)}")
        
        assert len(metrics) > 0, "Metrikler veritabanına kaydedilmiş olmalıydı."
        assert "pipeline.duration" in names, "pipeline.duration bulunamadı."
        assert "pipeline.stage.duration" in names, "pipeline.stage.duration bulunamadı."
        assert "business.imported.rows" in names, "business.imported.rows bulunamadı."
        assert "health.score" in names, "health.score bulunamadı."
        
        print("  - [SUCCESS] Metriklerin veritabanına doğru şekilde yazıldığı doğrulandı.")
        
    finally:
        db.close()
        
    # 6. JSON Dosyasının doğrulanması
    print("\n[TEST 4] JSON arşiv dosyasının doğrulanması...")
    metrics_dir = Path("outputs/metrics")
    json_files = list(metrics_dir.glob("metrics_*.json"))
    print(f"  - Bulunan JSON metrik dosyası sayısı: {len(json_files)}")
    assert len(json_files) > 0, "JSON metrik dosyası oluşturulmuş olmalıydı."
    
    # En yeni dosyayı oku ve doğrula
    json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    latest_file = json_files[0]
    content = json.loads(latest_file.read_text(encoding="utf-8"))
    print(f"  - Dosya Adı: {latest_file.name} (Boyut: {len(content)} metrik)")
    assert len(content) > 0, "JSON dosyasının içi boş olmamalıydı."
    
    print("\n===== Tüm Gözlemlenebilirlik Testleri Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    test_metrics_framework()
