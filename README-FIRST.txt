================================================================================
          SolarReportAutomation Kurulum ve Çalıştırma Kılavuzu
================================================================================

Bu paket, platformu canlı (production) Windows ortamlarında kurmak ve çalıştırmak
için gerekli tüm dosyaları ve hazır betikleri barındırır.

Hızlı Kurulum Adımları:
1. PostgreSQL Veritabanı Sunucusunu hazırlayın ve bir şema oluşturun.
2. Dizin içindeki `.env` dosyasını düzenleyin ve database url, mail, portal credentials ayarlarını yapın.
3. Yönetici yetkileriyle komut satırından `scripts/verify_installation.bat` çalıştırın.
4. Doğrulama başarılı ise günlük çalıştırmalar için `scripts/run_etl.bat` betiğini Windows Görev Zamanlayıcısına ekleyin.

Dashboard Nasıl Açılır?
- Proje ana dizinindeki `open_dashboard.bat` dosyasına çift tıklayarak veya komut satırından çalıştırarak Dashboard'u başlatabilirsiniz.
- Bu işlem web sunucusunu arka planda başlatacak ve varsayılan tarayıcınızda otomatik olarak http://127.0.0.1:8080 (veya yapılandırılmış port) adresini açacaktır.
- Web sunucusunu durdurmak için `scripts/stop_services.bat` betiğini çalıştırın.

Test Çalıştırmaları:
- Canlı veri çekim akışı için: `scripts/run_etl.bat`
- Dry-run test akışı için: `scripts/run_etl_dry_run.bat`
- SMTP mail altyapısını test etmek için: `scripts/test_smtp.bat`

Dosya ve Klasör Yapısı:
- scripts/              -> Başlatıcı batch betikleri (.bat)
- app/                  -> Sistem çekirdeği ve modülleri
- config/               -> Kaynaklar ve yapılandırma JSON'ları
- logs/                 -> app.log ve hata kayıtları
- backups/              -> Günlük zaman damgalı PostgreSQL yedekleri
- docs/                 -> Detaylı Kurulum ve İşletim Rehberleri

Daha fazla detay için docs/INSTALLATION_GUIDE.md ve docs/OPERATIONS_MANUAL.md dokümanlarını okuyun.
