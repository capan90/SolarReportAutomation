import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.logger import setup_logger
from app.core.exceptions import IsolarError
from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.infrastructure.storage.archive_manager import ArchiveManager
from app.extractors.isolar.extractor import IsolarExtractor
from app.profiling.excel_profiler import ExcelProfiler
from app.validation.schemas.schema_registry import SchemaRegistry
from app.validation.engine.schema_validator import SchemaValidator
from app.transformation.yield_report_transformer import YieldReportTransformer
from app.database import create_tables, test_connection, DatabaseLoader
from app.orchestrator.pipeline_stage import PipelineStage
from app.orchestrator.pipeline_result import PipelineResult

logger = setup_logger("ETLOrchestrator")

class ETLOrchestrator:
    """
    Neden: Tüm ETL + Reporting akışını (Login, Navigation, Download, Archive,
    Profiling, Schema Validation, Transformation, Database Load) koordine etmek,
    hata durumlarında pipeline durdurma ve skip kurallarını işletmek ve tarayıcıyı
    güvenle sonlandırmak.
    """
    def __init__(self):
        self.profiles_dir = settings.download_directory.parent / "profiles"
        self.validation_dir = settings.download_directory.parent / "validation_reports"
        self.transformed_dir = settings.download_directory.parent / "transformed"

    def _get_newest_file(self, directory: Path, pattern: str) -> Optional[str]:
        """
        Neden: Aşamalar sonucunda oluşturulan en yeni çıktı dosyalarını tespit etmek.
        """
        if not directory.exists():
            return None
        files = list(directory.glob(pattern))
        if not files:
            return None
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return files[0].name

    def run(self) -> PipelineResult:
        logger.info("===== ETL Pipeline Başlatılıyor =====")
        start_time = datetime.now()
        
        stages: List[PipelineStage] = []
        skipped_stage: List[str] = []
        issues: List[str] = []
        
        # Dosya ve kayıt referansları
        source_file = None
        profiling_file = None
        validation_file = None
        transformed_file = None
        inserted_records = 0
        updated_records = 0

        # Kontrol durum bayrakları
        is_pipeline_aborted = False
        validation_failed = False
        transformation_failed = False

        # Nesneler
        archive_manager = ArchiveManager()
        profiler = ExcelProfiler()
        schema_registry = SchemaRegistry()
        validator = SchemaValidator()
        transformer = YieldReportTransformer()
        db_loader = DatabaseLoader()

        # Veritabanı tablolarının varlığından emin ol
        try:
            test_connection()
            create_tables()
        except Exception as e:
            logger.critical(f"Veritabanı başlatılamadı: {e}")
            is_pipeline_aborted = True
            issues.append(f"Veritabanı Başlatma Hatası: {e}")

        # Playwright ve Extractor Akışı
        temp_file_path = None
        final_file_path = None
        profile = None
        val_report = None
        trans_result = None

        with PlaywrightClient() as client:
            page = client.create_page()
            extractor = IsolarExtractor(page)

            # --- AŞAMA 1: Login ---
            stage_name = "Login"
            stage_start = datetime.now()
            logger.info(f"Aşama: {stage_name} başlatılıyor...")
            if is_pipeline_aborted:
                stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
                skipped_stage.append(stage_name)
            else:
                try:
                    settings.validate()
                    extractor.login_and_verify()
                    stages.append(PipelineStage(
                        name=stage_name,
                        status="SUCCESS",
                        started_at=stage_start.isoformat(),
                        finished_at=datetime.now().isoformat(),
                        duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                    ))
                except Exception as e:
                    is_pipeline_aborted = True
                    issues.append(f"Login Hatası: {e}")
                    stages.append(PipelineStage(
                        name=stage_name,
                        status="FAILED",
                        started_at=stage_start.isoformat(),
                        finished_at=datetime.now().isoformat(),
                        duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                        exception=str(e)
                    ))

            # --- AŞAMA 2: Navigation ---
            stage_name = "Navigation"
            stage_start = datetime.now()
            logger.info(f"Aşama: {stage_name} başlatılıyor...")
            if is_pipeline_aborted:
                stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
                skipped_stage.append(stage_name)
            else:
                try:
                    extractor.navigate_to_daily_report()
                    stages.append(PipelineStage(
                        name=stage_name,
                        status="SUCCESS",
                        started_at=stage_start.isoformat(),
                        finished_at=datetime.now().isoformat(),
                        duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                    ))
                except Exception as e:
                    is_pipeline_aborted = True
                    issues.append(f"Navigation Hatası: {e}")
                    stages.append(PipelineStage(
                        name=stage_name,
                        status="FAILED",
                        started_at=stage_start.isoformat(),
                        finished_at=datetime.now().isoformat(),
                        duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                        exception=str(e)
                    ))

            # --- AŞAMA 3: Download ---
            stage_name = "Download"
            stage_start = datetime.now()
            logger.info(f"Aşama: {stage_name} başlatılıyor...")
            if is_pipeline_aborted:
                stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
                skipped_stage.append(stage_name)
            else:
                try:
                    temp_file_path = extractor.download_daily_report()
                    stages.append(PipelineStage(
                        name=stage_name,
                        status="SUCCESS",
                        started_at=stage_start.isoformat(),
                        finished_at=datetime.now().isoformat(),
                        duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                    ))
                except Exception as e:
                    is_pipeline_aborted = True
                    issues.append(f"Download Hatası: {e}")
                    stages.append(PipelineStage(
                        name=stage_name,
                        status="FAILED",
                        started_at=stage_start.isoformat(),
                        finished_at=datetime.now().isoformat(),
                        duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                        exception=str(e)
                    ))

        # Tarayıcı kapandıktan sonra yerel işlem aşamaları

        # --- AŞAMA 4: Archive ---
        stage_name = "Archive"
        stage_start = datetime.now()
        logger.info(f"Aşama: {stage_name} başlatılıyor...")
        if is_pipeline_aborted:
            stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
            skipped_stage.append(stage_name)
        else:
            try:
                final_file_path = archive_manager.archive_raw_file(temp_file_path)
                source_file = final_file_path.name
                stages.append(PipelineStage(
                    name=stage_name,
                    status="SUCCESS",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                ))
            except Exception as e:
                is_pipeline_aborted = True
                issues.append(f"Archive Hatası: {e}")
                stages.append(PipelineStage(
                    name=stage_name,
                    status="FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                    exception=str(e)
                ))

        # --- AŞAMA 5: Profiling ---
        stage_name = "Profiling"
        stage_start = datetime.now()
        logger.info(f"Aşama: {stage_name} başlatılıyor...")
        if is_pipeline_aborted:
            stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
            skipped_stage.append(stage_name)
        else:
            try:
                profile = profiler.profile_file(final_file_path)
                profiling_file = self._get_newest_file(self.profiles_dir, "profile_*.json")
                stages.append(PipelineStage(
                    name=stage_name,
                    status="SUCCESS",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                ))
            except Exception as e:
                is_pipeline_aborted = True
                issues.append(f"Profiling Hatası: {e}")
                stages.append(PipelineStage(
                    name=stage_name,
                    status="FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                    exception=str(e)
                ))

        # --- AŞAMA 6: Validation ---
        stage_name = "Validation"
        stage_start = datetime.now()
        logger.info(f"Aşama: {stage_name} başlatılıyor...")
        if is_pipeline_aborted:
            stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
            skipped_stage.append(stage_name)
        else:
            try:
                schema = schema_registry.get_schema("isolar_yield_report")
                val_report = validator.validate(profile, schema, profiling_ref=profiling_file or "")
                validation_file = self._get_newest_file(self.validation_dir, "validation_*.json")
                
                if val_report.status.upper() != "SUCCESS":
                    validation_failed = True
                    issues.append(f"Şema Doğrulama Başarısız (FAILED): {validation_file}")
                    
                stages.append(PipelineStage(
                    name=stage_name,
                    status="SUCCESS" if not validation_failed else "FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                ))
            except Exception as e:
                is_pipeline_aborted = True
                issues.append(f"Validation Engine Hatası: {e}")
                stages.append(PipelineStage(
                    name=stage_name,
                    status="FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                    exception=str(e)
                ))

        # --- AŞAMA 7: Transformation ---
        stage_name = "Transformation"
        stage_start = datetime.now()
        logger.info(f"Aşama: {stage_name} başlatılıyor...")
        if is_pipeline_aborted or validation_failed:
            stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
            skipped_stage.append(stage_name)
        else:
            try:
                trans_result = transformer.transform(final_file_path, profile, val_report.status)
                transformed_file = self._get_newest_file(self.transformed_dir, "transformed_*.json")
                
                if trans_result.status.upper() != "SUCCESS":
                    transformation_failed = True
                    issues.append(f"Veri Dönüşümü Başarısız (FAILED): {transformed_file}")
                    
                stages.append(PipelineStage(
                    name=stage_name,
                    status="SUCCESS" if not transformation_failed else "FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                ))
            except Exception as e:
                is_pipeline_aborted = True
                issues.append(f"Transformation Engine Hatası: {e}")
                stages.append(PipelineStage(
                    name=stage_name,
                    status="FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                    exception=str(e)
                ))

        # --- AŞAMA 8: Database Load ---
        stage_name = "Database Load"
        stage_start = datetime.now()
        logger.info(f"Aşama: {stage_name} başlatılıyor...")
        if is_pipeline_aborted or validation_failed or transformation_failed:
            stages.append(PipelineStage(name=stage_name, status="SKIPPED"))
            skipped_stage.append(stage_name)
        else:
            try:
                load_result = db_loader.load(trans_result)
                inserted_records = load_result.inserted_plants + load_result.inserted_generations
                updated_records = load_result.updated_plants + load_result.updated_generations
                
                load_ok = load_result.status.upper() == "SUCCESS"
                if not load_ok:
                    issues.extend(load_result.issues)
                    
                stages.append(PipelineStage(
                    name=stage_name,
                    status="SUCCESS" if load_ok else "FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000)
                ))
            except Exception as e:
                issues.append(f"Database Load Hatası (ROLLBACK uygulandı): {e}")
                stages.append(PipelineStage(
                    name=stage_name,
                    status="FAILED",
                    started_at=stage_start.isoformat(),
                    finished_at=datetime.now().isoformat(),
                    duration_ms=int((datetime.now() - stage_start).total_seconds() * 1000),
                    exception=str(e)
                ))

        # --- SONUÇ RAPORU OLUŞTUR ---
        finished_time = datetime.now()
        total_duration_ms = int((finished_time - start_time).total_seconds() * 1000)
        
        # Pipeline genel durumunu belirle
        has_failed_stages = any(s.status == "FAILED" for s in stages)
        pipeline_status = "FAILED" if has_failed_stages else "SUCCESS"

        result = PipelineResult(
            status=pipeline_status,
            started_at=start_time.isoformat(),
            finished_at=finished_time.isoformat(),
            duration_ms=total_duration_ms,
            source_file=source_file,
            profiling_file=profiling_file,
            validation_file=validation_file,
            transformed_file=transformed_file,
            inserted_records=inserted_records,
            updated_records=updated_records,
            skipped_stage=skipped_stage,
            issues=issues,
            stages=stages
        )

        logger.info(f"===== ETL Pipeline Sonlandı. Durum: {pipeline_status}, Süre: {total_duration_ms} ms =====")
        return result
