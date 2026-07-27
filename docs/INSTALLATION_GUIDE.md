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
```

Tarayıcıları **makine geneli** dizine kurun (PowerShell, yönetici):
```powershell
setx /M PLAYWRIGHT_BROWSERS_PATH C:\ProgramData\ms-playwright
$env:PLAYWRIGHT_BROWSERS_PATH = "C:\ProgramData\ms-playwright"
.venv\Scripts\playwright install chromium
```

> **Neden makine geneli?** `PLAYWRIGHT_BROWSERS_PATH` tanımlı değilse Playwright
> tarayıcıları `%USERPROFILE%\AppData\Local\ms-playwright` altında arar; bu yol hesaba
> bağlıdır. Dashboard görevi `NT AUTHORITY\SYSTEM` hesabında koştuğundan
> (`scripts/setup_dashboard_task_server.ps1`) profil yolu
> `C:\Windows\system32\config\systemprofile\...` olur ve kurulumu görmez —
> dashboard'dan tetiklenen raporlar `Executable doesn't exist` ile düşer.
> Kurulum ve `.env` satırının **sırası önemlidir**: önce kurulum, sonra `.env`.
> Aksi halde o ana kadar çalışan zamanlanmış job'lar da boş dizine bakmaya başlar.

Ardından `.env` dosyasına aynı değeri ekleyin (bkz. `.env.example`):
```ini
PLAYWRIGHT_BROWSERS_PATH=C:\ProgramData\ms-playwright
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

### Adım 3b: Faturalama Katsayısı (ilk aylık rapordan ÖNCE)

Dashboard → **Sistem Ayarları → Faturalama Katsayısı** bölümünden fazla satış birim
fiyatını (TL/kWh, **KDV hariç**) tanımlayın.

> ⚠️ **Sıra önemlidir.** Bir ayın katsayısı, o ayın `monthly_billing` satırı **ilk
> oluştuğunda** snapshot olarak kilitlenir (ADR-0002). Katsayı o an tanımlı değilse o
> ayın fatura tutarı hesaplanamaz; Excel ve dashboard "Bekleniyor" gösterir. Kalıcı
> bir kilitlenme değildir — ay yeniden hesaplandığında katsayı yakalanır — ancak rapor
> bir kez eksik gitmiş olur.
>
> **Geçerlilik ayı**, faturalanacak en eski ayın ilk günü olmalıdır. Katsayı sonradan
> değiştirilebilir; değişiklik yalnızca geçerlilik ayından sonraki, henüz kilitlenmemiş
> aylara etki eder ve dashboard'ın yeniden başlatılmasını gerektirmez.

OSB kesintisinin değişken katsayısı her ay elle girilir: aylık rapor üretildikten sonra
dashboard'da çıkan **"OSB Birim Fiyatı Bekleniyor"** uyarı bandından, OSB'nin bir önceki
aya ait gerçek faturasındaki birim fiyat girilir. Giriş yapıldığında o ay kilitlenir.

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
