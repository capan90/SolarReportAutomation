import sys
import os
from pathlib import Path
from app.cli import parse_args
from app.orchestrator import ETLOrchestrator

LOCK_FILE = Path("outputs/runtime/etl.lock")

def run():
    """
    Neden: CLI komut parametrelerini alarak, lock file kontrolü altında
    ETLOrchestrator'ı tetiklemek ve çıkış kodlarını (exit codes) yönetmek.
    """
    # 1. CLI argümanlarını ayrıştır ve doğrula (Fail-Fast)
    try:
        args = parse_args()
    except Exception as e:
        print(f"CLI / Konfigürasyon Hatası: {e}")
        sys.exit(4)  # CONFIG_ERROR

    # 2. Lock file kontrolü (Uç uca çakışmaları engellemek)
    if LOCK_FILE.exists():
        print(f"Hata: İkinci bir ETL işlemi çalışamaz. Lock dosyası aktif: {LOCK_FILE}")
        sys.exit(3)  # LOCK_EXISTS

    # Lock dosyasını oluştur
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.touch()
    except Exception as e:
        print(f"Kritik Hata: Lock dosyası oluşturulamadı: {e}")
        sys.exit(1)  # FAILED

    try:
        # 3. Orchestrator tetikle
        orchestrator = ETLOrchestrator()
        result = orchestrator.run(args)
        
        # Konsola genel durumu yazdır
        print("\n===== Pipeline Run Result =====")
        print(f"Pipeline Status  : {result.status}")
        print(f"Total Duration   : {result.duration_ms} ms")
        print(f"Source File      : {result.source_file}")
        print(f"Profiling File   : {result.profiling_file}")
        print(f"Validation File  : {result.validation_file}")
        print(f"Transformed File : {result.transformed_file}")
        print(f"Database Stats   : Inserted={result.inserted_records}, Updated={result.updated_records}")
        print(f"Skipped Stages   : {', '.join(result.skipped_stage) if result.skipped_stage else 'None'}")
        if result.target_date:
            print(f"Target Date      : {result.target_date}")
        
        # Aşama detaylarına göre hata çıkış kodunu belirle
        validation_stage = next((s for s in result.stages if s.name == "Validation"), None)
        validation_failed = validation_stage and validation_stage.status == "FAILED"
        
        if result.issues:
            print("\nIssues / Errors:")
            for issue in result.issues:
                print(f"  - {issue}")
                
        if result.status.upper() == "FAILED":
            if validation_failed:
                sys.exit(2)  # VALIDATION_FAILED
            else:
                sys.exit(1)  # FAILED
        else:
            sys.exit(0)  # SUCCESS
            
    except Exception as e:
        print(f"Kritik çalıştırma hatası: {e}")
        sys.exit(1)  # FAILED
        
    finally:
        # 4. Hata olsa bile lock dosyası temizlenir
        if LOCK_FILE.exists():
            try:
                LOCK_FILE.unlink()
            except Exception as e:
                print(f"Lock dosyası temizlenirken hata oluştu: {e}")

if __name__ == "__main__":
    run()
