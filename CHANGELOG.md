# Changelog (Değişiklik Günlüğü)

Tüm önemli değişiklikler bu dosyada belgelenecektir.

---

## [Unreleased]

### Kaldırıldı
- **Güvenlik**: Tracked durumdaki 9 `scratch/` dosyası Git index'ten çıkarıldı (diskte korunuyor); `scratch/` klasörü `.gitignore`'a eklendi. Not: `scratch/create_users.py` düz metin admin şifresi içeriyordu — şifre Git geçmişinde kaldığı için rotasyonu önerilir.

---

## [1.0.0-GA] - 2026-06-30

### Eklendi
- **Multi Source Extraction**: iSolarCloud haricinde farklı güneş paneli portallarını destekleyen dinamik `SourceRegistry` ve `ISourceExtractor` adaptör mimarisi.
- **Tarihsel Analiz Motoru**: Günlük, haftalık ve aylık üretim toplamları, zirve gün tespiti ve kesintisiz ardışık tarih arama ile kayıp gün (Missing Day) tarama algoritmaları.
- **Yönetici Arayüzü (Settings & PDF/Excel Export)**: Arayüze salt-okunur sistem ayarları (Settings) paneli, tablolar için Türkçe karakter uyumlu Excel/CSV dışa aktarım desteği ve print-friendly PDF baskı çıktı şablonları eklendi.
- **Windows Task Scheduler & Otomatik Yedekleme**: Günlük otomatik PostgreSQL yedeklerini alan ve 14 günlük retention kuralları işleten otomatik yedekleme/kurtarma motorları (`scripts/db_backup.py`).
- **Kurulum Doğrulama Testi**: Tüm sistemi test edip 100 üzerinden Canlıya Hazırlık Skoru üreten `verify_installation.bat` aracı.
- **Log Rotasyonu**: Disk dolmasını engelleyen `RotatingFileHandler` log yapılandırması.
