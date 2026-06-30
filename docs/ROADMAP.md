# SolarReportAutomation Roadmap

Bu doküman, SolarReportAutomation projesinin geçmiş, şimdiki ve gelecek sürüm/sprint planlarını ve hedeflerini içerir.

---

## Yol Haritası ve Durum Tablosu

| Sürüm | Aşama / Modül | Hedef | Durum |
| :--- | :--- | :--- | :---: |
| **S11A** | Health & Notification | Merkezi Sağlık Kontrolü ve E-Posta Bildirim Entegrasyonu | **Tamamlandı** |
| **S12** | Production Readiness | Konfigürasyon Profilleri, Startup Validation, Retry Framework, Sinyal Graceful Shutdown ve IScheduler Soyutlamaları (Release Candidate RC-1) | **Tamamlandı** |
| **S13** | Metrics & Observability | CPU, Memory, Disk okuma/yazma, Web Portal gecikme süreleri ve veritabanı log metriklerinin toplanması ve izlenmesi | **Tamamlandı** |
| **S14** | Operational Dashboard | Toplanan metriklerin, audit loglarının ve bildirim geçmişinin görselleştirileceği izleme paneli (Release Candidate RC-3) | **Tamamlandı** |
| **S15** | Historical Analytics | Veritabanındaki geçmiş üretim verilerinin trend analizleri ve tahminleme raporlarının kurgulanması | *Hazırlık Aşamasında* |
| **S16** | Multi Source Integration | İsOlar dışındaki diğer güneş paneli ve inverter API/web servis veri kaynaklarının entegre edilmesi | *Planlandı* |
| **S17** | REST API & Service Mode | Sistemimizin RESTful API ile dış dünya servislerine açılması ve kalıcı Windows/Linux Daemon servisine dönüştürülmesi | *Planlandı* |
| **S18** | CI/CD & Cloud Deploy | Bulut altyapılarına otomatik dağıtım (Docker/Kubernetes) ve CI/CD süreçlerinin kurulması | *Planlandı* |

---

## Teknik Borç Takibi (Technical Debt Tracker)
- **Kuyruk Dayanıklılığı (Sprint 12'den kalan)**: In-memory bildirim kuyruğunun PostgreSQL DB queue veya Redis Queue ile değiştirilmesi.
- **Log Rotasyonu (Sprint 12'den kalan)**: `app.log` boyutu için rotasyon limitlerinin eklenmesi.
