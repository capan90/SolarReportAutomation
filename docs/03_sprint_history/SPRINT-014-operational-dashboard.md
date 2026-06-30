# Sprint 14: Operational Dashboard Platform

- **Başlangıç Tarihi**: 2026-06-30
- **Bitiş Tarihi**: 2026-06-30
- **Sürüm Hedefi**: Release Candidate RC-3

## Sprint Amaçları ve Kazanımları
Bu sprintin temel amacı, platformun tüm alt yapılarından (Sağlık Kontrolü, Metrikler, Retry Olayları, E-Posta Bildirimleri ve Denetim Kayıtları) elde edilen verileri, sıfır dış bağımlılıkla ve salt-okunur (read-only) güvenlik ilkeleri doğrultusunda tek bir merkezden izleyen **Operational Dashboard** web uygulamasını geliştirmekti.

### Tamamlanan Görevler:
1. **Dashboard Server**: `http.server` temelli, localhost'a bind edilen, GET-only REST controller ve static dosya sunucusu.
2. **DTO & Read Model Mappings**: DB modellerini doğrudan expose etmeyen, `ExecutiveSummaryDto`, `PipelineRunDto` ve `HealthStatusDto` modelleri.
3. **Responsive UI**: HTML5, Vanilla CSS ve yerel vendor olarak sunulan Chart.js ile zengin koyu tema (dark mode) destekli operasyon ekranı.
4. **Güvenlik Sınırları**: Stack trace ve secrets sızıntısı engellendi, Path Traversal saldırılarına karşı çözümlenmiş yol kontrolleri (resolve) eklendi.
5. **Duman Testleri**: Bütün endpoint'lerin ve metod engellemelerinin (HTTP 405) doğrulandığı entegrasyon testleri yazıldı.
