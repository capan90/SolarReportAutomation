import sys
from app.orchestrator import ETLOrchestrator

def run():
    """
    Neden: ETLOrchestrator üzerinden tüm login, download, validation, transformation
    ve veritabanı yükleme adımlarını koordine eden ana giriş fonksiyonu.
    """
    try:
        orchestrator = ETLOrchestrator()
        result = orchestrator.run()
        
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
        
        if result.issues:
            print("\nIssues / Errors:")
            for issue in result.issues:
                print(f"  - {issue}")
                
        if result.status.upper() == "FAILED":
            sys.exit(1)
            
    except Exception as e:
        print(f"Kritik çalıştırma hatası: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run()
