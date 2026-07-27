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
| **S19** | Billing & Invoice Reconciliation | Fazla Satış Faturası ve OSB Kesintisi TL hesaplarının aylık rapora eklenmesi; aya kilitlenen katsayı snapshot'ları (ADR-0002). Sprint A: veri modeli + servis, B: dashboard, C: Excel/e-posta/chatbot | *Geliştiriliyor* |

---

## Teknik Borç Takibi (Technical Debt Tracker)
- **Kuyruk Dayanıklılığı (Sprint 12'den kalan)**: In-memory bildirim kuyruğunun PostgreSQL DB queue veya Redis Queue ile değiştirilmesi.
- **Log Rotasyonu (Sprint 12'den kalan)**: `app.log` boyutu için rotasyon limitlerinin eklenmesi.
- **Ruff Temizliği (2026-07-20, güncellendi)**: 101 ihlal (90 F401 unused-import ağırlıklı) + 124 dosyalık `ruff format` bekliyor. Ön koşul TAMAMLANDI: 107 testlik smoke güvenlik ağı kuruldu (tests/smoke/, pre-commit'te blocking). Sıradaki adım tek izole commit'te: `ruff format .` + `ruff check --fix` → `pytest tests/smoke/` ile davranış değişmediğini doğrula → hook'taki ruff kontrolünü warn-only'den tekrar blocking'e al. Elle düzeltilecek 9 ihlal (E701/F841/E712) ve F823 bug'ı (ayrı madde) bu kapsamda ele alınacak.
- ~~**F823 Potansiyel Bug (2026-07-20)**~~ → **ÇÖZÜLDÜ (2026-07-27)**: "Potansiyel" değilmiş — `_handle_api` içindeki yerel `import re`, modül seviyesindeki `re`'yi tüm fonksiyon kapsamında gölgeliyordu ve o satırdan önce çalışan her dal `UnboundLocalError` alıyordu. Bug, Sprint B'de eklenen ve ay formatını `re.match` ile doğrulayan faturalama endpoint'lerinde canlıya çıktı (`/api/billing/monthly/{YYYY-MM}` her istekte 500 veriyordu). Yerel import kaldırıldı; `ruff check --select F823` temiz.
- **Dashboard Prod Ortamı (2026-07-21)**: Prod = APPS sunucusu (`APPS.erdemsoft.local`, 10.0.0.169, sabit IP); kullanıcı erişimi `http://10.0.0.169:8081`. Kalıcı çalışma kurulumu `scripts/setup_dashboard_task_server.ps1` ile yapılır (AtStartup + SYSTEM görevi, firewall 8081, restart-on-failure). Prod `.env` gereksinimleri: `DASHBOARD_PORT=8081`, `DASHBOARD_ACCESS_MODE=network`, `DASHBOARD_URL=http://10.0.0.169:8081` (e-posta linkleri bunu kullanır). Dev laptop'un IP'si DHCP ile değişkendir — dev'de dashboard `http://localhost:8081` üzerinden kullanılmalı, LAN linki paylaşılmamalı.
- **KDV Hesabı (2026-07-27, ADR-0002 kapsam dışı)**: Faturalama katsayıları net (KDV hariç) TL/kWh olarak tanımlandı. KDV oranı, KDV'li tutar üretimi ve fatura belgesi oluşturma kapsam dışı bırakıldı. İhtiyaç doğarsa `monthly_billing` tablosuna `vat_rate` + `*_try_gross` kolonları eklenerek çözülebilir; mevcut net alanlar korunur.
- **Kilitli Ay Override Akışı (2026-07-27, ADR-0002 kapsam dışı)**: `monthly_billing` satırı LOCKED olduktan sonra katsayı değiştirilemez. Kullanıcı hatası (yanlış OSB birim fiyatı girilmesi) durumunda düzeltme yolu yok. Gerekli olan: yönetici şifresiyle korunan, eski değeri audit_log'a yazan ve gerekçe zorunlu kılan ayrı bir override endpoint'i.
- **Rol Bazlı Yetkilendirme (2026-07-27, ADR-0002 kapsam dışı)**: Finansal veri yazımı (katsayı girişi/değişikliği) tek bir düz metin `DASHBOARD_ADMIN_PASSWORD` ortam değişkenine bağlı; tüm dashboard kullanıcıları için aynı şifre, kullanıcı bazlı rol ayrımı yok. `dashboard_users` tablosuna rol kolonu eklenip finansal endpoint'lerin bu role bağlanması gerekir.
- **Faturalama Geriye Dönük Doldurma (2026-07-27, ADR-0002 kapsam dışı)**: Billing katmanı devreye girmeden önce hesaplanmış aylar için `monthly_billing` satırı oluşmayacak. Bu aylar dashboard ve raporda TL alanı olmadan görünür. Gerekirse `valid_from` tarihli katsayılarla toplu backfill scripti yazılabilir.
- **`datetime.utcnow()` Deprecation (2026-07-27)**: Python 3.12'de `datetime.utcnow()` kullanımdan kaldırılmak üzere işaretlendi; smoke koşusunda 59 DeprecationWarning üretiyor. Kullanım proje geneline yayılmış durumda — `app/database/models.py`'deki tüm `default=datetime.utcnow` tanımları, `billing_repository.py`, `audit_repository.py` ve diğerleri. Timezone-aware `datetime.now(datetime.UTC)`'ye geçiş **ayrı bir temizlik görevi** olarak ele alınmalı; tek bir sprint içinde kısmi değiştirmek karışık stil yaratır. Dikkat: DB'de saklanan mevcut naive değerlerle karşılaştırma yapan sorgular gözden geçirilmeli (aware/naive karışımı `TypeError` üretir).
