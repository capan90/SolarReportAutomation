# /daily

Günlük durum raporu — sabah session'ında çalıştır.

## Adımlar

1. `/start` komutunu çalıştır (bağlam + health check).
2. `/log-check` çalıştır (dünün logları).
3. `/db-check` çalıştır (son üretim ve mahsup verileri).
4. GitHub MCP ile open PR ve issue'ları listele.
5. Açık sprint planı varsa `docs/sprints/` içinde bul — tamamlanmamış kriterleri listele.
6. Tek özet sun:

```
## Günlük Durum — [Tarih]

### Sistem
Sağlık     : ✓ / ✗
Son ETL    : [tarih, durum]
Son commit : [mesaj]

### Veri
Son üretim : [tarih, miktar kWh]
Son mahsup : [tarih]
DB anomali : Yok / [açıkla]

### Loglar
ERROR      : [N] — [varsa özet]
WARNING    : [N]

### GitHub
Açık PR    : [N] — [başlıklar]
Açık issue : [N] — [başlıklar]

### Sprint
Açık plan  : [PLAN-S17 — tamamlanmamış kriterler]

### Bugün ne yapılacak?
```

Son satırdan sonra kullanıcının cevabını bekle.
