import re
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import asdict

from app.core.config import settings
from app.core.logger import setup_logger
from app.core.exceptions import IsolarError
from app.profiling.profile_models import WorkbookProfile, SheetProfile, ColumnProfile
from app.validation.schemas.schema_models import WorkbookSchema, SheetSchema, ColumnSchema
from app.validation.reports.severity import Severity
from app.validation.reports.validation_issue import ValidationIssue
from app.validation.reports.validation_summary import ValidationSummary
from app.validation.reports.validation_report import ValidationReport

logger = setup_logger("SchemaValidator")

class SchemaValidator:
    """
    Neden: Profil raporu (WorkbookProfile) ile şema kaydı (WorkbookSchema) verilerini
    karşılaştırarak şema uyumluluğunu, eksik kolonları, tip uyuşmazlıklarını ve
    null/tekillik ihlallerini bulup standart bir rapor halinde kaydetmek.
    """
    def __init__(self):
        self.reports_dir = settings.download_directory.parent / "validation_reports"

    def ensure_reports_directory(self) -> None:
        """
        Neden: Doğrulama raporlarının kaydedileceği dizinin varlığından emin olmak.
        """
        if not self.reports_dir.exists():
            logger.info(f"Doğrulama rapor dizini oluşturuluyor: {self.reports_dir}")
            self.reports_dir.mkdir(parents=True, exist_ok=True)

    def validate(self, profile: WorkbookProfile, schema: WorkbookSchema, profiling_ref: str = "") -> ValidationReport:
        """
        Neden: Profil ve Şemayı karşılaştırarak tüm doğrulama kurallarını işletmek.
        """
        logger.info(f"Şema doğrulaması başlatılıyor. Dosya: {profile.file_name}, Şema: {schema.name}")
        
        start_time = datetime.now()
        issues: List[ValidationIssue] = []
        
        # Toplam kontrollerin sayacı
        total_checks = 0
        passed_checks = 0

        # Helper: Kontrol kaydetmek için
        def add_check(passed: bool):
            nonlocal total_checks, passed_checks
            total_checks += 1
            if passed:
                passed_checks += 1

        # 1. Chart Sayfalarını Atla (INFO)
        for sheet_p in profile.sheets:
            if sheet_p.sheet_role == "chart":
                add_check(True)
                issues.append(
                    ValidationIssue(
                        sheet=sheet_p.name,
                        column=None,
                        row=None,
                        rule="sheet_role_skip",
                        severity=Severity.INFO,
                        expected="chart role",
                        actual="skipped",
                        message=f"Chart sheet '{sheet_p.name}' is skipped from validation.",
                        timestamp=datetime.now().isoformat()
                    )
                )

        # 2. Sayfa Seviyesi Kontroller (Sheet Checks)
        for sheet_s in schema.sheets:
            # Profil içinde şema sayfasını bul
            sheet_p = next((s for s in profile.sheets if s.name.lower() == sheet_s.name.lower()), None)
            
            # Sayfa yoksa (CRITICAL)
            if not sheet_p:
                add_check(False)
                issues.append(
                    ValidationIssue(
                        sheet=sheet_s.name,
                        column=None,
                        row=None,
                        rule="sheet_existence",
                        severity=Severity.CRITICAL,
                        expected=f"Sheet '{sheet_s.name}' exists",
                        actual="Not found",
                        message=f"Expected data sheet '{sheet_s.name}' is missing in the workbook.",
                        timestamp=datetime.now().isoformat()
                    )
                )
                continue

            add_check(True)

            # Sayfa Rolü Kontrolü (WARNING)
            role_match = sheet_p.sheet_role == sheet_s.expected_role
            add_check(role_match)
            if not role_match:
                issues.append(
                    ValidationIssue(
                        sheet=sheet_p.name,
                        column=None,
                        row=None,
                        rule="sheet_role_match",
                        severity=Severity.WARNING,
                        expected=sheet_s.expected_role,
                        actual=sheet_p.sheet_role,
                        message=f"Sheet role mismatch for '{sheet_p.name}'. Expected '{sheet_s.expected_role}', found '{sheet_p.sheet_role}'.",
                        timestamp=datetime.now().isoformat()
                    )
                )

            # Minimum Satır Kontrolü (ERROR)
            rows_ok = sheet_p.total_rows >= sheet_s.minimum_rows
            add_check(rows_ok)
            if not rows_ok:
                issues.append(
                    ValidationIssue(
                        sheet=sheet_p.name,
                        column=None,
                        row=None,
                        rule="minimum_rows_limit",
                        severity=Severity.ERROR,
                        expected=f">= {sheet_s.minimum_rows}",
                        actual=sheet_p.total_rows,
                        message=f"Sheet '{sheet_p.name}' row count ({sheet_p.total_rows}) is below minimum limit ({sheet_s.minimum_rows}).",
                        timestamp=datetime.now().isoformat()
                    )
                )

            # Minimum Kolon Kontrolü (ERROR)
            cols_ok = sheet_p.total_columns >= sheet_s.minimum_columns
            add_check(cols_ok)
            if not cols_ok:
                issues.append(
                    ValidationIssue(
                        sheet=sheet_p.name,
                        column=None,
                        row=None,
                        rule="minimum_columns_limit",
                        severity=Severity.ERROR,
                        expected=f">= {sheet_s.minimum_columns}",
                        actual=sheet_p.total_columns,
                        message=f"Sheet '{sheet_p.name}' column count ({sheet_p.total_columns}) is below minimum limit ({sheet_s.minimum_columns}).",
                        timestamp=datetime.now().isoformat()
                    )
                )

            # Header Row Konum Kontrolü
            header_row_ok = sheet_p.header_row_index == sheet_s.header_row
            add_check(header_row_ok)
            if not header_row_ok:
                issues.append(
                    ValidationIssue(
                        sheet=sheet_p.name,
                        column=None,
                        row=None,
                        rule="header_row_index_match",
                        severity=Severity.WARNING,
                        expected=sheet_s.header_row,
                        actual=sheet_p.header_row_index,
                        message=f"Header row index mismatch for '{sheet_p.name}'. Expected {sheet_s.header_row}, found {sheet_p.header_row_index}.",
                        timestamp=datetime.now().isoformat()
                    )
                )

            # Data Start Row Konum Kontrolü
            data_start_ok = sheet_p.data_start_row_index == sheet_s.data_start_row
            add_check(data_start_ok)
            if not data_start_ok:
                issues.append(
                    ValidationIssue(
                        sheet=sheet_p.name,
                        column=None,
                        row=None,
                        rule="data_start_row_match",
                        severity=Severity.WARNING,
                        expected=sheet_s.data_start_row,
                        actual=sheet_p.data_start_row_index,
                        message=f"Data start row index mismatch for '{sheet_p.name}'. Expected {sheet_s.data_start_row}, found {sheet_p.data_start_row_index}.",
                        timestamp=datetime.now().isoformat()
                    )
                )

            # 3. Kolon Seviyesi Kontroller (Column Checks)
            matched_profile_cols = set()

            for col_s in sheet_s.columns:
                # Kolonu canonical name veya alias üzerinden bul
                col_p = None
                matched_by_alias = False
                
                for cp in sheet_p.columns:
                    # Canonical eşleşme
                    if cp.name.strip().lower() == col_s.name.strip().lower():
                        col_p = cp
                        break
                    # Alias eşleşmesi
                    if any(alias.strip().lower() == cp.name.strip().lower() for alias in col_s.aliases):
                        col_p = cp
                        matched_by_alias = True
                        break

                # Kolon Bulunamadı Kontrolü (Required -> CRITICAL, Optional -> INFO)
                if not col_p:
                    add_check(False)
                    severity = Severity.CRITICAL if col_s.required else Severity.INFO
                    rule_name = "required_column_missing" if col_s.required else "optional_column_missing"
                    issues.append(
                        ValidationIssue(
                            sheet=sheet_p.name,
                            column=col_s.name,
                            row=None,
                            rule=rule_name,
                            severity=severity,
                            expected="Column present",
                            actual="Not found",
                            message=f"Column '{col_s.name}' ({'required' if col_s.required else 'optional'}) is missing in sheet '{sheet_p.name}'.",
                            timestamp=datetime.now().isoformat()
                        )
                    )
                    continue

                add_check(True)
                matched_profile_cols.add(col_p.name)

                # Alias İle Eşleşme Bildirimi (WARNING)
                if matched_by_alias:
                    issues.append(
                        ValidationIssue(
                            sheet=sheet_p.name,
                            column=col_s.name,
                            row=None,
                            rule="column_matched_by_alias",
                            severity=Severity.WARNING,
                            expected=col_s.name,
                            actual=col_p.name,
                            message=f"Column '{col_p.name}' matched via alias for canonical name '{col_s.name}'.",
                            timestamp=datetime.now().isoformat()
                        )
                    )

                # Veri Tipi Kontrolü (ERROR)
                type_ok = self._is_type_compatible(col_p.inferred_type, col_s.expected_type)
                add_check(type_ok)
                if not type_ok:
                    issues.append(
                        ValidationIssue(
                            sheet=sheet_p.name,
                            column=col_p.name,
                            row=None,
                            rule="column_type_mismatch",
                            severity=Severity.ERROR,
                            expected=col_s.expected_type,
                            actual=col_p.inferred_type,
                            message=f"Type mismatch on column '{col_p.name}'. Expected type '{col_s.expected_type}', inferred '{col_p.inferred_type}'.",
                            timestamp=datetime.now().isoformat()
                        )
                    )

                # Nullable Kontrolü (ERROR)
                if not col_s.nullable:
                    nulls_ok = col_p.null_ratio == 0.0 and col_p.null_count == 0
                    add_check(nulls_ok)
                    if not nulls_ok:
                        issues.append(
                            ValidationIssue(
                                sheet=sheet_p.name,
                                column=col_p.name,
                                row=None,
                                rule="column_not_nullable_violation",
                                severity=Severity.ERROR,
                                expected="No null values",
                                actual=f"Null count = {col_p.null_count} (ratio = {col_p.null_ratio:.2%})",
                                message=f"Column '{col_p.name}' is marked non-nullable but contains null values.",
                                timestamp=datetime.now().isoformat()
                            )
                        )

                # Unique Kontrolü (ERROR)
                if col_s.unique:
                    unique_ok = col_p.unique_count == col_p.non_null_count
                    add_check(unique_ok)
                    if not unique_ok:
                        duplicates_count = col_p.non_null_count - col_p.unique_count
                        issues.append(
                            ValidationIssue(
                                sheet=sheet_p.name,
                                column=col_p.name,
                                row=None,
                                rule="column_unique_violation",
                                severity=Severity.ERROR,
                                expected="Unique values only",
                                actual=f"Duplicates count = {duplicates_count}",
                                message=f"Column '{col_p.name}' is marked unique but contains duplicate values.",
                                timestamp=datetime.now().isoformat()
                            )
                        )

            # 4. Beklenmeyen Fazla Kolon Kontrolü (WARNING)
            for cp in sheet_p.columns:
                if cp.name not in matched_profile_cols:
                    add_check(True)  # Fazla kolon bulunması akışı durdurmaz
                    issues.append(
                        ValidationIssue(
                            sheet=sheet_p.name,
                            column=cp.name,
                            row=None,
                            rule="unexpected_extra_column",
                            severity=Severity.WARNING,
                            expected="Defined schema columns",
                            actual=f"Extra column '{cp.name}'",
                            message=f"Unexpected extra column '{cp.name}' found in sheet '{sheet_p.name}'.",
                            timestamp=datetime.now().isoformat()
                        )
                    )

        # 5. Özet Bilgileri Oluştur (Summary)
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        warnings_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        errors_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        critical_count = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        
        failed_checks = errors_count + critical_count
        status = "FAILED" if failed_checks > 0 else "SUCCESS"

        summary = ValidationSummary(
            total_checks=total_checks,
            passed=total_checks - failed_checks,
            failed=failed_checks,
            warnings=warnings_count,
            errors=errors_count,
            critical=critical_count,
            duration_ms=duration_ms
        )

        # 6. ValidationReport Oluştur
        report = ValidationReport(
            status=status,
            schema_name=schema.name,
            schema_version=schema.version_info.version,
            file_name=profile.file_name,
            generated_at=datetime.now().isoformat(),
            summary=summary,
            issues=issues,
            profiling_reference=profiling_ref
        )

        # 7. JSON Rapor Dosyasını Yaz
        self.ensure_reports_directory()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file_path = self.reports_dir / f"validation_{timestamp}.json"
        
        try:
            with open(report_file_path, "w", encoding="utf-8") as f:
                f.write(report.to_json())
            logger.info(f"Doğrulama raporu başarıyla kaydedildi: {report_file_path}")
        except Exception as e:
            logger.error(f"Doğrulama rapor JSON dosyası yazılırken hata: {e}")

        return report

    def _is_type_compatible(self, inferred: str, expected: str) -> bool:
        """
        Neden: Profil veri tipi ile şemada beklenen veri tipinin uyumluluğunu
        esnek kurallarla denetlemek.
        """
        if inferred == expected:
            return True
            
        # Integer veri tipi float veya decimal beklenen alanlara atanabilir
        if inferred == "integer" and expected in ["float", "decimal"]:
            return True
            
        # Empty kolonlar nullable ise geçebilir
        if inferred == "empty":
            return True
            
        return False
