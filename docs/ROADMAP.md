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
| **S15** | Historical Analytics | Veritabanındaki geçmiş üretim verilerinin trend analizleri ve tahminleme raporlarının kurgulanması (Release Candidate RC-4) | **Tamamlandı** |
| **S16** | Multi Source Integration | İsOlar dışındaki diğer güneş paneli ve inverter API/web servis veri kaynaklarının entegre edilmesi (Release Candidate RC-5) | **Tamamlandı** |
| **S17** | REST API & Service Mode | Sistemimizin RESTful API ile dış dünya servislerine açılması ve kalıcı Windows/Linux Daemon servisine dönüştürülmesi | *Hazırlık Aşamasında* |
| **S18** | CI/CD & Cloud Deploy | Bulut altyapılarına otomatik dağıtım (Docker/Kubernetes) ve CI/CD süreçlerinin kurulması | *Planlandı* |

---

## Teknik Borç Takibi (Technical Debt Tracker)
- **Kuyruk Dayanıklılığı (Sprint 12'den kalan)**: In-memory bildirim kuyruğunun PostgreSQL DB queue veya Redis Queue ile değiştirilmesi.
- **Log Rotasyonu (Sprint 12'den kalan)**: `app.log` boyutu için rotasyon limitlerinin eklenmesi.
- **Ruff Temizliği (2026-07-20, güncellendi)**: 101 ihlal (90 F401 unused-import ağırlıklı) + 124 dosyalık `ruff format` bekliyor. Ön koşul TAMAMLANDI: 107 testlik smoke güvenlik ağı kuruldu (tests/smoke/, pre-commit'te blocking). Sıradaki adım tek izole commit'te: `ruff format .` + `ruff check --fix` → `pytest tests/smoke/` ile davranış değişmediğini doğrula → hook'taki ruff kontrolünü warn-only'den tekrar blocking'e al. Elle düzeltilecek 9 ihlal (E701/F841/E712) ve F823 bug'ı (ayrı madde) bu kapsamda ele alınacak.
- **F823 Potansiyel Bug (2026-07-20)**: `app/dashboard/web_server.py:422` — fonksiyon içi yerel `import re` nedeniyle olası `UnboundLocalError`, incelenmeli ve düzeltilmeli.
- **Dashboard Prod Ortamı (2026-07-21)**: Prod = APPS sunucusu (`APPS.erdemsoft.local`, 10.0.0.169, sabit IP); kullanıcı erişimi `http://10.0.0.169:8081`. Kalıcı çalışma kurulumu `scripts/setup_dashboard_task_server.ps1` ile yapılır (AtStartup + SYSTEM görevi, firewall 8081, restart-on-failure). Prod `.env` gereksinimleri: `DASHBOARD_PORT=8081`, `DASHBOARD_ACCESS_MODE=network`, `DASHBOARD_URL=http://10.0.0.169:8081` (e-posta linkleri bunu kullanır). Dev laptop'un IP'si DHCP ile değişkendir — dev'de dashboard `http://localhost:8081` üzerinden kullanılmalı, LAN linki paylaşılmamalı.
