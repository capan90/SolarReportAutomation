# Sprint S1 — Dashboard Oturum, Log Erişimi ve Ayar Güvenliği Revizyonları
Tarih: 2026-07-22

## Hedef
Dashboard'da oturum geçişlerindeki sayfa/yetki sızıntılarını kapatmak, dashboard kapalıyken log erişimi sağlamak ve sistem ayarları sayfasını şifre korumasına alıp kullanıcı uyarılarıyla donatmak.

## Madde Analizi

### 1. "Şifrenizi değiştirin" tarayıcı uyarısı — KOD DEĞİŞİKLİĞİ YOK
Bu uyarı dashboard'dan değil **Chrome'un kendisinden** geliyor (Google Şifre Denetimi):
girilen kullanıcı adı + şifre kombinasyonu bilinen veri sızıntısı listelerinde
bulununca Chrome bu balonu gösterir. Sunucu tarafından kapatılamaz.
Kalıcı çözüm: dashboard kullanıcı şifrelerini güçlü ve benzersiz değerlerle
değiştirmek (loglarda 6 karakterlik şifre görünüyor — zayıf). Dashboard'ın mevcut
şifre değiştirme akışı kullanılır; kod işi yok, kullanıcı aksiyonu.

### 2. Çıkış sonrası yeni kullanıcı eski sayfada açılıyor
Neden: `logout()` yalnızca login perdesini gösteriyor; arkadaki DOM son sayfada
kalıyor. Yeni giriş `hideLoginScreen()` + `loadHome()` çağırıyor ama görünen
sayfayı değiştirmiyor.
**Bonus güvenlik bulgusu:** `devToken` sessionStorage'da çıkışta SİLİNMİYOR —
developer paneli açılmış bir oturumdan çıkılınca, sonraki kullanıcı developer
loglarına şifresiz erişebiliyor. Aynı düzeltmede kapatılacak.

### 3. Dashboard kapalıyken log erişimi
Kapalı-kalma uyarı e-postasına son ~40 log satırı eklenir → sunucuya hiç
erişmeden neden görülür. (show_last_logs.ps1 seçeneği kullanıcı kararıyla
İPTAL: sunucuya fiziksel/RDP erişim her zaman mümkün olmayabilir; mail
her yerden okunur, en stabil kanal.)

### 4. Sistem ayarları: şifre koruması + uyarı metinleri
a) Ayarlar sayfası, Developer paneliyle aynı kalıpla kilitlenir: sayfa açılınca
   şifre ekranı; doğrulama mevcut `/api/dev/login` endpoint'iyle (kullanıcı
   kararı: DEVELOPER_PASSWORD kullanılacak) — backend değişikliği gerekmez,
   aynı 8 saatlik token paylaşılır, çıkışta ikisi birden kilitlenir.
   Kayıt endpoint'lerindeki yönetici şifresi zorunluluğu aynen kalır.
b) SMTP/bildirim kartlarına kısa uyarı kutusu: boş bırakılan alan değiştirilmez;
   şifre alanı boş = mevcut şifre korunur; port 1-65535; alıcıları virgülle ayır,
   alıcı kutusunu tamamen boşaltma; değişiklik sonrası "Kaydet ve Yeniden Başlat".

## Kapsam Dışı (yapılmayacaklar)
- Chrome uyarısını bastırmaya çalışmak (teknik olarak imkânsız).
- Ayrı log-viewer servisi / ikinci web sunucusu (yeni tekil hata noktası).
- Kullanıcı rol sistemi (admin/normal ayrımı) — ayrı sprint konusu.
- ETL, Canonical Layer, settlement — dokunulmaz.

## Etkilenecek Dosyalar
| Dosya | Değişiklik türü |
|---|---|
| app/dashboard/static/index.html | güncelleme (madde 2, 4a, 4b) |
| app/dashboard/web_server.py | güncelleme (madde 4a: unlock endpoint + token) |
| scripts/send_dashboard_down_alert.py | güncelleme (madde 3a: log kuyruğu eki) |
| tests/smoke/test_dashboard_down_alert.py | güncelleme (3a testi) |
| tests/smoke/test_dashboard_restart.py | güncelleme (4a endpoint testleri) |
| CHANGELOG.md | güncelleme |

## Yeni Dosyalar
| Dosya | Amaç |
|---|---|
| scripts/show_last_logs.ps1 | Dashboard kapalıyken son logları Notepad'de açan yardımcı (madde 3b) |

## Uygulama Adımları
1. Madde 2: `logout()` içine ana sayfaya dönüş + `devLogout()` çağrısı; giriş
   başarısında da ana sayfa aktifleştirme (savunma amaçlı çift taraf).
2. Madde 4a: `web_server.py`'ye `_SETTINGS_TOKENS` + `/api/settings/unlock`
   (dev-token kalıbının aynısı, DASHBOARD_ADMIN_PASSWORD ile); index.html'de
   ayarlar sayfasına kilit ekranı; çıkışta settings token'ı da temizlenir.
3. Madde 4b: ayar kartlarına uyarı kutusu metinleri.
4. Madde 3a: uyarı mailine son 40 log satırı (okunamazsa "log okunamadı" notu,
   best-effort bozulmaz); 3b: show_last_logs.ps1.
5. Smoke testler: unlock endpoint (yanlış/doğru şifre, token'sız erişim),
   mail gövdesinde log bölümü.
6. CHANGELOG + commit (onayla).
7. Push → sunucuda pull → görev restart → canlı doğrulama (madde 2 ve 4 senaryoları).

## Başarı Kriterleri
- [ ] python main.py --health yeşil
- [ ] Smoke test geçiyor (mevcut 171 + yeniler)
- [ ] Canonical Layer değişmedi
- [ ] Çıkış → farklı kullanıcıyla giriş → ana sayfada açılıyor, dev paneli kilitli
- [ ] Ayarlar sayfası şifresiz görüntülenemiyor
- [ ] Uyarı maili log kuyruğunu içeriyor
- [ ] show_last_logs.ps1 sunucuda çift tıkla çalışıyor

## Riskler
| Risk | Olasılık | Önlem |
|---|---|---|
| Ayarlar kilidi mevcut kullanıcı alışkanlığını bozar | Düşük | Token 8 saat geçerli, oturum başına 1 kez şifre |
| Log eki maili şişirir / hassas veri sızdırır | Orta | 40 satırla sınırla; loglarda secret zaten yok (proje kuralı) |
| index.html'de oturum akışına dokunurken regresyon | Orta | Değişiklik 3 küçük noktada; canlı senaryo testi başarı kriterinde |

## ADR Gerekiyor mu?
[x] Hayır — yeni teknoloji yok, mevcut kalıplar (dev-token, VBS, smoke) genişletiliyor.

## Tahmini Dosya / Satır
Dosya sayısı: 7 (max 10)
Satır tahmini: ~260 (max ~300)

## Not
CLAUDE.md'nin referans verdiği ARCHITECTURE.md ve docs/sprints/ henüz mevcut değildi;
bu dosya klasörün ilk planıdır (S1).
