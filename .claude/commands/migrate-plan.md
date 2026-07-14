# /migrate-plan

Veritabanı şema değişikliği planla — kod yazmadan önce onay al.

## Kullanım

```
/migrate-plan "settlement tablosuna grid_export_kwh kolonu ekle"
```

## Adımlar

1. SQLite MCP ile mevcut schema'yı oku:
```sql
SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;
```

2. İstenen değişikliği analiz et:
   - Ne ekleniyor / değiştiriliyor / kaldırılıyor?
   - Hangi tablolar etkileniyor?
   - Mevcut veri zarar görür mü?

3. Canonical Layer kontrolü:
   - `app/core/` veya `app/domain/` altındaki model dosyalarını oku.
   - Schema değişikliği Canonical modelle uyumlu mu?
   - Değilse — dur, kullanıcıya bildir.

4. Migration planını hazırla:

```
## Migration Planı

Değişiklik   : [ne yapılıyor]
Etkilenen    : [tablo listesi]
Veri riski   : [var / yok — açıkla]
Canonical uyum: [✓ / ✗]
Geri alınabilir: [evet / hayır]

SQL:
  -- Güvenli değişiklik (ALTER TABLE / CREATE TABLE / ...)
  ALTER TABLE settlement ADD COLUMN grid_export_kwh REAL;

  -- Geri alma (rollback)
  -- SQLite'ta kolonu silmek için tablo yeniden oluşturulmalı

Etkilenecek kod dosyaları:
  - app/...

Test:
  - python main.py --health
  - Mevcut kayıtlar bozulmadı mı?

Onaylıyor musunuz?
```

5. **Onay gelmeden migration çalıştırılmaz.**
6. Onay gelince SQL çalıştır, ardından health check yap.

**VERİTABANI DEĞİŞİKLİĞİ KULLANICI ONAYI OLMADAN YAPILMAZ.**
