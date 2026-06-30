# SolarReportAutomation - Installation Guide (Kurulum Kılavuzu)

Bu rehber, **SolarReportAutomation** platformunun hedef Windows (Windows 11 / Windows Server) işletim sistemlerinde PostgreSQL veritabanı ile canlı kurulum adımlarını açıklar.

---

## 1. Gereksinimler (Prerequisites)

- **Python**: v3.10 veya üzeri (PATH ortam değişkenine eklenmiş olmalı).
- **PostgreSQL**: v14 veya üzeri sunucu ve client araçları (pg_dump, psql PATH'e eklenmiş olmalı).
- **Ağ Erişimi**: iSolarCloud portalına bağlanmak ve rapor indirmek için internet erişimi.

---

## 2. Kurulum Adımları

### Adım 1: Depoyu/Klasörü Kopyalayın
Sunucuda çalıştırmak istediğiniz konuma (Örn: `C:\SolarReportAutomation`) tüm dosyaları yerleştirin.

### Adım 2: Sanal Ortam (venv) Oluşturma ve Bağımlılıklar
Komut satırını (cmd/PowerShell) yönetici olarak açın ve proje klasöründe şu komutları koşturun:
```cmd
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

### Adım 3: Yapılandırma (.env) Dosyası Hazırlama
Proje kök dizinindeki `.env` dosyasını düzenleyin:
```ini
APP_ENV=production
DATABASE_URL=postgresql://postgres:parola@localhost:5432/solar_db
ISOLAR_USERNAME=your_username
ISOLAR_PASSWORD=your_password
DASHBOARD_ACCESS_MODE=lan
DASHBOARD_PORT=8080
```

### Adım 4: Kurulum Doğrulama
Hazırladığımız otomatik doğrulama aracını çalıştırın:
```cmd
scripts\verify_installation.bat
```
Tüm adımlar `✓ OK` veya `✓ SUCCESS` dönene kadar eksiklikleri giderin.

---

## 3. Windows Görev Zamanlayıcı (Task Scheduler) Ayarları

ETL işleminin her gün otomatik çalışması için:
1. **Windows Görev Zamanlayıcısı**'nı açın ve **Yeni Görev Oluştur** seçin.
2. **Genel**: Görev adını `Solar_ETL_Daily` yapın. "En yüksek ayrıcalıklarla çalıştır" seçeneğini işaretleyin.
3. **Tetikleyiciler**: "Yeni" seçin, "Günlük" yapın ve başlangıç saatini sabah **07:00** olarak ayarlayın.
4. **Eylemler**: "Yeni" seçin, program/komut yerine `C:\SolarReportAutomation\scripts\run_etl.bat` yolunu girin. "Başlama yeri" alanına `C:\SolarReportAutomation` değerini verin.
5. Görevi kaydedin.

---

## 4. Windows Defender Güvenlik Duvarı İstisnası (LAN Modu)

Dashboard ekranının LAN üzerindeki diğer bilgisayarlardan erişilebilmesi için port izni verilmelidir:
1. **Gelişmiş Güvenlik Özellikli Windows Defender Güvenlik Duvarı** uygulamasını açın.
2. **Gelen Kuralları**'na tıklayın ve sağ taraftan **Yeni Kural** seçin.
3. **Bağlantı Noktası (Port)** seçeneğini seçip İleri deyin.
4. **TCP** seçeneğini seçin ve **Belirli yerel bağlantı noktaları** kısmına `8080` (veya değiştirdiyseniz config portunu) yazıp İleri deyin.
5. **Bağlantıya izin ver**'i seçip kuralları kaydedin (Örn ad: `Solar Dashboard Port 8080`).
