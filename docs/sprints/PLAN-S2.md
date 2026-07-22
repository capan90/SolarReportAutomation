# Sprint S2 — Zamanlanmış İş Dayanıklılığı: Mutlak Yollar + Sessiz Ölüm Uyarısı
Tarih: 2026-07-22

## Hedef
Zamanlanmış işlerin çalışma dizininden bağımsız hale getirilmesi (System32 hata sınıfının kodda öldürülmesi) ve bir iş yakalanmamış istisnayla sessizce öldüğünde log kuyruklu uyarı maili gönderilmesi.

## Bağlam (2026-07-22 canlı olayı)
DailySettlement görevi WorkingDirectory boş olduğu için System32 cwd'siyle
çalışıyor, `Path("outputs/reports")` göreli yolu System32 altına çözülüyor ve
iş "BAŞLADI" satırından sonra tek log üretmeden exit 1 ile ölüyordu (hata
stderr'e gidiyor, log yok, mail yok). Görev tanımları sunucuda düzeltildi;
bu sprint aynı hatanın kod tarafını kalıcı kapatır.

## Kapsam
1. **PROJECT_ROOT yolları**: `daily_settlement_job.py:58`,
   `monthly_settlement_job.py:267`, `isolar/extractor.py:513` (screenshot)
   göreli yolları PROJECT_ROOT kalıbına geçer (plant_status_job.py:19 örneği).
   GAOSB extractor output_dir'i çağırandan aldığı için job düzeltmesi onu da kapsar.
2. **Sessiz ölüm uyarısı**: yeni `app/notifications/system_alert.py` —
   `send_job_failure_alert(job_adi, hata)`: SMTP_TO_SYSTEM'e (yedek SMTP_TO)
   marka standardında konu + hata + son 40 log satırı. `main.py`'nin settlement
   ve settlement-monthly dallarındaki `except` bloklarına bağlanır (yalnızca
   yakalanmamış istisna — graceful FAILED zaten notify_pipeline ile mail atıyor,
   çiftleme olmaz). Best-effort: uyarı gönderilemezse loglanır, exit kodu değişmez.
3. **Captcha mail güvenliği**: `app/sources/gaosb/extractor.py:162` çıplak
   `int(...)` → `app.core.config._env_int` (boş GAOSB_ALERT_SMTP_PORT crash'i ölür).
4. **GES durum maili retry**: `plant_status_job.send_status_email` 3 deneme
   (aralarında 10 sn) — dünkü `getaddrinfo failed` gibi geçici ağ hatasında
   uyarı kaybolmasın.

## Kapsam Dışı
- Dashboard tarafındaki göreli okuma yolları (`web_server.py:23,192,204`,
  `settlement_repository.py:188,195`) — VBS başlatıcı cwd'yi garanti ediyor,
  risk düşük; ayrı küçük iş olarak backlog'a.
- NotificationService/EmailSender değişikliği yok.
- Canonical Layer / ETL dokunulmaz.

## Etkilenecek Dosyalar
| Dosya | Değişiklik |
|---|---|
| app/jobs/daily_settlement_job.py | PROJECT_ROOT output_dir |
| app/jobs/monthly_settlement_job.py | PROJECT_ROOT output_dir |
| app/extractors/isolar/extractor.py | PROJECT_ROOT screenshot dizini |
| app/sources/gaosb/extractor.py | _env_int ile güvenli port |
| app/jobs/plant_status_job.py | send_status_email retry (3×, 10 sn) |
| main.py | except dallarında failure alert çağrısı |
| tests/smoke/test_system_alert.py | YENİ — konu/gövde/retry testleri |
| CHANGELOG.md | güncelleme |

## Yeni Dosyalar
| Dosya | Amaç |
|---|---|
| app/notifications/system_alert.py | İş çökme uyarı maili (log kuyruklu, best-effort) |

## Başarı Kriterleri
- [ ] Smoke paketi geçiyor (174 + yeniler)
- [ ] Jobs, System32 cwd simülasyonunda bile proje köküne yazar (test)
- [ ] main.py except yolu alert çağırır (test, monkeypatch ile ağsız)
- [ ] Canonical Layer değişmedi

## Riskler
| Risk | Olasılık | Önlem |
|---|---|---|
| Retry, PlantStatus 15 dk periyodunu geciktirir | Düşük | Toplam ek bekleme ≤20 sn |
| Alert de ölürse exit kodu maskelenir | Düşük | try/except; exit kodu her durumda korunur |

## ADR Gerekiyor mu?
[x] Hayır

## Tahmini Dosya / Satır
Dosya sayısı: 9 (max 10)
Satır tahmini: ~220 (max ~300)
