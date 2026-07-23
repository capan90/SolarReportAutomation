# Changelog (Değişiklik Günlüğü)

Tüm önemli değişiklikler bu dosyada belgelenecektir.

---

## [Unreleased]

### GAOSB Headless Geçişi ve Launch Dayanıklılığı (2026-07-23 canlı olayı)
- **Kök neden**: DailySettlement görevi "Interactive only" tanımlı ve RDP oturumu X ile kapatılınca (disconnected) aktif masaüstü kalmıyor; GAOSB'nin zorunlu görünür tarayıcısı `launch_persistent_context` aşamasında 180 sn timeout ile ölüyor, günlük mahsuplaşma maili yerine hata maili gidiyordu. Aynı koşuda iSolar aşamasının (headless) sorunsuz geçmesi teşhisi doğruladı.
- **Headless=new Geçişi**: `GAOSB_HEADLESS_MODE` ortam değişkeni (varsayılan `new`) — günlük çekim artık tam Chromium'un yeni headless moduyla (`channel="chromium"`) koşuyor; aktif masaüstü oturumu gerekmiyor. Profildeki BotGuard clearance ile gerçek portala captcha'sız headless giriş laptop'ta doğrulandı. Captcha çıkarsa otomatik görünür moda düşülüyor (clearance yenileme headed şart); `headed` değeri eski davranışa dönüş anahtarı.
- **Launch Dayanıklılığı**: Launch timeout 180→60 sn; başarısızlıkta profil kilidini tutan artık Chromium süreçleri temizlenip bir kez daha deneniyor. `renew_session` da aynı ortak launch yolunu kullanıyor.
- **Net Hata Sınıflandırması**: Yeni `GaosbBrowserLaunchError` — hata maili "portalden rapor alınamadı" yerine olası nedeni (profil kilidi / aktif masaüstü oturumu yok) ve yapılacak kontrolü söylüyor.
- **tscon Sigortası**: `scripts/disconnect_keep_console.ps1` — sunucudan çıkarken RDP'yi X ile kapatmak yerine oturumu konsola devrederek masaüstünü aktif bırakır (parola/kilit politikası değişmez); headless mod sunucuda doğrulanana kadar yedek çözüm.

### E-posta Bildirim İyileştirmeleri
- **Konu Başlıkları**: Tüm bildirim senaryoları tek kurumsal formata geçirildi: "{emoji} Erdemsoft GES — {Durum} ({Tarih/Dönem})" (maksimum 60 karakter). Aylık rapor konusu artık ay adını içeriyor (örn. "Aylık Mahsuplaşma Raporu (Temmuz 2026)") — dönem, ek dosya adındaki YYYYMM deseninden çözülüyor (eski davranışta aylık maile yanlışlıkla günün tarihi düşüyordu).
- **Arıza Bildirimleri**: Üç durum gelen kutusunda emoji ile ayrışıyor: 🔧 Arıza Tespit Edildi / ⏳ Arıza Devam Ediyor / ✅ Arıza Giderildi.
- **Gövde Tasarımı**: Günlük/aylık rapor istatistikleri (Toplam Üretim, Toplam Tüketim, Toplam Mahsup, Şebekeden Çekiş, Fazla Satış) kalın etiketli, iki nokta hizalı ve açık yeşil arkaplanlı tabloya dönüştürüldü (`EmailSender._render_summary_html`, e-posta istemcisi uyumluluğu için inline CSS). Jobs katmanına dokunulmadı.
- **Teknik Detaylar**: Run ID, olay tipi, süre, sunucu ve commit bilgileri konu satırından çıkarılıp gövde altındaki "Teknik Detaylar" bölümüne taşındı (captcha maili dahil). Hata özetleri insan diline çevrildi ("Portala giriş yapılamadı", "Rapor dosyası indirilemedi" vb.).
- **Footer Birleştirme**: 6 template'teki üç farklı footer metni "Bu e-posta Erdemsoft GES Yönetim Sistemi tarafından otomatik olarak oluşturulmuştur." olarak tekleştirildi.
- **Doğrulama Notu**: pytest/ruff bu ortamda kurulu olmadığından otomatik test koşulamadı; py_compile syntax kontrolü ve 6 senaryoluk render/subject doğrulama scripti ile manuel doğrulama yapıldı (test ortamı kurulumu ayrı görev).

