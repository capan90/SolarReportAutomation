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
    import uuid
    import signal
    from datetime import datetime
    start_time = datetime.now()
    args = None

    # Sinyal dinleyicileri kur (Graceful Shutdown için)
    def signal_handler(signum, frame):
        print(f"\n[Graceful Shutdown] Kapatma sinyali alındı ({signum}). Kaynaklar temizleniyor...")
        raise KeyboardInterrupt(f"Sinyal {signum} nedeniyle program kesildi.")
        
    try:
        signal.signal(signal.SIGINT, signal_handler)
    except ValueError:
        pass
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except ValueError:
        pass
    if hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, signal_handler)
        except ValueError:
            pass

    # 1. CLI argümanlarını ayrıştır ve doğrula (Fail-Fast)
    try:
        args = parse_args()
    except Exception as e:
        print(f"CLI / Konfigürasyon Hatası: {e}")
        try:
            from app.notifications import NotificationService
            NotificationService().notify_pipeline(
                run_id=str(uuid.uuid4()),
                exit_code=4,
                duration_ms=0,
                stage_summary=f"CLI / Konfigürasyon Hatası: {e}"
            )
        except Exception:
            pass
        sys.exit(4)  # CONFIG_ERROR

    # 1.5. Sağlık kontrolü modu (Komut çalıştırıldığında etl ve lock kontrollerini atla)
    if args and args.health:
        from app.monitoring.health.health_checker import HealthChecker
        try:
            checker = HealthChecker()
            report = checker.run_all()
            checker.print_summary(report)
            if report.overall_status == "FAILED":
                sys.exit(5)
            else:
                sys.exit(0)
        except Exception as he:
            print(f"Sağlık kontrolü çalıştırılırken kritik hata: {he}")
            sys.exit(5)

    if args and getattr(args, 'settlement_monthly', False):
        from app.jobs.monthly_settlement_job import MonthlySettlementJob
        try:
            job = MonthlySettlementJob()
            result = job.run(
                target_month=getattr(args, 'settlement_month', None)
            )
            print(f"Monthly Settlement Job: {result['status']}")
            print(f"Ay: {result['month']}")
            print(f"Rapor: {result['report_path']}")
            print(f"Mahsup satırı: {result['settlement_count']}")
            if result['error']:
                print(f"Hata: {result['error']}")
            sys.exit(0 if result['status'] == 'SUCCESS' else 1)
        except Exception as e:
            # Neden: Yakalanmamış istisna scheduled bağlamda stderr'e gidip kayboluyor
            # (2026-07-22 olayı) — kullanıcıya log kuyruklu uyarı maili atılır (best-effort).
            print(f"Monthly Settlement Job hatası: {e}")
            from app.notifications.system_alert import send_job_failure_alert
            send_job_failure_alert("Aylık Mahsup", str(e))
            sys.exit(1)

    if args and args.settlement:
        from app.jobs.daily_settlement_job import DailySettlementJob
        try:
            job = DailySettlementJob()
            result = job.run(
                target_date=getattr(args, 'settlement_date', None)
            )
            print(f"Settlement Job: {result['status']}")
            print(f"Tarih: {result['date']}")
            print(f"Rapor: {result['report_path']}")
            print(f"Mahsup satırı: {result['settlement_count']}")
            if result['error']:
                print(f"Hata: {result['error']}")
            sys.exit(0 if result['status'] == 'SUCCESS' else 1)
        except Exception as e:
            # Neden: Yakalanmamış istisna scheduled bağlamda stderr'e gidip kayboluyor
            # (2026-07-22 olayı) — kullanıcıya log kuyruklu uyarı maili atılır (best-effort).
            print(f"Settlement Job hatası: {e}")
            from app.notifications.system_alert import send_job_failure_alert
            send_job_failure_alert("Günlük Mahsup", str(e))
            sys.exit(1)

    if args and getattr(args, 'plant_status', False):
        from app.jobs.plant_status_job import PlantStatusJob
        import traceback
        try:
            job = PlantStatusJob()
            result = job.run()
            print(f"Plant Status Job: {result['status']}")
            if result.get('error'):
                print(f"Hata: {result['error']}")
            sys.exit(0 if result['status'] in ('SUCCESS', 'SKIPPED') else 1)
        except SystemExit:
            raise
        except BaseException as e:
            print(f"Plant Status Job hatası / kesinti (BaseException): {e}")
            traceback.print_exc()
            sys.exit(1)

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

    # 2.5. Startup Validation (Fail-Fast)
    # Kritik kontrolleri çalıştır (Database, Browser, Filesystem, Portal)
    from app.monitoring.health.health_checker import HealthChecker
    try:
        checker = HealthChecker()
        report = checker.run_all()
        
        if report.overall_status == "FAILED":
            print("\n[CRITICAL] Startup Validation FAILED! ETL Pipeline başlatılamıyor.")
            checker.print_summary(report)
            
            # Bildirim gönder
            try:
                from app.notifications import NotificationService
                NotificationService().notify_pipeline(
                    run_id=str(uuid.uuid4()),
                    exit_code=5,
                    duration_ms=report.duration_ms,
                    stage_summary=f"Startup Validation Başarısız Oldu. Genel Durum: {report.overall_status}",
                    validation_summary=f"Kritik sağlık kontrollerinden biri veya birkaçı başarısız oldu. Detaylar için health JSON raporunu inceleyin."
                )
            except Exception:
                pass

            # Metrikleri kaydet (best-effort)
            try:
                from app.monitoring.metrics import get_default_registry, MetricsCollector
                registry = get_default_registry()
                collector = MetricsCollector(registry)
                rid = str(uuid.uuid4())
                collector.record_operational_metrics(run_id=rid, is_failed=True, is_startup_failure=True)
                registry.flush_and_export()
            except Exception:
                pass
            
            # Lock dosyasını temizle
            if LOCK_FILE.exists():
                try:
                    LOCK_FILE.unlink()
                except Exception:
                    pass
            
            sys.exit(5)  # HEALTH_FAILED
    except Exception as ve:
        print(f"Startup Validation esnasında beklenmeyen hata: {ve}")
        # Lock dosyasını temizle
        if LOCK_FILE.exists():
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass
        sys.exit(5)

    exit_code = 1  # Varsayılan: FAILED
    result = None

    try:
        # 3. Orchestrator tetikle
        orchestrator = ETLOrchestrator()
        result = orchestrator.run(args)
        
        # Konsola genel durumu yazdır
        print("\n===== Pipeline Run Result =====")
        print(f"Run ID           : {result.run_id}")
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
                exit_code = 2  # VALIDATION_FAILED
            else:
                exit_code = 1  # FAILED
        else:
            exit_code = 0  # SUCCESS
            
    except Exception as e:
        print(f"Kritik çalıştırma hatası: {e}")
        exit_code = 1  # FAILED
        
    finally:
        # E-posta bildirimi gönder (best-effort)
        try:
            if args and not args.health:
                from app.notifications import NotificationService
                notifier = NotificationService()
                
                rid = result.run_id if result else str(uuid.uuid4())
                duration = result.duration_ms if result else int((datetime.now() - start_time).total_seconds() * 1000)
                
                issues_str = "\n".join(result.issues) if (result and result.issues) else ""
                stage_summary = f"Pipeline Sonucu: {result.status if result else 'CRITICAL ERROR'}\n{issues_str}"
                
                validation_summary = None
                if result:
                    validation_stage = next((s for s in result.stages if s.name == "Validation"), None)
                    if validation_stage and validation_stage.status == "FAILED":
                        validation_summary = f"Excel validation failed. Detaylar için validation raporuna bakınız."
                
                notifier.notify_pipeline(
                    run_id=rid,
                    exit_code=exit_code,
                    duration_ms=duration,
                    stage_summary=stage_summary,
                    validation_summary=validation_summary
                )
        except Exception as ne:
            print(f"Bildirim gönderilemedi (best-effort): {ne}")

        # Metrikleri topla ve dışa aktar (best-effort)
        try:
            if args and not args.health:
                from app.monitoring.metrics import get_default_registry, MetricsCollector
                registry = get_default_registry()
                collector = MetricsCollector(registry)
                
                rid = result.run_id if result else str(uuid.uuid4())
                duration = result.duration_ms if result else int((datetime.now() - start_time).total_seconds() * 1000)
                
                # 1. Pipeline ve Stage süreleri
                collector.record_pipeline_duration(rid, duration)
                if result:
                    for stage in result.stages:
                        if stage.status != "SKIPPED":
                            collector.record_stage_duration(rid, stage.name, stage.duration_ms)
                
                # 2. Sistem metrikleri (CPU/RAM/Disk)
                collector.collect_system_metrics(rid)
                
                # 3. Business metrikleri
                if result:
                    plant_count = 1 if result.inserted_records or result.updated_records else 0
                    imported_rows = result.inserted_records + result.updated_records
                    validation_stage = next((s for s in result.stages if s.name == "Validation"), None)
                    validation_errors = len(result.issues) if (validation_stage and validation_stage.status == "FAILED") else 0
                    
                    collector.record_business_metrics(
                        run_id=rid,
                        plant_count=plant_count,
                        imported_rows=imported_rows,
                        validation_errors=validation_errors,
                        duplicate_records=0
                    )
                
                # 4. Operasyonel metrikler
                is_failed = True if (exit_code != 0 and exit_code != 2) else False
                collector.record_operational_metrics(
                    run_id=rid,
                    is_failed=is_failed,
                    is_startup_failure=False
                )
                
                registry.flush_and_export()
                print("[INFO] Gözlemlenebilirlik metrikleri başarıyla işlendi.")
        except Exception as me:
            print(f"Metrikler toplanamadı (best-effort): {me}")

        # 4. Audit kaydı yaz (best-effort: başarısız olursa pipeline sonucunu değiştirmez)
        if result is not None:
            try:
                from app.database.audit_repository import AuditRepository
                audit = AuditRepository()
                audit.save_pipeline_result(result, args, exit_code)
            except Exception as e:
                print(f"Audit kaydı yazılamadı (best-effort): {e}")
        
        # 5. Hata olsa bile lock dosyası temizlenir
        if LOCK_FILE.exists():
            try:
                LOCK_FILE.unlink()
            except Exception as e:
                print(f"Lock dosyası temizlenirken hata oluştu: {e}")
        
        # Log bufferlarını temizle ve dosyaları serbest bırak
        try:
            import logging
            logging.shutdown()
        except Exception:
            pass
            
        sys.exit(exit_code)

if __name__ == "__main__":
    run()
