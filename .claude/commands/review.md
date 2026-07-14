# /review

Değişiklikleri Solar mimarisine ve proje kurallarına göre değerlendir.

## Adımlar

1. `git diff HEAD` çalıştır.
2. CLAUDE.md kurallarını ve ARCHITECTURE.md'yi oku.
3. İlgili sprint planını bul ve karşılaştır.
4. Aşağıdaki kriterleri kontrol et.
5. Sonucu kullanıcıya sun.

## Kontrol Listesi

### Mimari Sınırlar
- [ ] Canonical Layer (EnergyDataPoint, MeterReading, PlantRecord) değiştirilmedi
- [ ] Dashboard ETL tetiklemiyor, DB'ye yazmıyor
- [ ] Adapter kodu platform katmanına sızmadı
- [ ] Portal-özel logic adapter içinde kaldı
- [ ] Yeni bağımlılık varsa ADR yazıldı

### Kod Kalitesi
- [ ] Sessiz hata yok (bare except / pass / swallowed exception)
- [ ] Secret / credential kodda açık değil
- [ ] Discovery / spike kodu production'a karışmadı (scratch/ kontrolü)
- [ ] Dosya sayısı ≤ 10, satır tahmini makul

### Portal Özellikleri (adapter değiştiyse)
- [ ] iSolar: x-access-key config'den okunuyor (hardcode yok)
- [ ] iSolar: delta hesabı yapılıyor (kümülatif ham veri kalmadı)
- [ ] GAOSB: VIEWSTATE her POST öncesi taze alınıyor
- [ ] GAOSB: FIXED_VALUE delta hesabı var

### Test & Dokümantasyon
- [ ] `python main.py --health` yeşil
- [ ] Smoke test geçiyor
- [ ] CHANGELOG.md güncellendi
- [ ] Gerekiyorsa ADR eklendi

## Çıktı

**Geç** — commit yapılabilir.
**Bekle** — şu sorunlar var: [liste]
**Engelle** — kritik ihlal: [açıklama]
