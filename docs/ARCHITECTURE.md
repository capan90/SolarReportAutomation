# SolarReportAutomation Mimari Tasarım Kılavuzu

Bu doküman, SolarReportAutomation projesinin Clean Architecture (Temiz Mimari) yapısını, katman sınırlarını ve Sprint 12 itibarıyla eklenen yeni yeteneklerin mimari konumlandırmasını açıklar.

---

## 1. Katman Yapısı (Clean Architecture Layers)

Uygulamamız Clean Architecture ve SOLID prensiplerine göre katmanlandırılmıştır:

### 1.1. Core / Domain Katmanı (`app/core/`)
- Platformun genel ayarlarını (`config.py`), logger sistemini (`logger.py`) ve temel istisna tanımlarını barındırır.
- Sprint 12 ile eklenen `@with_retry` dekoratörü ve `RetryPolicy` frameworkü de sıfır bağımlılıklı yapısıyla bu katmandadır.
- İç katmandır, diğer hiçbir dış modüle veya kütüphaneye bağımlı değildir.

### 1.2. Monitoring & Notifications Modülleri (`app/monitoring/`, `app/notifications/`)
- Sağlık durumlarını denetleyen arayüzler (`IHealthCheck`) ve bildirim servisleri (`NotificationService`, `INotificationQueue`) bu modüldedir.
- Dış sistemler (SMTP Server, Playwright, DB session) soyutlamalar üzerinden çağrılır.

### 1.3. Infrastructure & Database Katmanı (`app/infrastructure/`, `app/database/`)
- Playwright tarayıcı oturumları, veritabanı ORM modelleri (`SolarPlant`, `DailyGeneration`, `EtlRun`, `NotificationHistory`, `RetryHistory`) ve low-level SMTP client (`EmailSender`) bu katmanda yer alır.

---

## 2. Zamanlama Soyutlaması (IScheduler)
- `IScheduler` arayüzü sayesinde platform bağımsız olarak (Windows/Linux) görev zamanlayıcılarına kayıt yapabilir. Çalışma anında uygun olan implementasyon simple factory yardımıyla dinamik döndürülür.
