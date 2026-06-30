# Sprint 11A: Health Check & Email Notifications

- **Başlangıç Tarihi**: 2026-06-30
- **Bitiş Tarihi**: 2026-06-30

## Sprint Amaçları ve Kazanımları
Sistem çalıştırılmadan önce ve istendiğinde sağlık kontrolü yapacak modüler bir Health Check yapısının kurulması ve hata durumlarında alarm mailleri atan E-Posta bildirim altyapısının kurulması.

### Tamamlanan Görevler:
1. **Health Check Framework**: `IHealthCheck` sözleşmesini uygulayan Database, Playwright Browser, Filesystem/Disk, SMTP ve Portal erişilebilirlik kontrolleri yazıldı.
2. **Email Notification Framework**: SMTP bağlantı, HTML template enjeksiyon ve kural politikasını dış JSON konfigürasyonundan okuyan bildirim servisi yazıldı.
3. **CLI Komut Desteği**: `python main.py --health` CLI desteği eklendi.
4. **Notification Audit Trail**: Gönderilen bildirimlerin durumu veritabanında `notification_history` tablosunda loglanmaya başlandı.
