# SolarReportAutomation Project Overview

SolarReportAutomation, güneş paneli santrali (Solar Plant) günlük üretim verilerini otomatik olarak toplayan, doğrulayan, veri tabanına yükleyen ve pdf/grafik çıktısı üreten modüler ve kurumsal bir ETL platformudur.

## Sürüm Durumu: Release Candidate RC-1 (Sprint 12)

Platform, yapılan son kurumsal yetenek geliştirmeleriyle canlandırma süreçlerine tam uyumlu hale getirilmiştir:

### Ana Yetenekler (Core Capabilities)
1. **Dinamik Ortam Yapılandırması (Config Profiles)**:
   - Farklı ortamlarda (`APP_ENV` = development, staging, production vb.) loglama ve timeout davranışları dinamik değişir.
2. **Dayanıklı Hata Yönetimi (Retry Framework)**:
   - `@with_retry` ile Playwright portal gezinmeleri, veri indirme ve veritabanı adımları geçici network kayıplarına karşı 3 kez exponential backoff yöntemiyle tekrar denenir.
3. **Erken Hata Tespit (Startup Validation)**:
   - ETL başlamadan sağlık taraması yapılır, arızalı durumlarda fail-fast yapılarak e-posta alarmı atılır.
4. **Zamanlama Altyapısı (IScheduler)**:
   - Windows Görev Zamanlayıcısı ve Linux Cron araçları tek bir arayüzden yönetilir.
5. **Güvenli Kapanış (Graceful Shutdown)**:
   - İşletim sisteminden gelen kill komutlarında (SIGTERM/SIGBREAK) lock dosyaları ve kaynaklar temizlenerek çıkış yapılır.
