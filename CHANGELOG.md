# Changelog (Değişiklik Günlüğü)

Tüm önemli değişiklikler bu dosyada belgelenecektir.

---

## [Unreleased]

### Eklendi
- **Geliştirme Altyapısı**: `CLAUDE.md` proje kılavuzu, Claude Code slash command'ları (`.claude/commands/`) ve pre-commit hook kaynağı (`.github/pre-commit.sh`) versiyon kontrolüne alındı.
- **Kullanıcı Yönetimi (Dashboard Auth)**: `DashboardAuth` sınıfına `update_user`, `change_password` ve `delete_user` metotları; `DashboardUser` ve `AuditLog` modelleri `app.database` paketinden dışa aktarıldı.
- **Denetim Günlüğü Genişletmesi**: Kullanıcı güncelleme ve silme işlemleri (başarısız denemeler dahil) aktör ve IP bilgisiyle `audit_log` tablosuna kaydediliyor.
- **Dashboard Smoke Test Genişletmesi**: 401/login/token akışı ve kullanıcı yönetimi API'leri (`/api/users` CRUD, şifre değiştirme, kendini silme koruması) test kapsamına alındı.

### Değiştirildi
- **Güvenlik**: Smoke testteki sabit admin şifresi koddan çıkarıldı; `.env` üzerindeki `DASHBOARD_TEST_ADMIN_PASSWORD` değişkeninden okunuyor.
- **`.gitignore`**: `node_modules/`, `outputs/manual_tests/` ve `.claude/settings.local.json` ignore listesine eklendi.

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
