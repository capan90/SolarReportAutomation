# -*- coding: utf-8 -*-
"""
Neden: run_id kolonları String(36) tanımlıydı ancak job run_id formatı
("job-settlement-monthly-YYYY-MM-{timestamp}" = 41+ karakter) bu sınırı aşıyor.
PostgreSQL'de StringDataRightTruncation (value too long for varying(36)) hatası
oluşuyor; SQLite uzunluğu zorlamadığından yerelde görünmüyordu.

Bu script DATABASE_URL'e bağlanır:
  - PostgreSQL ise: 4 tabloda run_id kolonunu VARCHAR(100)'e genişletir.
  - SQLite ise: no-op (SQLite varchar uzunluğunu zorlamaz; models.py'deki
    String(100) yeni kurulumlarda geçerli olur).

Kullanım: .venv\\Scripts\\python.exe scripts\\migrate_run_id_width.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.config import load_dotenv
load_dotenv()

from app.database.db_session import engine  # noqa: E402

TABLES = ["etl_runs", "notification_history", "retry_history", "performance_metrics"]
NEW_WIDTH = 100


def main():
    dialect = engine.dialect.name
    print(f"Veritabanı: {engine.url.render_as_string(hide_password=True)} (dialect={dialect})")

    if dialect == "sqlite":
        print(
            "SQLite varchar uzunluğunu zorlamaz — ALTER gerekmiyor (no-op).\n"
            "models.py'deki String(100) tanımı yeni tablo oluşturmalarında geçerlidir."
        )
        return

    if dialect != "postgresql":
        print(f"Beklenmeyen dialect '{dialect}' — elle inceleyin, işlem yapılmadı.")
        sys.exit(1)

    with engine.begin() as conn:
        for table in TABLES:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
                {"t": table},
            ).fetchone()
            if not exists:
                print(f"  {table}: tablo yok, atlandı")
                continue

            current = conn.execute(
                text(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'run_id'"
                ),
                {"t": table},
            ).scalar()
            if current is not None and current >= NEW_WIDTH:
                print(f"  {table}.run_id: zaten {current} — atlandı")
                continue

            conn.execute(
                text(f"ALTER TABLE {table} ALTER COLUMN run_id TYPE VARCHAR({NEW_WIDTH})")
            )
            print(f"  {table}.run_id: {current} -> VARCHAR({NEW_WIDTH}) OK")

    print("\nMigration tamamlandı.")


if __name__ == "__main__":
    main()
