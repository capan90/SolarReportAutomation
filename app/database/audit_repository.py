import socket
import subprocess
from datetime import datetime, date
from typing import Optional, List

from app.core.logger import setup_logger
from app.database.db_session import SessionLocal
from app.database.models import EtlRun
from app.orchestrator.pipeline_result import PipelineResult
from app.cli.cli_models import CliArgs

logger = setup_logger("AuditRepository")


def _get_git_commit() -> Optional[str]:
    """
    Neden: Çalışan kodun hangi Git commit'ine ait olduğunu kaydetmek.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _count_severity(issues: List[str], keyword: str) -> int:
    """
    Neden: Issue listesindeki metinleri ayrıştırarak WARNING/ERROR/CRITICAL
    sayılarını tahmin etmek.
    """
    return sum(1 for i in issues if keyword.upper() in i.upper())


class AuditRepository:
    """
    Neden: Pipeline çalışma geçmişini (Run History) etl_runs tablosuna
    best-effort olarak kaydetmek. Audit yazılamazsa ana pipeline sonucunu
    FAILED yapmaz, yalnızca loglar.
    """

    def save_pipeline_result(
        self,
        result: PipelineResult,
        cli_args: Optional[CliArgs],
        exit_code: int
    ) -> bool:
        """
        Neden: PipelineResult, CLI argümanları ve çıkış kodunu birleştirerek
        etl_runs tablosuna tek bir audit kaydı yazmak.
        """
        session = SessionLocal()
        try:
            # Tarih çözümleme
            target_date_val = None
            if result.target_date:
                try:
                    target_date_val = datetime.strptime(result.target_date, "%Y-%m-%d").date()
                except ValueError:
                    target_date_val = None

            # Zaman damgası çözümleme
            started_at_dt = datetime.fromisoformat(result.started_at)
            finished_at_dt = datetime.fromisoformat(result.finished_at)

            # Severity sayıları
            issues_count = len(result.issues)
            warnings_count = _count_severity(result.issues, "WARNING")
            errors_count = _count_severity(result.issues, "ERROR") + _count_severity(result.issues, "HATA")
            critical_count = _count_severity(result.issues, "CRITICAL") + _count_severity(result.issues, "KRİTİK")

            etl_run = EtlRun(
                run_id=result.run_id,
                started_at=started_at_dt,
                finished_at=finished_at_dt,
                duration_ms=result.duration_ms,
                status=result.status,
                cli_mode=cli_args.mode if cli_args else "daily",
                target_date=target_date_val,
                source_file=result.source_file,
                profiling_file=result.profiling_file,
                validation_file=result.validation_file,
                transformed_file=result.transformed_file,
                inserted_records=result.inserted_records,
                updated_records=result.updated_records,
                skipped_stages=", ".join(result.skipped_stage) if result.skipped_stage else None,
                issues_count=issues_count,
                warnings_count=warnings_count,
                errors_count=errors_count,
                critical_count=critical_count,
                exit_code=exit_code,
                hostname=socket.gethostname(),
                git_commit=_get_git_commit()
            )

            session.add(etl_run)
            session.commit()
            logger.info(f"Audit kaydı başarıyla yazıldı. Run ID: {result.run_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.warning(f"Audit kaydı yazılamadı (best-effort): {e}")
            return False

        finally:
            session.close()
