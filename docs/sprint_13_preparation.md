# Sprint 13 Hazırlık ve Mimari Tasarım Dokümanı: Metrics & Observability

Bu doküman, bir sonraki sprint olan **Sprint 13 (Metrikler ve Gözlemlenebilirlik)** için kapsamı, mimari vizyonu, etkilenecek katmanları ve hazırlık kriterlerini (Definition of Ready) tanımlar.

---

## 1. Sprint Amacı

ETL motorumuzun ve canlandırma sistemimizin (Health & Notification) üretim ortamında (Production) ürettiği performans metriklerini toplamak, izlenebilirliği (observability) artırmak ve verileri Dashboard / Analytics modüllerinin kolayca tüketebileceği bir altyapıya kavuşturmak.

---

## 2. Mimari Vizyon (Architecture Vision)

Sprint 11A'da kurduğumuz `app/monitoring/` üst modülü altındaki boş `metrics/` dizini doldurularak metrik toplama yeteneği kazandırılacaktır.
- **Push vs Pull**: Metrikler uygulama içinde toplanarak veritabanına yazılacak (Push model) ve console/logs üzerinden dış izleme araçlarının (örn: Prometheus) çekebileceği (Pull model) bir formata dönüştürülecektir.
- **Sıfır Performans Kaybı**: Metrik toplama işlemleri ana ETL akışını engellememeli, asenkron veya hızlı çalışmalıdır.

---

## 3. Modül Sınırları ve Etkilenecek Katmanlar

### Modül Sınırları (`app/monitoring/metrics/`)
- **MetricsCollector**: CPU, RAM kullanımı, Disk okuma/yazma süreleri, veritabanı sorgu gecikmeleri ve Playwright sayfa yükleme metriklerini toplayan modül.
- **MetricsRegistry**: Toplanan metrikleri geçici olarak tutan ve veritabanı / log katmanına gönderen veri havuzu.

### Etkilenecek Katmanlar:
- **`app/monitoring/metrics/` (Yeni)**: Metrik toplama motoru ve veri modelleri.
- **`app/database/models.py` (Güncellenecek)**: Metriklerin kaydedileceği `performance_metrics` tablosunun ORM modeli.
- **`app/orchestrator/etl_orchestrator.py` (Güncellenecek)**: Aşamaların başlangıç/bitiş sürelerini metrik motoruna bildirme entegrasyonu.

---

## 4. Riskler ve Önlemler

| Risk | Tanım | Önlem |
| :--- | :--- | :--- |
| **Performans Kaybı** | Metrik toplayıcıların CPU/RAM sorguları nedeniyle ETL süresini uzatması. | Metrik toplama sıklığı dar tutulacak veya her aşama bittiğinde tek seferlik hızlı sistem sorgusu yapılacaktır. |
| **Boyut Şişmesi (Disk/DB)** | Çok sık yazılan metriklerin veritabanını şişirmesi. | Metrik verileri için otomatik temizleme (purge) veya günlük özetleme (aggregation) mantığı kurgulanacaktır. |

---

## 5. Başarı Kriterleri

- Her ETL pipeline çalışmasında CPU, RAM ve Disk alanı metriklerinin en az 1 kez toplanması.
- Playwright adımlarının (Login, Navigation, Download) sayfa yüklenme sürelerinin (milisaniye) ölçülebilmesi.
- Toplanan metriklerin `performance_metrics` tablosuna başarıyla yazılması.
- Metriklerin console/log dosyasına Prometheus uyumlu formatta basılabilmesi.

---

## 6. Definition of Ready (DoR)

- [x] Sprint 12 başarıyla kapatıldı ve Release Candidate (RC-1) frozen ilan edildi.
- [x] `performance_metrics` için tablo şeması taslak olarak belirlendi.
- [x] CPU/Memory metrikleri için Python standart kütüphanelerinin (`psutil` vb.) kullanımı veya sıfır dış bağımlılık tercih kararı netleşti.
