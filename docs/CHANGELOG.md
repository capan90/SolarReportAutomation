# Changelog

All notable changes to this project will be documented in this file.

---

## [1.2.0-rc3] - 2026-06-30 (Sprint 14)

### Added
- Localhost binding (`127.0.0.1`) ve port yapılandırma desteğiyle asenkron çalışan `DashboardWebServer`.
- Sunucuda salt-okunur (GET-only) güvence ve yazma/güncelleme isteklerini (POST/PUT/DELETE) engelleme lojiği (HTTP 405).
- Veritabanı sorgularını soyutlayan ve ORM modellerini maskeleyen `DashboardRepository` ile `DashboardService` katmanları.
- ExecutiveSummary, PipelineRun, HealthStatus ve MetricSeries için tasarlanan DTO modelleri.
- Responsive, dark-mode ve glassmorphism temalı tek sayfalık HTML5/CSS3 arayüzü (`app/dashboard/static/`).
- Çevrimdışı çalışmaya hazır yerel vendor `chart.min.js` entegrasyonu.

---

## [1.1.0-rc2] - 2026-06-30 (Sprint 13)

### Added
- `MetricType` (Counter, Gauge, Histogram, Timer) tanımlarını içeren genel Metrik ve Gözlemlenebilirlik Frameworkü.
- `MetricsCollector` ile sistem (CPU, RAM, Disk), uygulama, operasyonel ve iş metriklerini toplama yeteneği.
- `ConsoleMetricExporter` (Prometheus-like), `DatabaseMetricExporter` ve `JsonMetricExporter` ihracatçıları.
- `@with_retry` decorator üzerinden her tekrar denemede `retry.count` metriğinin toplanması.
- `PerformanceMetric` ORM veritabanı modeli ve `MetricRepository` soyutlaması.

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
