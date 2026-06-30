# SolarReportAutomation - Operations Manual (İşletim Kılavuzu)

Bu kılavuz, **SolarReportAutomation** platformunun canlı ortamdaki günlük yönetimini, veritabanı yedekleme/kurtarma adımlarını, sorun giderme ve acil durum prosedürlerini içerir.

---

## 1. Günlük Çalışma Kontrolü (Daily Monitoring)

Platform günlük olarak otomatik çalışır ve `logs/app.log` dosyasına işlem kayıtlarını yazar.
- **Başarı Durumu**: `logs/etl_scheduler.log` dosyasındaki en son satırlarda `Cikis Kodu: 0` görülmesi veya Dashboard üzerindeki "Pipeline Monitor" sekmesinde yeşil renkli "SUCCESS" etiketinin bulunması işlemin başarılı olduğunu gösterir.
- **Sorun Tespiti**: Başarısız durumlarda (Exit Code > 0) sistem otomatik olarak hata loglarını `logs/app.log` dosyasına ve `logs/backup_error.log` (yedekleme hatası ise) dosyasına kaydeder.

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
