import os
import sys
import time
import urllib.request
import urllib.error
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.db_session import SessionLocal, create_tables
from app.database.models import SettlementDaily, SettlementMonthly
from app.dashboard.web_server import start_dashboard_server

# Prepare dummy/mock reports
def setup_dummy_files_and_db():
    print("Preparing test database entries and dummy report files...")
    create_tables()
    
    db = SessionLocal()
    try:
        # Delete daily 2026-07-06 and 2026-07-03
        db.query(SettlementDaily).filter(SettlementDaily.date.in_([
            datetime.strptime("2026-07-06", "%Y-%m-%d").date(),
            datetime.strptime("2026-07-03", "%Y-%m-%d").date()
        ])).delete(synchronize_session=False)
        
        # Delete monthly 2026-05 and 2026-04
        db.query(SettlementMonthly).filter(
            ((SettlementMonthly.year == 2026) & (SettlementMonthly.month == 5)) |
            ((SettlementMonthly.year == 2026) & (SettlementMonthly.month == 4))
        ).delete(synchronize_session=False)
        
        # Insert daily 2026-07-06
        daily_row = SettlementDaily(
            date=datetime.strptime("2026-07-06", "%Y-%m-%d").date(),
            production_kwh=100.0,
            consumption_kwh=80.0,
            settled_kwh=80.0,
            grid_import_kwh=0.0,
            grid_export_kwh=20.0
        )
        db.add(daily_row)
        
        # Insert monthly 2026-05
        monthly_row = SettlementMonthly(
            year=2026,
            month=5,
            production_kwh=3000.0,
            consumption_kwh=2500.0,
            settled_kwh=2500.0,
            grid_import_kwh=0.0,
            grid_export_kwh=500.0
        )
        db.add(monthly_row)
        
        db.commit()
    finally:
        db.close()
        
    # Dummy report files
    daily_dir = Path("outputs/reports/2026-07")
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / "mahsup_20260706.xlsx"
    daily_file.write_bytes(b"dummy daily excel file content")

    monthly_dir = Path("outputs/reports/2026-05")
    monthly_dir.mkdir(parents=True, exist_ok=True)
    monthly_file = monthly_dir / "mahsup_202605_aylik.xlsx"
    monthly_file.write_bytes(b"dummy monthly excel file content")

    # Ensure non-cached files do not exist
    non_cached_daily = Path("outputs/reports/2026-07/mahsup_20260703.xlsx")
    if non_cached_daily.exists():
        non_cached_daily.unlink()
        
    non_cached_monthly = Path("outputs/reports/2026-04/mahsup_202604_aylik.xlsx")
    if non_cached_monthly.exists():
        non_cached_monthly.unlink()
        
    print("Test setup ready.")

