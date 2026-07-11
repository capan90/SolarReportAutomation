import os
import sys
import time
import urllib.request
import urllib.error
import json
import threading
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.dashboard.web_server import start_dashboard_server

def test_dashboard_server():
    print("===== Dashboard Web Server Smoke Testleri Başlatılıyor =====")
    
    # 1. Sunucuyu ayrı bir thread üzerinde başlat (Port: 8099)
    port = 8099
    server_thread = threading.Thread(target=start_dashboard_server, args=(port,), daemon=True)
    server_thread.start()
    
    # Sunucunun başlaması için kısa bir süre bekle
    time.sleep(1.5)
    
    # 2. REST API: GET /api/kpis Test Et
    print("\n[TEST 1] GET /api/kpis endpoint çağrısı...")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/kpis", method="GET")
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            
            print(f"  - Response status: {response.status}")
            print(f"  - Response body: {body[:300]}")
            
            assert data["success"] is True, "Success True olmalı."
            assert "data" in data, "Data alanı bulunmalı."
            assert "metadata" in data, "Metadata bulunmalı."
            assert "timestamp" in data["metadata"], "timestamp metadata içinde bulunmalı."
            
            # Hassas veri gizleme denetimi
            assert "ISOLAR_PASSWORD" not in body, "Şifre sızıntısı var!"
            assert "SMTP_PASSWORD" not in body, "SMTP şifre sızıntısı var!"
            
            print("  - [SUCCESS] GET /api/kpis başarıyla test edildi.")
    except Exception as e:
        print(f"  - [FAIL] GET /api/kpis başarısız: {e}")
        raise e

    # 3. HTTP Kısıtlama: POST /api/kpis -> 405 Method Not Allowed Test Et
    print("\n[TEST 2] POST /api/kpis (405 Method Not Allowed) testi...")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/kpis", data=b"{}", method="POST")
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            print(f"  - [FAIL] POST isteği 200 döndü! (405 dönmeliydi)")
            assert False, "POST isteğine izin verilmemeliydi."
    except urllib.error.HTTPError as he:
        print(f"  - HTTP Error Status: {he.code}")
        body = he.read().decode("utf-8")
        data = json.loads(body)
        print(f"  - Response Body: {body}")
        
        assert he.code == 405, "Status Code 405 olmalı."
        assert data["success"] is False, "POST başarısız (False) olmalı."
        assert "HTTP metodu desteklenmiyor" in data["error"], "Hata mesajı doğru olmalı."
        print("  - [SUCCESS] POST isteği beklendiği gibi engellendi (405).")

    # 4. Statik Dosya Sunumu: GET /index.html Test Et
    print("\n[TEST 3] GET /index.html statik dosya sunumu testi...")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/index.html", method="GET")
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            print(f"  - Response status: {response.status}")
            print(f"  - Gelen html ilk satırlar: {body[:150]}")
            
            assert "GES Enerji" in body, "index.html içeriği doğru olmalı."
            assert response.getheader("Content-Type") == "text/html; charset=utf-8", "Content-Type doğru olmalı."
            print("  - [SUCCESS] GET /index.html başarıyla servis edildi.")
    except Exception as e:
        print(f"  - [FAIL] index.html sunumu başarısız: {e}")
        raise e

    # 5. Statik Vendor: GET /static/js/chart.min.js Test Et
    print("\n[TEST 4] GET /static/js/chart.min.js local vendor sunumu testi...")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/static/js/chart.min.js", method="GET")
        with urllib.request.urlopen(req) as response:
            body = response.read()
            print(f"  - Response status: {response.status}")
            print(f"  - Script Boyutu: {len(body)} bytes")
            
            assert len(body) > 0, "Script dosyası boş olmamalı."
            assert response.getheader("Content-Type") == "application/javascript", "Content-Type doğru olmalı."
            print("  - [SUCCESS] GET /static/js/chart.min.js başarıyla servis edildi.")
    except Exception as e:
        print(f"  - [FAIL] chart.min.js sunumu başarısız: {e}")
        raise e

    print("\n===== Tüm Dashboard Smoke Testleri Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    test_dashboard_server()
