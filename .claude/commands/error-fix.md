# /error-fix

Hata çıktısını al, teşhis et, düzeltme planı sun — kod yazmadan önce onay al.

## Kullanım

Terminal çıktısını kopyala, komutla birlikte yapıştır:
```
/error-fix
[hata çıktısı buraya]
```

## Adımlar

1. Hata mesajından şunları ayıkla: tip, dosya, satır, mesaj.
2. Stack trace'deki dosyaları oku.
3. CLAUDE.md kurallarını kontrol et — mimari ihlal var mı?
4. Solar'a özgü kontroller:
   - iSolar hatası mı? → appKey rotation, RSA şifreleme, rate limit?
   - GAOSB hatası mı? → session expired, VIEWSTATE stale, Cloudflare?
   - Canonical Layer hatası mı? → delta hesabı, tip uyumsuzluğu?
   - ETL hatası mı? → validation pipeline, DB transaction?
5. Kök nedeni tek cümleyle yaz.
6. Düzeltme planını sun.
7. **Onay gelmeden kod yazma.**
8. Onay gelince düzelt → test çalıştır → /review yap.

## Çıktı Formatı

```
## Hata Teşhisi

Tip      : [ImportError / SessionExpired / DeltaCalculationError / ...]
Dosya    : [path:satır]
Kök neden: [tek cümle]

Solar bağlamı: [iSolar / GAOSB / Canonical / ETL / Dashboard / Diğer]
Mimari ihlal : [Evet — açıkla / Hayır]

## Düzeltme Planı
1. ...
2. ...

## Test
[Düzeltme sonrası çalıştırılacak komut]

Onaylıyor musunuz?
```