### Eklendi
- **Kaydet ve Yeniden Başlat (Dashboard)**: SMTP/bildirim ayarları kaydedildikten sonra kullanıcıya kontrollü yeniden başlatma teklif eden akış — onay diyalogu (~1 dk kesinti + oturum kapanması uyarısı ve zamanlanmış görev varsayımı notu), yönetici şifresi zorunlu `POST /api/settings/restart` endpoint'i (kabul/ret `audit_log`'a yazılır), `os._exit(10)` ile çıkış → Task Scheduler restart-on-failure taze `.env` ile geri getirir, "yeniden başlatılıyor" bekleme ekranı sunucu dönünce sayfayı otomatik yeniler. Kayıt notu netleştirildi ("gerekebilir" → "gerekir"; kök neden: frozen settings yalnızca process başlangıcında yüklenir). 4 smoke test eklendi (paket 164'e ulaştı; timer mock/iptal ile gerçek restart tetiklenmeden).
- **Dashboard Kalıcı Çalışma (Prod)**: `scripts/setup_dashboard_task_server.ps1` — APPS sunucusunda tek seferlik kurulum: `SolarReportAutomation_Dashboard` görevi (sistem açılışında, SYSTEM hesabı, çökmede 3 denemelik otomatik restart, süre limiti kapalı) + 8081 firewall kuralı + kurulum sonrası port/HTTP doğrulaması. `scripts/run_dashboard_hidden.vbs` gizli başlatıcısı proje kökünü script konumundan türetir (dev/prod aynı dosya, sabit yol yok) ve sunucuyu beklediği için exit kodu göreve yansır — restart-on-failure gerçekten çalışır. Dev laptop'ta aynı görev oturum açılışı tetikleyicisiyle kuruldu. Prod erişim adresi: `http://10.0.0.169:8081`.
- **Chatbot Doğal Dil İyileştirmeleri**: Tarih (bu ayki/geçen ayki/ocakta/önceki gün/son 2 hafta vb.) ve metrik (ne ürettik/ne harcadık/şebekeye sattık/rekor vb.) kapsamı genişletildi. Yeni `IntentParser` ile selam, yardım ve desteklenmeyen kıyas sorularında bağlama duyarlı yönlendirme; tarih anlaşılmadığında sessizce "dün"e düşme bug'ı giderildi. Salt-okunur; LLM/API kullanılmadı. 53 smoke test (`test_chatbot.py`, paket 160'a ulaştı).
- **Dashboard Mouse Tooltip**: sidebar, sekme, KPI kartı, sistem durumu, buton, filtre ve grafik başlıklarında (38 eleman) açıklayıcı hover tooltip'i — vanilla JS, event delegation, dokunmatik cihazlarda devre dışı, Chart.js ile çakışmıyor.
- **HealthChecker + Adapter Import Smoke Testleri**: sağlık kontrolü orkestrasyonu (severity birleştirme, timeout koruması, rapor yazımı — sahte kontrollerle ağsız) ve 10 kritik modülün import edilebilirlik güvencesi — 14 test. Smoke paketi 107 teste ulaştı.
- **Notification Servis Smoke Testleri**: politika kuralları ve fallback, kuyruk FIFO davranışı, force bypass, best-effort garantisi (sender hatası pipeline'ı bozmaz) — 6 test, stub sender ile SMTP/DB'siz.
- **Validation Smoke Testleri**: SchemaValidator severity ayrımları (CRITICAL/ERROR/WARNING/INFO), tip uyumluluk kuralları, null/unique ihlalleri ve JSON rapor yazımı — 7 test, in-memory sentetik profil/şema nesneleriyle.
- **Canonical Layer Smoke Testleri**: registry varsayılan mapping'leri, çift kayıt koruması, JSON export yapısı ve Türkçe karakter korunumu, alias→canonical çözümü, mapping veri bütünlüğü (benzersizlik, entity kümesi, required/nullable tutarlılığı, immutability) — 10 test.
- **Settlement Engine Smoke Testleri**: kümülatif→delta hesabı, negatif delta sıfırlama, önceki gün referans satırı, GES kolon ayrışması, GAOSB endeksin doğrudan tüketim alınması, Excel seri tarih çözümü, +1 gün filtresi ve mahsup matematiği (min/max + inner join) — 9 test, tamamı sentetik Excel dosyalarıyla.
- **Config Smoke Testleri**: SMTP_TO_* öncelik zinciri, bool/int çevrimleri, geçersiz APP_ENV → development fallback, validate() eksik değişken hatası ve Settings immutability — 10 test (importlib.reload ile izole, gerçek .env okunmadan).
- **Smoke Test Altyapısı**: `tests/smoke/` paketi + `pytest.ini` kuruldu; ilk modül `email_sender` (51 test — konu formatı, YYYYMM dönem çözümü, gövde render, SMTP güvenlik kapısı).
- **Geliştirme Altyapısı**: pytest + ruff kuruldu (`requirements-dev.txt`); pre-commit ruff kontrolü, mevcut 101 ihlal temizlenene kadar geçici warn-only; teknik borç kayıtları ROADMAP'e eklendi.
- **Geliştirme Altyapısı**: `CLAUDE.md` proje kılavuzu, Claude Code slash command'ları (`.claude/commands/`) ve pre-commit hook kaynağı (`.github/pre-commit.sh`) versiyon kontrolüne alındı.
- **Kullanıcı Yönetimi (Dashboard Auth)**: `DashboardAuth` sınıfına `update_user`, `change_password` ve `delete_user` metotları; `DashboardUser` ve `AuditLog` modelleri `app.database` paketinden dışa aktarıldı.
- **Denetim Günlüğü Genişletmesi**: Kullanıcı güncelleme ve silme işlemleri (başarısız denemeler dahil) aktör ve IP bilgisiyle `audit_log` tablosuna kaydediliyor.
- **Dashboard Smoke Test Genişletmesi**: 401/login/token akışı ve kullanıcı yönetimi API'leri (`/api/users` CRUD, şifre değiştirme, kendini silme koruması) test kapsamına alındı.

### Değiştirildi
- **E-Posta Durum Rozeti Üç Durumlu**: Sistem Durumu'ndaki e-posta rozeti "eksik" durumunu (SMTP açık ama sunucu/kullanıcı/şifre/alıcı alanlarından biri boş) daha önce PASİF diye gösterip yanlış teşhise yol açıyordu. Artık AKTİF (yeşil) / EKSİK (sarı) / PASİF (kırmızı, SMTP_ENABLED kapalı) ayrı gösteriliyor; her durum ne yapılması gerektiğini anlatan hover tooltip'i taşıyor.
- **Dashboard Kullanıcı Kartı**: Sağ üstteki kullanıcı bilgisi ve "Son güncelleme" pill'leri tek birleşik kartta toplandı (üst üste binme giderildi); baş harfli avatar, hover'da belirginleşen nötr çıkış butonu ve canlılık hissi veren pulse noktası eklendi. Logout ve saat güncelleme mantığı değişmedi.
- **Depo Düzeni**: `docs/PROJECT_CONTEXT.md`, `docs/prompts/`, Mimari Keşif Raporu (güvenli dosya adına taşındı), `run_settlement.bat` ve `tests/test_historical_api.py` versiyon kontrolüne alındı; `config/isolar_browser_profile/`, `outputs/reports/` ve `outputs/test_*` `.gitignore`'a eklendi; kullanılmayan `package*.json` silindi.
- **Dashboard**: Ana Sayfa Sistem Durumu'ndaki "Mahsup Edilen" KPI kartı kaldırıldı (backend hesaplaması ve diğer ekranlardaki mahsup gösterimleri değişmedi); KPI satırı 4 sütunlu düzene geçti.
- **Güvenlik**: Smoke testteki sabit admin şifresi koddan çıkarıldı; `.env` üzerindeki `DASHBOARD_TEST_ADMIN_PASSWORD` değişkeninden okunuyor.
- **`.gitignore`**: `node_modules/`, `outputs/manual_tests/` ve `.claude/settings.local.json` ignore listesine eklendi.

### Sprint S2 — Zamanlanmış İş Dayanıklılığı (docs/sprints/PLAN-S2.md)
- **Kök neden (2026-07-22 canlı olayı)**: DailySettlement görevi WorkingDirectory boş tanımlandığından System32 cwd'siyle çalışıyor, `Path("outputs/reports")` göreli yolu System32 altına çözülüyor ve iş "BAŞLADI" satırından sonra tek log üretmeden exit 1 ile ölüyordu — hata stderr'e gittiği için görünmüyor, günlük rapor maili sessizce kesiliyordu (21-22 Temmuz). Görev tanımları sunucuda düzeltildi (WorkingDirectory eklendi, aylık görev dahil); bu sprint kod tarafını kalıcı kapattı.
- **Mutlak Çıktı Yolları**: `daily_settlement_job`, `monthly_settlement_job` ve iSolar extractor screenshot dizini `PROJECT_ROOT` kalıbına geçirildi — görev tanımı yanlış bile olsa işler System32'ye yazamaz/ölemez. GAOSB extractor `output_dir`'i çağırandan aldığı için otomatik kapsandı.
- **Sessiz Ölüm Uyarısı**: yeni `app/notifications/system_alert.py` — `main.py`'nin settlement/settlement-monthly `except` dalları yakalanmamış istisnada SMTP_TO_SYSTEM'e hata + son 40 log satırıyla uyarı maili atıyor (best-effort, exit kodu korunur). Graceful FAILED yolu zaten `notify_pipeline` ile maillendiğinden çift bildirim oluşmaz.
- **Captcha Mail Güvenliği**: `app/sources/gaosb/extractor.py`'deki çıplak `int(GAOSB_ALERT_SMTP_PORT)` `_env_int`'e geçirildi — boş değer artık captcha uyarısını crash edemez.
- **GES Durum Maili Retry**: `send_status_email` 3 deneme / 10 sn arayla — geçici ağ hatası (2026-07-21 `getaddrinfo failed` örneği) kritik arıza uyarısını artık kaybettirmiyor. 5 yeni smoke test (paket 179'a ulaştı).

### Sprint S1 — Oturum, Log Erişimi ve Ayar Güvenliği (docs/sprints/PLAN-S1.md)
- **Oturum Sayfa/Yetki Mirası Kapatıldı**: Çıkış yapan kullanıcının açık sayfası ve developer oturumu sonraki kullanıcıya geçiyordu — çıkışta artık dev token düşürülüyor (`devLogout`), ayar kilidi kapanıyor ve ana sayfaya dönülüyor; her yeni giriş ana sayfadan başlıyor. Güvenlik notu: dev token `sessionStorage`'da çıkışta silinmiyordu, ikinci kullanıcı loglara şifresiz erişebiliyordu — kapatıldı.
- **Sistem Ayarları Şifre Kilidi**: Ayarlar sayfası Developer paneliyle aynı kalıpla kilitlendi — görüntülemek için geliştirici şifresi gerekiyor (mevcut `/api/dev/login`, 8 saatlik ortak token; backend değişikliği yok). Kayıt endpoint'lerindeki yönetici şifresi zorunluluğu ayrıca sürüyor.
- **Ayar Kartlarına Uyarı Kutuları**: SMTP ve bildirim kartlarına 2026-07-21 olayının derslerini özetleyen dikkat kutuları eklendi (boş alan değiştirilmez, şifre boş = korunur, port 1-65535, alıcı kutusu tamamen boşaltılmaz, kayıt sonrası yeniden başlat).
- **Uyarı Mailine Log Kuyruğu**: "Dashboard Kapalı" uyarı e-postasına en güncel log dosyasının son 40 satırı gömülüyor (HTML escape'li) — sunucuya erişim olmadan çökme nedeni görülebiliyor; log okunamazsa mail yine gider, nedeni belirtilir.
- **Not — Chrome "şifrenizi değiştirin" uyarısı**: Dashboard kaynaklı değil; Chrome Şifre Denetimi girilen şifreyi bilinen sızıntı listelerinde bulunca gösteriyor. Çözüm kod değil, kullanıcı şifrelerinin güçlü/benzersiz değerlerle değiştirilmesi.

### Eklendi (Dashboard Dayanıklılık)
- **Paylaşımsız Port Bağlama**: `HTTPServer` varsayılanındaki `SO_REUSEADDR`, elle başlatılan ikinci bir dashboard instance'ının görevin instance'ıyla aynı anda 8081'i dinlemesine izin veriyordu (istekler rastgele dağılıp "ayar uygulanmadı" hayalet hataları üretiyordu — 2026-07-21 canlı olayı). `_ExclusiveHTTPServer` ile kapatıldı; ikinci bind artık WinError 10048 ile anında reddediliyor ve net bir hata loglanıyor.
- **Kapalı-Kalma E-posta Uyarısı**: `run_dashboard_hidden.vbs` art arda 4 çökmede pes ettiğinde `scripts/send_dashboard_down_alert.py` çağrılıyor — sistem alıcısına (SMTP_TO_SYSTEM, yedek SMTP_TO) "🔴 Erdemsoft GES — Dashboard Kapalı" konulu, sunucu adı + aksiyon adımlı uyarı gidiyor. Best-effort: gönderim hatası VBS'i bloklamaz, sonuç her durumda loglanır. 4 smoke test (paket 171'e ulaştı).

### Düzeltildi
- **Boş SMTP_PORT Dashboard'ı Çökertiyordu**: Kök neden zinciri: `/api/settings/config` yanıtında `smtp_port` alanı olmadığından ayarlar formundaki Port kutusu her yüklemede boş kalıyor, `saveSmtp()` boş portu gönderiyor ve backend'in iç içe `smtp` yolu (`val is not None` kontrolü boş string'i geçirdiğinden) `.env`'e `SMTP_PORT=` yazıyordu; restart sonrası `config.py` `int("")` ile ValueError verip dashboard'ı başlatılamaz bırakıyordu (`os.environ.get` varsayılanı yalnızca anahtar *yokken* devreye girer, boş değerde girmez). Üç katmanlı düzeltme: (1) config yanıtına `smtp_port` eklendi (prefill artık çalışıyor) ve backend port'u doğruluyor — boş ("Port boş olamaz") veya 1-65535 dışı değerler reddediliyor, boş host/username/password artık "değiştirme" sayılıp `.env`'den silinmiyor (aynı bug her kayıtta `SMTP_PASSWORD`'ü de boşaltıyordu); (2) `config.py`'ye `_env_int`/`_env_bool` güvenli parse yardımcıları — boş/bozuk ortam değişkeninde loglayıp varsayılana düşer, hiçbir env değeri config import'unu crash edemez; (3) `saveSmtp()` frontend port format kontrolü. 3 yeni smoke test (boş/geçersiz int ve boş bool senaryoları).
- **Dashboard Restart Sonrası Geri Gelmeme**: "Kaydet ve Yeniden Başlat" akışı Task Scheduler'ın restart-on-failure ayarına dayanıyordu; ancak bu ayarın yalnızca görev *başlatılamadığında* devreye girdiği, çalışan programın sıfır olmayan exit koduyla bitmesini failure saymadığı deneyle doğrulandı (dashboard restart sonrası kapalı kalıyordu). Yeniden başlatma döngüsü `scripts/run_dashboard_hidden.vbs` içine taşındı: exit 10 (kontrollü restart) → anında yeniden başlatma (kesinti ~1 dk yerine birkaç saniye); diğer sıfır olmayan kodlar (çökme) → 1 dk arayla en fazla 3 deneme; exit 0 → temiz kapanış. Çökme dalı canlı ortamda doğrulandı (process kill → ~60 sn'de otomatik geri geldi). UI metinleri yeni süre ve varsayımla güncellendi.
- **Restart Butonu Kontrastı**: Onay modalındaki "Yeniden Başlat" butonu renk varyantsız `.btn` sınıfıyla kaldığından tarayıcı varsayılan açık zemininde beyaz yazı okunmuyordu; `.btn.red` varyantı eklendi (tema `--red` değişkeni) ve buton kırmızıya bağlandı.
- **PlantStatusJob WinError 5**: Task Scheduler System32 cwd'siyle başlattığında göreli `config/isolar_browser_profile` yolu korumalı `System32\config` dizinine çözülüp erişim hatası veriyordu — santral izleme yalnızca dashboard tetiklerinde çalışabiliyordu. Profil ve 4 şablon yolu `PROJECT_ROOT`'a sabitlendi; zamanlanmış izleme (15 dk) artık gerçekten çalışıyor.
- **PlantStatusJob Konsol Penceresi**: Zamanlanmış çalışmada `python.exe`'nin masaüstünde açtığı konsol penceresi gizlendi. Görev artık `wscript.exe` + `scripts/run_plant_status_hidden.vbs` gizli başlatıcısıyla çağrılıyor (pencere stili 0). python.exe korundu (pythonw.exe'nin `print()` → RuntimeError riski elendi), headless=True tarayıcı ve login akışı değişmedi.

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
