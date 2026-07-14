# /db-check

Veritabanı durumunu kontrol et — schema, son kayıtlar, anomaliler.

## Kullanım

```
/db-check
/db-check settlement      ← belirli tablo
/db-check date 2026-07-01 ← belirli tarih
```

## Adımlar

1. SQLite MCP ile bağlan.
2. Parametre yoksa genel sağlık kontrolü yap:

```sql
-- Tablo listesi
SELECT name FROM sqlite_master WHERE type='table';

-- Her tablonun son kaydı ve satır sayısı
SELECT 'daily_generation' AS tbl, COUNT(*) AS rows,
       MAX(date) AS last_date FROM daily_generation;
-- (diğer tablolar için tekrar et)

-- Son ETL çalışması
SELECT run_id, status, started_at, duration_seconds
FROM etl_run ORDER BY started_at DESC LIMIT 5;

-- Son notification
SELECT event_type, status, sent_at
FROM notification_history ORDER BY sent_at DESC LIMIT 5;
```

3. Parametre `settlement` ise:
```sql
SELECT date, plant_id,
       production_kwh, consumption_kwh,
       settlement_kwh
FROM settlement
ORDER BY date DESC LIMIT 10;
```

4. Parametre `date YYYY-MM-DD` ise o tarihe ait tüm tablolardaki kayıtları göster.

5. Anomali kontrolü:
   - Sıfır üretim ama gündüz saati var mı?
   - Delta negatif kayıt var mı?
   - etl_run.status = 'failed' son 7 günde var mı?

6. Kullanıcıya özet sun:

```
## DB Sağlık Raporu [tarih]

Tablolar      : [liste + satır sayıları]
Son üretim    : [tarih, miktar]
Son mahsup    : [tarih]
ETL durumu    : [son 5 run — ✓/✗]
Anomali       : [varsa açıkla / yoksa "Yok"]
```
