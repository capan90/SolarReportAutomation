# Changelog

All notable changes to this project will be documented in this file.

---

## [1.0.0-rc1] - 2026-06-30 (Sprint 12)

### Added
- Geleceğe hazır Config Profiles desteği (`development`, `test`, `staging`, `production`, `ci`, `debug`).
- Yeniden kullanılabilir ve database audit log özellikli `@with_retry` decorator ve `RetryPolicy` frameworkü.
- `IScheduler` soyutlaması ve `WindowsTaskScheduler`, `LinuxCronScheduler` platform entegrasyonları.
- Pipeline başlamadan önce kritik health checkleri koşturan Startup Validation aşaması.
- OS Sinyal yöneticileri (SIGINT/SIGTERM/SIGBREAK) ile Graceful Shutdown desteği.

### Changed
- Log çıktıları console stdout ve log dosyasına paralel yönlendirilerek Dockerize edilmeye hazır hale getirildi.
- Giriş, navigasyon ve indirme adımları retry koruması altına alındı.

---

## [0.9.0] - 2026-06-30 (Sprint 11A)

### Added
- Modüler Health Check Framework ve `python main.py --health` CLI desteği.
- Dış JSON politikasından beslenen ve in-memory queue destekli Email Notification Framework.
- E-posta şablonları (`templates/` success, failed, validation_failed HTML).
- Bildirim geçmişinin veritabanına kaydedildiği `notification_history` audit yapısı.