def cleanup_test_setup():
    print("Cleaning up test database entries and report files...")
    db = SessionLocal()
    try:
        db.query(SettlementDaily).filter(SettlementDaily.date.in_([
            datetime.strptime("2026-07-06", "%Y-%m-%d").date(),
            datetime.strptime("2026-07-03", "%Y-%m-%d").date()
        ])).delete(synchronize_session=False)
        
        db.query(SettlementMonthly).filter(
            ((SettlementMonthly.year == 2026) & (SettlementMonthly.month == 5)) |
            ((SettlementMonthly.year == 2026) & (SettlementMonthly.month == 4))
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
        
    daily_file = Path("outputs/reports/2026-07/mahsup_20260706.xlsx")
    if daily_file.exists():
        daily_file.unlink()
        
    monthly_file = Path("outputs/reports/2026-05/mahsup_202605_aylik.xlsx")
    if monthly_file.exists():
        monthly_file.unlink()
    print("Cleanup done.")

def test_historical_endpoints():
    print("===== Geçmiş Rapor API Testleri Başlatılıyor =====")
    setup_dummy_files_and_db()
    
    # Mocking DailySettlementJob.run
    import app.jobs.daily_settlement_job
    mock_daily_run = MagicMock()
    mock_daily_run.return_value = {
        "status": "SUCCESS",
        "date": "2026-07-03",
        "report_path": "outputs/reports/2026-07/mahsup_20260703.xlsx",
        "settlement_count": 24,
        "error": None
    }
    app.jobs.daily_settlement_job.DailySettlementJob.run = mock_daily_run

    # Mocking MonthlySettlementJob.run
    import app.jobs.monthly_settlement_job
    mock_monthly_run = MagicMock()
    mock_monthly_run.return_value = {
        "status": "SUCCESS",
        "month": "2026-04",
        "report_path": "outputs/reports/2026-04/mahsup_202604_aylik.xlsx",
        "settlement_count": 720,
        "error": None
    }
    app.jobs.monthly_settlement_job.MonthlySettlementJob.run = mock_monthly_run

    # Start dashboard server on port 8097
    port = 8097
    server_thread = threading.Thread(target=start_dashboard_server, args=(port,), daemon=True)
    server_thread.start()
    time.sleep(1.5)
    
    try:
        # TEST 1: DB'de olan tarih (2026-07-06) -> cached dönmeli
        print("\n[TEST 1] POST /api/settlement/trigger/daily-date -> 2026-07-06 (cached)")
        url = f"http://127.0.0.1:{port}/api/settlement/trigger/daily-date"
        payload = json.dumps({"date": "2026-07-06"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {res.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is True
            assert data["data"]["status"] == "cached"
            assert data["data"]["download_url"] == "/api/settlement/download/daily/2026-07-06"
            print("  - [SUCCESS] Cached daily report trigger test passed.")

        # TEST 2: DB'de olmayan tarih (2026-07-03) -> job çalışmalı
        print("\n[TEST 2] POST /api/settlement/trigger/daily-date -> 2026-07-03 (run job)")
        payload = json.dumps({"date": "2026-07-03"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {res.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is True
            assert data["data"]["status"] == "SUCCESS"
            assert data["data"]["download_url"] == "/api/settlement/download/daily/2026-07-03"
            mock_daily_run.assert_called_once_with(target_date="2026-07-03")
            print("  - [SUCCESS] Trigger daily report job run test passed.")

        # TEST 3: Geçersiz tarih (gelecek tarih veya yanlış format) -> hata
        print("\n[TEST 3] POST /api/settlement/trigger/daily-date -> Future date validation")
        payload = json.dumps({"date": "2030-01-01"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {res.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is False
            assert "geçmişte" in data["error"] or "gecmiste" in data["error"] or "tarih" in data["error"]
            print("  - [SUCCESS] Daily future date validation test passed.")

        # TEST 4: DB'de olan ay (2026-05) -> cached dönmeli
        print("\n[TEST 4] POST /api/settlement/trigger/monthly-date -> 2026-05 (cached)")
        url_monthly = f"http://127.0.0.1:{port}/api/settlement/trigger/monthly-date"
        payload = json.dumps({"month": "2026-05"}).encode("utf-8")
        req = urllib.request.Request(url_monthly, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {res.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is True
            assert data["data"]["status"] == "cached"
            assert data["data"]["download_url"] == "/api/settlement/download/monthly/2026-05"
            print("  - [SUCCESS] Cached monthly report trigger test passed.")

        # TEST 5: DB'de olmayan ay (2026-04) -> job çalışmalı
        print("\n[TEST 5] POST /api/settlement/trigger/monthly-date -> 2026-04 (run job)")
        payload = json.dumps({"month": "2026-04"}).encode("utf-8")
        req = urllib.request.Request(url_monthly, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {res.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is True
            assert data["data"]["status"] == "SUCCESS"
            assert data["data"]["download_url"] == "/api/settlement/download/monthly/2026-04"
            mock_monthly_run.assert_called_once_with(target_month="2026-04")
            print("  - [SUCCESS] Trigger monthly report job run test passed.")

        # TEST 6: Geçersiz ay (gelecek ay) -> hata
        print("\n[TEST 6] POST /api/settlement/trigger/monthly-date -> Future month validation")
        payload = json.dumps({"month": "2030-01"}).encode("utf-8")
        req = urllib.request.Request(url_monthly, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {res.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is False
            assert "ay" in data["error"] or "tarih" in data["error"]
            print("  - [SUCCESS] Monthly future month validation test passed.")

        # TEST 7: Download daily
        print("\n[TEST 7] GET /api/settlement/download/daily/2026-07-06")
        download_url = f"http://127.0.0.1:{port}/api/settlement/download/daily/2026-07-06"
        req = urllib.request.Request(download_url, method="GET")
        with urllib.request.urlopen(req) as res:
            content = res.read()
            print(f"  - Response status: {res.status}")
            print(f"  - Content-Type: {res.getheader('Content-Type')}")
            print(f"  - Content-Length: {res.getheader('Content-Length')}")
            assert res.status == 200
            assert "application/vnd.openxmlformats-officedocument" in res.getheader('Content-Type')
            assert content == b"dummy daily excel file content"
            print("  - [SUCCESS] Download daily endpoint verified.")

        # TEST 8: Download monthly
        print("\n[TEST 8] GET /api/settlement/download/monthly/2026-05")
        download_url = f"http://127.0.0.1:{port}/api/settlement/download/monthly/2026-05"
        req = urllib.request.Request(download_url, method="GET")
        with urllib.request.urlopen(req) as res:
            content = res.read()
            print(f"  - Response status: {res.status}")
            print(f"  - Content-Type: {res.getheader('Content-Type')}")
            print(f"  - Content-Length: {res.getheader('Content-Length')}")
            assert res.status == 200
            assert "application/vnd.openxmlformats-officedocument" in res.getheader('Content-Type')
            assert content == b"dummy monthly excel file content"
            print("  - [SUCCESS] Download monthly endpoint verified.")

        print("\n===== Tüm Geçmiş Rapor API Testleri Başarıyla Tamamlandı =====")
    finally:
        cleanup_test_setup()

if __name__ == "__main__":
    test_historical_endpoints()
