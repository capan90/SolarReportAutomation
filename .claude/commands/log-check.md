# /log-check

Log dosyalarını tara, hata ve uyarıları özetle.

## Kullanım

```
/log-check           ← bugünün logları
/log-check 2026-07-13
/log-check error     ← sadece ERROR seviyesi
```

## Adımlar

1. Filesystem MCP ile `logs/` klasörünü listele.
2. Parametre yoksa bugünün log dosyasını oku.
3. Şunları say ve listele:

```
ERROR   → tümünü göster (dosya:satır + mesaj)
WARNING → ilk 10'unu göster
INFO    → sadece ETL start/end event'leri
```

4. Portal bazlı gruplama yap:
   - iSolar hataları (appKey, RSA, rate limit, session)
   - GAOSB hataları (session, VIEWSTATE, Cloudflare, delta)
   - ETL hataları (validation, transformation, load)
   - Notification hataları (SMTP, queue)

5. Özet sun:

```
## Log Raporu [tarih]

ERROR   : [N adet]
  - [mesaj] (logs/app.log:satır)

WARNING : [N adet]
  - ...

ETL Çalışmaları:
  ✓ [run_id] — [süre]s
  ✗ [run_id] — [hata özeti]

Portal Durumu:
  iSolar : [✓ / ✗ — son hata]
  GAOSB  : [✓ / ✗ — son hata]

Dikkat gerektiren: [varsa açıkla]
```

6. ERROR varsa: `/error-fix` komutuyla ilgili log satırını incele önerisini sun.
