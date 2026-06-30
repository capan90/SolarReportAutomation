import os
import sys
import time
import urllib.request
import urllib.error
import json
import threading
from pathlib import Path
from datetime import date, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.analytics.service import AnalyticsService
from app.analytics.repository import AnalyticsRepository
from app.database import create_tables, SessionLocal, SolarPlant, DailyGeneration
from app.dashboard.web_server import start_dashboard_server

def setup_dummy_data():
    """Geliştirme/Test veritabanına yapay analiz verisi ekler."""
    create_tables()
    session = SessionLocal()
    try:
        # Tesis ekle (varsa geç)
        plant = session.query(SolarPlant).filter(SolarPlant.name == "Test Santrali 1").first()
        if not plant:
            plant = SolarPlant(
                name="Test Santrali 1",
                installed_power_kwp=250.50,
                grid_connection_date=date(2026, 1, 1),
                address="Ankara, TR"
            )
            session.add(plant)
            session.commit()
            session.refresh(plant)
            
        # Günlük üretim kayıtları ekle (Tarih aralığında 1 günlük boşluk bırak: Missing Day)
        # Günler: 2026-06-01, 2026-06-02, 2026-06-04 (03 eksik!)
        dates = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 4)]
        yields = [500.0, 600.0, 700.0]
        
        for d, y in zip(dates, yields):
            existing = session.query(DailyGeneration).filter(
                DailyGeneration.plant_id == plant.id,
                DailyGeneration.date == d
            ).first()
            if not existing:
                gen = DailyGeneration(
                    plant_id=plant.id,
                    date=d,
                    yield_today_kwh=y,
                    total_yield_kwh=y + 1000,
                    equivalent_hours=y / 250.50,
                    revenue_today=y * 2.5,
                    revenue_currency="TL",
                    co2_reduction_kg=y * 0.45
                )
                session.add(gen)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Test verisi oluşturulamadı: {e}")
    finally:
        session.close()

def test_analytics_engine():
    print("===== Historical Analytics Engine Testleri Başlatılıyor =====")
    
    # 0. Test verisi hazırla
    setup_dummy_data()
    
    # 1. AnalyticsService Doğrulaması
    print("\n[TEST 1] AnalyticsService Mantıksal Hesaplama Testi...")
    service = AnalyticsService()
    
    overview = service.get_overview()
    print(f"  - Toplam Üretim: {overview.total_yield_kwh} kWh")
    print(f"  - Günlük Ortalama: {overview.avg_daily_yield_kwh} kWh")
    print(f"  - Zirve Üretim Günü: {overview.peak_production_day} ({overview.peak_production_kwh} kWh)")
    print(f"  - Eksik Gün Sayısı: {overview.missing_days_count}")
    
    assert overview.total_yield_kwh >= 1800.0, "Toplam üretim en az 1800 olmalı."
    assert overview.avg_daily_yield_kwh > 0.0, "Günlük ortalama sıfırdan büyük olmalı."
    
    # 2. Eksik Gün Tespiti (Missing Day Detection)
    print("\n[TEST 2] Missing Day Detection testi...")
    missing_days = service.get_missing_days()
    missing_dates = [m.date for m in missing_days]
    print(f"  - Bulunan Eksik Günler: {missing_dates}")
    
    assert "2026-06-03" in missing_dates, "2026-06-03 eksik gün olarak tespit edilmeliydi."
    print("  - [SUCCESS] Eksik gün tespiti başarıyla doğrulandı.")

    # 3. Haftalık / Aylık Özetler ve Trendler
    print("\n[TEST 3] Haftalık/Aylık Gruplama ve Trend testi...")
    weekly = service.get_weekly_summary()
    monthly = service.get_monthly_summary()
    trend = service.get_trend(limit_days=30)
    
    print(f"  - Haftalık Kayıt Sayısı: {len(weekly)}")
    print(f"  - Aylık Kayıt Sayısı: {len(monthly)}")
    print(f"  - Trend Yönü: {trend.direction} (Değişim: {trend.change_percent}%)")
    
    assert len(weekly) > 0, "Haftalık özet boş olmamalı."
    assert len(monthly) > 0, "Aylık özet boş olmamalı."
    
    # 4. REST API Endpoint Doğrulaması
    print("\n[TEST 4] REST API Analytics Endpoint Testi (Port: 8098)...")
    port = 8098
    server_thread = threading.Thread(target=start_dashboard_server, args=(port,), daemon=True)
    server_thread.start()
    time.sleep(1.5) # Server boot bekle
    
    endpoints = [
        "/api/analytics/overview",
        "/api/analytics/daily",
        "/api/analytics/weekly",
        "/api/analytics/monthly",
        "/api/analytics/missing-days",
        "/api/analytics/trend"
    ]
    
    for ep in endpoints:
        url = f"http://127.0.0.1:{port}{ep}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as response:
                body = response.read().decode("utf-8")
                data = json.loads(body)
                print(f"  - GET {ep}: status={response.status}, success={data['success']}, data_type={type(data['data']).__name__}")
                assert response.status == 200, f"{ep} 200 dönmeliydi."
                assert data["success"] is True, f"{ep} success true dönmeliydi."
                assert data["metadata"]["version"] == "rc-4", "Metadata sürümü rc-4 olmalı."
        except Exception as e:
            print(f"  - [FAIL] Endpoint {ep} başarısız oldu: {e}")
            raise e

    # 5. HTTP Kısıtlama: POST /api/analytics/overview -> 405 Method Not Allowed Test Et
    print("\n[TEST 5] POST /api/analytics/overview (405 Method Not Allowed) testi...")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/analytics/overview", data=b"{}", method="POST")
        with urllib.request.urlopen(req) as response:
            assert False, "POST isteğine izin verilmemeliydi."
    except urllib.error.HTTPError as he:
        print(f"  - HTTP Error Status: {he.code}")
        assert he.code == 405, "Status Code 405 olmalı."
        print("  - [SUCCESS] POST isteği beklendiği gibi 405 ile engellendi.")

    print("\n===== Tüm Historical Analytics Testleri Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    test_analytics_engine()
