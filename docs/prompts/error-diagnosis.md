# Prompt: Hata Teşhisi

## Kullanım
Terminal çıktısını kopyala, [...] alanlarını doldur, gönder.
Alternatif: `/error-fix` komutuyla doğrudan yapıştır.

---

Aşağıdaki hatayı teşhis et.

**Ortam:**
- Sprint / Modül: [Örn: Sprint 17 / GAOSB Adapter]
- Komut: [python main.py --health / pytest / ...]
- Ne yapılırken çıktı: [Örn: GAOSB'den veri çekerken]

**Hata çıktısı:**
```
[BURAYA YAPISTIR]
```

**Son değişiklik:**
[En son ne eklendi / değiştirildi?]

**Beklenen davranış:**
[Ne olması gerekiyordu?]

Önce kök nedeni tek cümleyle tanımla.
Sonra düzeltme planını sun — kod yazma, önce onaylayayım.
iSolar hatası ise: appKey / RSA / rate limit mi?
GAOSB hatası ise: session / VIEWSTATE / Cloudflare mı?
Mimari ihlal varsa belirt.
