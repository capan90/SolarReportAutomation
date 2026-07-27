# SolarReportAutomation - Operations Manual (İşletim Kılavuzu)

Bu kılavuz, **SolarReportAutomation** platformunun canlı ortamdaki günlük yönetimini, veritabanı yedekleme/kurtarma adımlarını, sorun giderme ve acil durum prosedürlerini içerir.

---

## 1. Günlük Çalışma Kontrolü (Daily Monitoring)

Platform günlük olarak otomatik çalışır ve işlem kayıtlarını **iki ayrı log dosyasına** yazar:

| Dosya | İçerik |
| :--- | :--- |
| `logs/app.log` | Zamanlanmış görevler (günlük/aylık mahsuplaşma, santral durumu) — kısa ömürlü process'ler |
| `logs/dashboard.log` | Dashboard süreci ve **dashboard'dan tetiklenen** işler (geçmiş rapor, captcha yenileme, faturalama) |

> **Neden ayrı?** Dashboard 7/24 çalışıp dosyayı açık tuttuğu için Windows'ta log rotasyonu (`os.rename`) başarısız oluyor ve kayıtlar sessizce kayboluyordu. Uzun ömürlü tek yazıcı ayrılınca `app.log` normal şekilde döndürülebiliyor. Bir işi ararken **onu neyin tetiklediğine** göre dosya seçin.

- **Başarı Durumu**: `logs/etl_scheduler.log` dosyasındaki en son satırlarda `Cikis Kodu: 0` görülmesi veya Dashboard üzerindeki "Pipeline Monitor" sekmesinde yeşil renkli "SUCCESS" etiketinin bulunması işlemin başarılı olduğunu gösterir.
- **Sorun Tespiti**: Başarısız durumlarda (Exit Code > 0) sistem otomatik olarak hata loglarını ilgili log dosyasına (`logs/app.log` veya `logs/dashboard.log`) ve `logs/backup_error.log` (yedekleme hatası ise) dosyasına kaydeder.

---

## 1b. Dashboard'ı Yeniden Başlatma (ZORUNLU PROSEDÜR)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart_dashboard.ps1
```

> ⛔ **Dashboard'ı ASLA düz `Stop-ScheduledTask` / `Start-ScheduledTask` ile yeniden başlatmayın.**
>
> Görev `wscript.exe`'yi başlatır, o da `python.exe`'yi çalıştırır. Task Scheduler görevi durdurduğunda **`wscript.exe` ölür ama `python.exe` çocuk process'i hayatta kalır** ve 8081 portunu tutmaya devam eder. Sonraki başlatma `WinError 10048` alır; `run_dashboard_hidden.vbs` döngüsü 4 deneme sonra pes eder ve **dashboard tamamen kapalı kalır**. 2026-07-27'de canlıda yaşandı; dev makinesinde `Stop-ScheduledTask` sonrası 6 gün önce başlamış bir `python.exe`'nin portu hâlâ tuttuğu ölçülerek doğrulandı.
>
> `restart_dashboard.ps1` bu tuzağı kapatır: görevi durdurur, portu tutan process'i sonlandırır, **portun gerçekten boşaldığını** doğrular (20 sn timeout), görevi başlatır ve HTTP 200 ile teyit eder. Başarısız olursa `logs/dashboard.log`'un son satırlarını gösterir.

Kurulum script'i (`setup_dashboard_task_server.ps1`) da başlatma aşamasında bu script'i çağırır — yani restart yolu her kurulumda otomatik olarak sınanır.

**Dashboard kapalı kalırsa haberiniz olur:** VBS döngüsü pes ettiğinde sistem otomatik "Dashboard Kapalı" uyarı e-postası gönderir (`scripts/send_dashboard_down_alert.py`).

---

## 2. Dashboard ve LAN Erişimi

- **Localhost Modu**: `http://127.0.0.1:8080`
- **LAN Modu**: Sunucunun yerel IP adresi üzerinden (Örn: `http://192.168.1.50:8080`) şirket içi diğer bilgisayarlardan tarayıcıyla erişilebilir.
- **Salt-Okunur**: Arayüz üzerinden veri silme veya güncelleme yapılamaz, bu nedenle güvenlidir.

---

## 3. Yedekleme ve Kurtarma (Backup & Restore)

### 3.1. Yedek Alma (Manuel / Otomatik)
Yedekler otomatik olarak her gün alınır. Manuel yedek almak isterseniz:
1. `scripts/backup_database.bat` dosyasını çalıştırın.
2. Dosya `backups/backup_solar_db_YYYYMMDD_HHMMSS.sql` adıyla kaydedilecektir.

### 3.2. Yedeği Geri Yükleme (Restore)
Herhangi bir veri kaybı durumunda yedeği geri yüklemek için:
1. Geri yüklenecek `.sql` yedek dosyasını belirleyin (Örn: `backups/backup_solar_db_20260630_104850.sql`).
2. Komut satırından parametre vererek şu komutu koşturun:
   ```cmd
   scripts\restore_database.bat backups\backup_solar_db_20260630_104850.sql
   ```
3. Gelen onay sorusuna `evet` yazıp enter'a basın.

---

## 4. Sorun Giderme (Troubleshooting)

### Sorun 1: Port Çakışması (Address already in use)
- **Belirti**: Dashboard başlatılırken hata veriyor.
- **Çözüm**: `.env` içindeki `DASHBOARD_PORT` değerini `8085` gibi boş bir porta çekin veya `scripts/stop_services.bat` betiğini çalıştırarak eski dashboard sürecini kapatın.

### Sorun 2: PostgreSQL Bağlantı Hatası (Connection Refused)
- **Belirti**: `verify_installation.bat` komutunda `PostgreSQL Bağlantısı: FAILED` hatası.
- **Çözüm**: PostgreSQL servisinin Windows Hizmetler (Services.msc) altında çalıştığından ve `.env` dosyasındaki `DATABASE_URL` kullanıcı adı/şifre bilgilerinin doğruluğundan emin olun.

---

## 5. Acil Durum Durdurma (Emergency Stop)

Sistemde ters giden bir tarayıcı döngüsü veya aşırı bellek tüketimi gözlemlenirse:
1. `scripts/stop_services.bat` dosyasını çalıştırarak tüm arka plan dashboard servislerini sonlandırın.
2. Devam eden günlük ETL sürecini sonlandırmak için komut satırından `taskkill /f /im python.exe` komutunu koşturun.
