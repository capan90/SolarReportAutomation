# Release Notes: Release Candidate RC-1 (Sprint 12)

Bu sürüm, SolarReportAutomation platformunu tam anlamıyla kurumsal seviyede canlı ortama (Production) hazırlayan özellikleri içermektedir.

## Yeni Yetenekler (New Features)

1. **Config Profiles**: `APP_ENV` ortam değişkenine bağlı olarak Development, Test, Staging, Production ve CI profillerine göre otomatik log seviyesi ve zaman aşımı çarpanı yönetimi.
2. **Retry Policy Framework**: Operasyonlardaki transient (geçici) hataları exponential backoff yöntemiyle 3 kez yeniden deneyen ve sonuçları veritabanı `retry_history` tablosuna işleyen `@with_retry` dekoratörü.
3. **OS-Native Scheduler Abstraction**: Windows Task Scheduler (`schtasks`) ve Linux `crontab` entegrasyonu sağlayan `IScheduler` yapısı.
4. **Startup Validation**: Program başlarken kritik bağımlılıkları doğrulayan ve hata durumunda programı durdurup (Fail-Fast) bildirim gönderen erken kontrol mekanizması.
5. **Graceful Shutdown**: OS sinyallerini (SIGINT/SIGTERM/SIGBREAK) yakalayıp kilitleri, tarayıcıları ve log bufferlarını temizleyerek çıkış yapan güvenli kapanış lojiği.

## Değişiklikler ve İyileştirmeler (Changelog)

- `main.py` entry point dosyası startup validation ve graceful shutdown entegrasyonlarıyla güçlendirildi.
- E-posta bildirim sistemi hata/pipeline çıkış kodlarına göre dinamik politikalara (JSON bazlı) bağlandı.
- Log çıktıları console stdout akışına yönlendirilerek Dockerize edilmeye uygun hale getirildi.

## Kurulum ve Konfigürasyon Notları
- `.env` içerisine `APP_ENV=production` girilerek canlı profil aktif edilebilir.
- Zamanlayıcı eklemek için `python main.py` zamanlayıcı arayüzleri kullanılabilir.
