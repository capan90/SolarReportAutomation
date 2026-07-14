# CLAUDE.md — SolarReportAutomation

## Komutlar

```bash
# Sağlık kontrolü (her session başında çalıştır)
python main.py --health

# Smoke test
pytest tests/smoke/ -x -q

# Lint
ruff check . && ruff format --check .
```

## Proje Bağlamı

Proje adı     : SolarReportAutomation
Dil / Runtime : Python 3.12
Veritabanı    : SQLite (solar_report_db.sqlite) → PostgreSQL'e migrate planlandı
Ana giriş     : main.py
Release       : 1.0.0-GA (2026-06-30 — CHANGELOG.md'deki güncel kayıt)
Mimari ref    : ARCHITECTURE.md
Roadmap ref   : ROADMAP.md
Changelog ref : CHANGELOG.md

## Katmanlar (dokunma sırası)

```
iSolar Adapter  →  GAOSB Adapter
        ↓                ↓
      Canonical Layer (DEĞİŞTİRME)
            ↓
      Settlement Engine
            ↓
      Analytics Engine
            ↓
   Dashboard (read-only) / PDF / REST API
```

## Değişmez Kurallar

- Canonical Layer (EnergyDataPoint, MeterReading, PlantRecord) izinsiz değiştirilmez.
- Mevcut çalışan ETL pipeline bozulmaz — 1.0.0-GA stabil kalır.
- Dashboard hiçbir zaman ETL tetiklemez, DB'ye yazmaz.
- Sessiz hata kabul edilmez — her kritik adım loglanır.
- Secret / credential loglara ve Git'e girmez (.env zorunlu).
- Yeni teknoloji = önce ADR (docs/adr/).
- Discovery scriptleri production koduna karışmaz (scratch/ klasöründe kalır).

## Portal Özeti (Adapter yazarken oku)

iSolarCloud:
- Auth: email + password + appKey + AES-CBC + RSA-1024 (x-random-secret-key, x-limit-obj, x-access-key)
- x-access-key değeri config'den okunmalı (Sungrow rotate eder — kritik risk)
- Ana endpoint: gateway.isolarcloud.eu/v1/reportService/v2/getCusReportData
- Saatlik veri kümülatif gelir → delta hesabı şart (p83004, p83006)
- Export async: getExportingTaskList polling gerekir

GAOSB:
- Auth: ASP.NET form login → ASP.NET_SessionId cookie
- Her POST öncesi GET ile __VIEWSTATE + __EVENTVALIDATION parse edilmeli
- OBIS: P.01.1.9, Çarpan: 26.400 (sabit)
- FIXED_VALUE kümülatif → delta hesabı şart
- Tarih: Unix millisecond (Date1_Raw / Date2_Raw)

## Geliştirme Akışı

Plan session  → /sprint-plan → docs/sprints/PLAN-[NO].md → sen onaylar → /clear
Execute session → plan dosyasını oku → uygula → hook çalışır
Error session  → /error-fix [hata çıktısı] → teşhis → sen onaylar → düzeltme
Commit        → /commit → sen onaylar → push

## Dosya Sınırları

- Tek task: maksimum 10 dosya, ~300 satır
- Git işlemi kullanıcı onayı olmadan yapılmaz
- Her commit CHANGELOG.md günceller

## Referans Dosyalar

- Mimari kararlar  : docs/adr/
- Sprint geçmişi   : docs/sprints/
- Prompt şablonları: docs/prompts/
- Adapter analizi  : docs/ (Mimari-Keşif-Raporu)
