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

from app.core.config import load_dotenv
from app.dashboard.web_server import start_dashboard_server

# Gerçek admin şifresi koda yazılmaz — .env'den okunur (CLAUDE.md: secret Git'e girmez)
load_dotenv()
ADMIN_PASSWORD = os.environ.get("DASHBOARD_TEST_ADMIN_PASSWORD")

def test_dashboard_server():
    print("===== Dashboard Web Server Smoke Testleri Başlatılıyor =====")

    assert ADMIN_PASSWORD, "DASHBOARD_TEST_ADMIN_PASSWORD .env dosyasında tanımlı olmalı."
    
    # 1. Sunucuyu ayrı bir thread üzerinde başlat (Port: 8099)
    port = 8099
    server_thread = threading.Thread(target=start_dashboard_server, args=(port,), daemon=True)
    server_thread.start()
    
    # Sunucunun başlaması için kısa bir süre bekle
    time.sleep(1.5)
    
    # 2. REST API: Yetkisiz GET /api/kpis -> 401 Unauthorized Test Et
    print("\n[TEST 1] Yetkisiz GET /api/kpis (401 Unauthorized) testi...")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/kpis", method="GET")
        with urllib.request.urlopen(req) as response:
            assert False, "Yetkisiz isteğe izin verilmemeliydi."
    except urllib.error.HTTPError as he:
        print(f"  - HTTP Error Status: {he.code}")
        assert he.code == 401, "Status Code 401 olmalı."
        print("  - [SUCCESS] Yetkisiz istek beklendiği gibi engellendi (401).")

    # 3. REST API: POST /api/auth/login -> 200 OK & Token al
    print("\n[TEST 2] POST /api/auth/login testi...")
    token = None
    try:
        login_data = json.dumps({"username": "admin", "password": ADMIN_PASSWORD}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/auth/login",
            data=login_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            print(f"  - Response status: {response.status}")
            print(f"  - Response body: {body}")
            assert data["success"] is True, "Success True olmalı."
            assert "token" in data["data"], "token bulunmalı."
            token = data["data"]["token"]
            print("  - [SUCCESS] Login başarılı, token alındı.")
    except Exception as e:
        print(f"  - [FAIL] Login başarısız: {e}")
        raise e

    # 4. REST API: Yetkili GET /api/kpis Test Et
    print("\n[TEST 3] Yetkili GET /api/kpis endpoint çağrısı...")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/kpis",
            headers={"Authorization": f"Bearer {token}"},
            method="GET"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            
            print(f"  - Response status: {response.status}")
            print(f"  - Response body: {body[:300]}")
            
            assert data["success"] is True, "Success True olmalı."
            assert "data" in data, "Data alanı bulunmalı."
            assert "metadata" in data, "Metadata bulunmalı."
            
            # Hassas veri gizleme denetimi
            assert "ISOLAR_PASSWORD" not in body, "Şifre sızıntısı var!"
            assert "SMTP_PASSWORD" not in body, "SMTP şifre sızıntısı var!"
            
            print("  - [SUCCESS] Yetkili GET /api/kpis başarıyla test edildi.")
    except Exception as e:
        print(f"  - [FAIL] Yetkili GET /api/kpis başarısız: {e}")
        raise e

    # 5. HTTP Kısıtlama: Yetkili POST /api/kpis -> 405 Method Not Allowed Test Et
    print("\n[TEST 4] Yetkili POST /api/kpis (405 Method Not Allowed) testi...")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/kpis",
            data=b"{}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
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

    # 6. Statik Dosya Sunumu: GET /index.html Test Et (Token gerekmez)
    print("\n[TEST 5] GET /index.html statik dosya sunumu testi...")
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

    # 7. Statik Vendor: GET /static/js/chart.min.js Test Et (Token gerekmez)
    print("\n[TEST 6] GET /static/js/chart.min.js local vendor sunumu testi...")
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

    # 8. User Management API Tests (Requires auth with token)
    print("\n[TEST 7] Kullanıcı Yönetimi API testleri başlıyor...")
    try:
        # a. GET /api/users
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users",
            headers={"Authorization": f"Bearer {token}"},
            method="GET"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data["success"] is True
            users = data["data"]
            print(f"  - GET /api/users response: {[u['username'] for u in users]}")
            assert any(u["username"] == "admin" for u in users)

        # b. POST /api/users (create user 'testuser')
        create_payload = json.dumps({
            "username": "testuser",
            "password": "TestUser2026!",
            "display_name": "Test Kullanıcı"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users",
            data=create_payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data["success"] is True
            print("  - POST /api/users: testuser başarıyla oluşturuldu.")

        # c. GET /api/users (verify testuser exists)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users",
            headers={"Authorization": f"Bearer {token}"},
            method="GET"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            users = data["data"]
            assert any(u["username"] == "testuser" for u in users)

        # d. PUT /api/users/testuser (update display_name and is_active)
        update_payload = json.dumps({
            "display_name": "Test Kullanıcı Güncellenmiş",
            "is_active": True
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users/testuser",
            data=update_payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="PUT"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data["success"] is True
            print("  - PUT /api/users/testuser: testuser başarıyla güncellendi.")

        # e. POST /api/auth/login (login with new user 'testuser' / 'TestUser2026!')
        tu_login_payload = json.dumps({
            "username": "testuser",
            "password": "TestUser2026!"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/auth/login",
            data=tu_login_payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        tu_token = None
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data["success"] is True
            tu_token = data["data"]["token"]
            print("  - POST /api/auth/login (testuser): Giriş başarılı.")

        # f. POST /api/users/change-password (testuser changes own password)
        change_pw_payload = json.dumps({
            "old_password": "TestUser2026!",
            "new_password": "NewTestUser2026!"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users/change-password",
            data=change_pw_payload,
            headers={"Authorization": f"Bearer {tu_token}", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data["success"] is True
            print("  - POST /api/users/change-password (testuser): Şifre başarıyla değiştirildi.")

        # g. DELETE /api/users/admin (should fail - self deletion check)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users/admin",
            headers={"Authorization": f"Bearer {token}"},
            method="DELETE"
        )
        try:
            with urllib.request.urlopen(req) as response:
                assert False, "Admin kendi kullanıcısını silememeliydi."
        except urllib.error.HTTPError as he:
            assert he.code == 400
            print("  - DELETE /api/users/admin: Kendi kullanıcısını silme engellendi (Beklenen davranış).")

        # h. DELETE /api/users/testuser (should succeed)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/users/testuser",
            headers={"Authorization": f"Bearer {token}"},
            method="DELETE"
        )
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            assert data["success"] is True
            print("  - DELETE /api/users/testuser: testuser başarıyla silindi.")

        print("  - [SUCCESS] Kullanıcı Yönetimi API testleri başarıyla tamamlandı.")
    except Exception as e:
        print(f"  - [FAIL] Kullanıcı Yönetimi API testleri başarısız: {e}")
        raise e

    print("\n===== Tüm Dashboard Smoke Testleri Başarıyla Tamamlandı =====")

if __name__ == "__main__":
    test_dashboard_server()
