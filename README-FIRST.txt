================================================================================
          SolarReportAutomation Kurulum ve Çalıştırma Kılavuzu
================================================================================

Bu paket, platformu canlı (production) Windows ortamlarında kurmak ve çalıştırmak
için gerekli tüm dosyaları ve hazır betikleri barındırır.

Hızlı Kurulum Adımları:
1. PostgreSQL Veritabanı Sunucusunu hazırlayın ve bir şema oluşturun.
2. Dizin içindeki `.env` dosyasını düzenleyin ve database url, mail, portal credentials ayarlarını yapın.
3. Yönetici yetkileriyle komut satırından `scripts/verify_installation.bat` dosyasını çalıştırın.
4. Doğrulama başarılı ise günlük çalıştırmalar için `scripts/run_etl.bat` betiğini Windows Görev Zamanlayıcısına ekleyin.

Dosya ve Klasör Yapısı:
- scripts/              -> Başlatıcı batch betikleri (.bat)
- app/                  -> Sistem çekirdeği ve modülleri
- config/               -> Kaynaklar ve yapılandırma JSON'ları
- logs/                 -> app.log ve hata kayıtları
- backups/              -> Günlük zaman damgalı PostgreSQL yedekleri
- docs/                 -> Detaylı Kurulum ve İşletim Rehberleri

Daha fazla detay için docs/INSTALLATION_GUIDE.md ve docs/OPERATIONS_MANUAL.md dokümanlarını okuyun.
