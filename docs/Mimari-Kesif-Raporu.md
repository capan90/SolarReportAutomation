# iSolarCloud × GAOSB — Mimari Keşif ve Adapter Analiz Raporu

**Tarih:** 06 Temmuz 2026  
**Kapsam:** Discovery ve mimari analiz — kod yazılmamıştır  
**Yöntem:** Canlı portal network trafiği incelemesi + ekran görüntüsü analizi

---

## 1. Portal Özetleri

### 1.1 iSolarCloud (web3.isolarcloud.eu)

Sungrow tarafından işletilen küresel GES izleme platformunun Avrupa sunucusudur. Vue.js tabanlı SPA mimarisi kullanır, `#/login` hash-routing ile yönlendirme yapar. Hiçbir zaman resmi public API yayınlanmamış; tüm API bilgisi topluluk tersine mühendisliğiyle elde edilmiştir.

- **Müşteri:** ERDEMSOFT (en az 8 santral: GES-2 ... GES-8)
- **Cihaz:** SG350HX (Sungrow 350kW HV string inverter), 10 adet/santral
- **Durum:** Tüm inverterlar "Normal"
- **API gateway:** `https://gateway.isolarcloud.eu/v1/`

### 1.2 GAOSB (elk.gaosb.org)

**Kritik not:** Domain adı yanıltıcıdır — ELK/Kibana değil, ASP.NET WebForms uygulamasıdır.

Gebze Organize Sanayi Bölgesi'nin sayaç otomasyon sistemine ait internet portalıdır. DevExpress v12.2.8 grid bileşenleri kullanan klasik web uygulamasıdır.

- **Teknoloji:** ASP.NET WebForms (.aspx) + DevExpress Web Controls v12.2.8
- **Sayaç tipi:** OBIS P.01.1.9 — Aktif enerji çekiş (LoadProfile)
- **Çarpan:** 26.400 (trafo/CT oranı — sabit)
- **Granülarite:** 15 dk (LoadProfile periyodu), saatlik görünüm seçilebiliyor

---

## 2. Teknik Bulgular

### 2.1 Authentication

| Başlık | iSolarCloud | GAOSB |
|---|---|---|
| Yöntem | email + password + appKey + RSA+AES şifreleme | Form login → ASP.NET_SessionId cookie |
| Session yönetimi | Per-request token (her istekte yeni RSA key çifti) | Server-side session cookie |
| Şifreleme | AES-CBC hex payload + RSA-1024 header şifreleme | Sadece HTTPS — payload açık |
| CAPTCHA | Login'de yok | Cloudflare bot koruması portal girişinde |
| MFA | Tespit edilmedi | Tespit edilmedi |
| Timeout | Token expiry alanı mevcut (JSON'da `token_expiry`) | IIS session timeout (~20 dk varsayılan) |
| CSRF koruması | `x-sign-code` header | `__EVENTVALIDATION` token |
| appKey riski | Sungrow periyodik rotate eder — **yüksek risk** | Yok |

**iSolarCloud şifreleme akışı (adapter için kritik):**

Her API isteğinde şu üç şey yapılmalıdır:
1. Rastgele bir AES session key üretilir
2. Gerçek JSON payload bu AES key ile `AES-CBC` → hex string'e şifrelenir
3. Üç header RSA-1024 ile şifrelenerek eklenir:
   - `x-random-secret-key`: AES session key'in RSA şifreli hali
   - `x-limit-obj`: userId'nin RSA şifreli hali
   - `x-access-key`: `0uyf06aujq9x8ses5ywfhp94b8yu9b24` (Temmuz 2026 aktif değeri)

Doğrulanmış başlık sabitler:
```
_vc: 2026052801          (versiyon kodu, build tarihi)
_did: 19f122d4f8df50-... (cihaz ID, sabit)
_global_new_web: 1
_pl: js
sys_code: 200
content-type: text/plain;charset=UTF-8
```

### 2.2 Navigasyon ve Sayfa Yapısı

| Başlık | iSolarCloud | GAOSB |
|---|---|---|
| Mimari | Vue.js SPA, hash router | ASP.NET WebForms, klasik web |
| Sayfa geçişi | JavaScript, yenileme yok | Full PostBack — sayfa yenilenir |
| URL yapısı | `#/dashboard`, `#/plant/{id}` | `MeterQuery.aspx`, `MainPage.aspx` |
| SPA mı? | Evet | Hayır |

**iSolarCloud menü yapısı:** Plant → Device → Maintenance (Curve, Remote, Live data, Fault) → Report → System → Support

**GAOSB menü yapısı (butonlar):**
- `Ana sayfa` → genel dashboard
- `Sayaç özet` → özet tablo
- `Endeks grafiği` → grafik görünümü
- `Sayaç sorgu` → MeterQuery.aspx (ana veri sorgulama sayfası)
- `Tüketim grafiği` → tüketim grafikleri
- `Şifre değiştir` / `Çıkış`

### 2.3 API ve Veri Erişim Katmanı

#### iSolarCloud — Doğrulanan Endpoint Envanteri

| # | Servis | Endpoint | Açıklama |
|---|---|---|---|
| 1 | `reportService` | `v2/getCusReportData` | **Ana rapor verisi** — tarih/santral bazlı veri çekimi |
| 2 | `reportService` | `v2/getSelfReportList` | Kayıtlı rapor şablonları listesi |
| 3 | `reportService` | `v2/getExportingTaskList` | Export task polling (async export) |
| 4 | `powerStationService` | `getPsListNova` | Santral listesi (v2 "Nova" API) |
| 5 | `powerStationService` | `getCustomColumnList` | Tablo kolon konfigürasyonu |
| 6 | `devService` | `getPsTree` | Santral cihaz ağacı (PS Tree) |
| 7 | `devService` | `getDeviceModelInfoListByUserOrPs` | Cihaz model listesi |
| 8 | `devService` | `getStationComparePoints` | Santral karşılaştırma ölçüm noktaları |
| 9 | `devService` | `getUserDeviceInfoWithPsFilter` | Kullanıcı + PS filtreli cihaz bilgisi |
| 10 | `userService` | `getCustomMenuSetting` | Kullanıcı menü konfigürasyonu |

**Henüz yakalanmayan (literatürden bilinen) kritik endpoint'ler:**
- `AppService/queryMutiPointDataList` — çok noktalı zaman serisi (5/60/120 dk)
- `AppService/getPowerStatistics` — güç istatistikleri
- `AppService/login` — authentication

#### GAOSB — Doğrulanan Parametreler

```
Yöntem:   POST https://elk.gaosb.org/MeterQuery.aspx
Auth:     Cookie: ASP.NET_SessionId=<session>
OBIS:     P.01.1.9 — Aktif enerji çekiş LoadProfile
Tarih:    Date1_Raw / Date2_Raw (Unix millisecond cinsinden)
          Örnek: 1782864000000 → 01.07.2026 00:00
Display:  Date1 = "1.07.2026 00:00" (DD.MM.YYYY HH:MM)
Sayaç:    cIndexer dropdown (VI=39 → P.01.1.9)
Export:   ButtonExportExcel → senkron POST download
VIEWSTATE: Her sayfada sunucudan alınması gerekiyor (değişken, büyük)
```

**Grid kolonları (DevExpress CallbackState'den decode edildi):**

| Kolon | Açıklama |
|---|---|
| `DATETIME_` | Ölçüm zaman damgası |
| `INDEX_CODE` | OBIS kodu (P.01.1.9) |
| `INDEX_INFO` | Endeks açıklaması |
| `RAW_VALUE` | Ham sayaç okuması (ondalık, yuvarlanmış gösteriliyor) |
| `MULTIPLIER` | Trafo/CT çarpanı (26.400 — sabit) |
| `FIXED_VALUE` | Hesaplanmış endeks değeri = RAW_VALUE_EXACT × MULTIPLIER |

### 2.4 Veri Yapısı Analizi

#### iSolarCloud — Cihaz ve Point Sistemi

Veri, `psId` (santral) + `psKey` (cihaz) + `pointId` (ölçüm noktası) üçlüsüyle adreslenir.

**Doğrulanan cihaz bilgileri:**
- Santral kodu: `ERDEMSOFT-GES-{2..8}`
- Inverter modeli: SG350HX (10 adet/santral)
- Seri no formatı: A2522xxxxxx ve A2531xxxxxx (iki farklı üretim dönemi)

**Literatürden bilinen kritik point ID'leri:**

| Point ID | Açıklama | Tip |
|---|---|---|
| `p83002` | Inverter AC Power | Anlık kW |
| `p83004` | Inverter Total Yield | Kümülatif kWh |
| `p83006` | Meter Daily Yield | Günlük kWh |
| `p83011` | Meter E-daily Consumption | Günlük tüketim kWh |

**Cihaz tipleri (device_type):**

| Değer | Tip |
|---|---|
| 1 | Inverter |
| 7 | Meter (sayaç) |
| 11 | Plant (santral agregat) |
| 14 | Energy Storage System |
| 43 | Battery |

#### GAOSB — Gerçek Veri Örneği (01.07.2026)

| Saat | Okunan Değer | Çarpan | Endeks Değeri |
|---|---|---|---|
| 00:00 | 0,59 (≈0.5890) | 26.400 | 15.549,60 kWh |
| 06:00 | 0,58 (≈0.5800) | 26.400 | 15.312,00 kWh |
| 08:00 | 0,51 (≈0.5120) | 26.400 | 13.516,80 kWh |
| 12:00 | 0,38 (≈0.3800) | 26.400 | 10.032,00 kWh |
| 13:00 | 0,38 (≈0.3794) | 26.400 | 9.979,20 kWh |
| 17:00 | 0,47 (≈0.4679) | 26.400 | 12.355,20 kWh |

**Önemli gözlem:** Endeks değerleri gündüz azalıyor (15.549 → 9.979), akşam artıyor. Bu, GES üretiminin OSB çekişini karşıladığı saat dilimlerini gösteriyor — mahsuplaşma hesabı için doğrudan kullanılabilir.

**Okunan Değer yorumu:** Ekranda 2 ondalıkla yuvarlanmış gösterilmekte, gerçek değer `FIXED_VALUE / MULTIPLIER` formülüyle hesaplanmalıdır.

### 2.5 Saatlik Veri ve Delta Hesabı

| Başlık | iSolarCloud | GAOSB |
|---|---|---|
| Veri tipi | Anlık + kümülatif (seçilebilir point bazlı) | LoadProfile kümülatif endeks (15 dk) |
| Delta gerekiyor mu? | Evet — `p83004` kümülatif | **Evet — FIXED_VALUE kümülatif endeks** |
| Granülarite | 5 dk minimum (60/120 dk seçenekleri) | 15 dk sabit |
| Gece verisi | 0 kWh (üretim yok) | Değer akar (tüketim gece de var) |
| Veri tipi belirsizliği | Düşük | **Orta** — FIXED_VALUE'nun kümülatif mi dönemsel mi olduğu test ortamında doğrulanmalı |

### 2.6 Export Mekanizması

| Başlık | iSolarCloud | GAOSB |
|---|---|---|
| Mekanizma | Async task tabanlı + polling | Senkron PostBack + doğrudan download |
| Polling endpoint | `v2/getExportingTaskList` | Yok |
| Format | JSON → adapter XLSX üretir | Native XLSX (ButtonExportExcel) |
| Tetikleyici | Export butonu → task ID üretir → polling | BtnSubmit / ButtonExportExcel POST |
| Büyük veri riski | Rate limiting | VIEWSTATE boyutu sorun yaratabilir |

### 2.7 Tarih Seçiciler

| Başlık | iSolarCloud | GAOSB |
|---|---|---|
| API formatı | `"YYYYMMDDHHMMSS"` string | Unix millisecond (Raw alanlar) |
| Display formatı | `DD/MM/YYYY` | `DD.MM.YYYY HH:MM` (Türkçe) |
| Aralık parametresi | `startTimeStamp` / `endTimeStamp` | `Date1_Raw` / `Date2_Raw` |
| Saat desteği | Var | Var (00:00 - 23:59) |
| Zaman dilimi | `x-client-tz: GMT+3` header | Sunucu saati Türkiye (implicit) |

---

## 3. Riskler

### iSolarCloud — Yüksek Riskler

**R1 — appKey rotasyonu (Kritik):**  
`x-access-key` değeri Sungrow tarafından önceden bildirimde bulunmadan değiştiriliyor. Kasım 2023'te yaşanan geniş çaplı kesinti bunun kanıtıdır. Şu an aktif değer `0uyf06aujq9x8ses5ywfhp94b8yu9b24` — önceki bilinen değerlerden farklı. Adapter'ın bu değeri harici konfigürasyondan okuması şarttır.

**R2 — Per-request RSA+AES şifreleme (Yüksek):**  
Her API çağrısında `CryptoJS.AES.encrypt` + RSA-1024 çifti üretilmesi gerekiyor. Bu hem implementasyon karmaşıklığı hem de her istekte ~10-50ms ek gecikme demektir. Sunucu tarafı RSA public key'inin de zaman zaman değişebileceği göz önünde bulundurulmalı.

**R3 — Async export polling (Orta):**  
`getExportingTaskList` endpoint'i sürekli polling yapıyor. Adapter'ın task ID takibi ve timeout yönetimi yapması gerekiyor.

**R4 — Rate limiting (Orta):**  
API "Repeated request" hatası döndürüyor. Çoklu santral için paralel sorgu yapılırken throttle mekanizması zorunlu.

**R5 — `queryMutiPointDataList` doğrulanmadı (Düşük-Orta):**  
En kritik zaman serisi endpoint'i canlı trafikte yakalanmadı. Literatürden biliniyor ancak parametre seti test edilmedi.

### GAOSB — Orta Riskler

**R6 — VIEWSTATE bağımlılığı (Yüksek):**  
Her POST isteğinde sunucudan alınan `__VIEWSTATE` ve `__EVENTVALIDATION` token'larının gönderilmesi zorunlu. Bu, adapter'ın önce bir GET isteğiyle sayfa HTML'ini alıp token'ları parse etmesi, sonra POST yapması gerektiği anlamına gelir. İki adımlı HTTP akışı zorunlu.

**R7 — Veri tipi belirsizliği (Orta):**  
`FIXED_VALUE`'nun kümülatif dönemler arası fark mı yoksa her periyodun bağımsız değeri mi olduğu netleştirilmeli. Gerçek delta hesabı buna göre yapılacak.

**R8 — Cloudflare bot koruması (Orta):**  
Programatik erişimde session kurulumu Cloudflare challenge'ı tetikleyebilir.

**R9 — DevExpress grid callback (Düşük):**  
Büyük veri setlerinde grid `CallbackState` ile sayfalama yapıyor. Tüm veriyi almak için sayfalama döngüsü gerekebilir.

**R10 — ASP.NET session süresi (Düşük):**  
IIS varsayılan session timeout 20 dakika. Uzun süren batch işlemlerde session yenileme gerekebilir.

---

## 4. Adapter Notları

### iSolarCloud Adapter

**Zorunlu bileşenler:**

1. **EncryptionService** — `CryptoJS` kullanarak:
   - Rastgele AES key üretimi
   - Payload AES-CBC şifreleme → hex
   - `x-random-secret-key` için AES key'i RSA ile şifreleme
   - `x-limit-obj` için userId'yi RSA ile şifreleme
   - RSA public key'i konfig'den okuma

2. **SessionManager** — token önbellekleme, expiry yönetimi, otomatik yenileme

3. **PlantResolver** — `getPsListNova` → `psId` listesi, `getPsTree` → `psKey` haritası

4. **PointMapper** — pointId → canonical alan adı mapping tablosu

5. **ReportDataFetcher** — `v2/getCusReportData` çağrısı + async export polling

6. **ExportTaskPoller** — `getExportingTaskList` → task tamamlanana kadar polling, timeout yönetimi

### GAOSB Adapter

**Zorunlu bileşenler:**

1. **SessionManager** — Login POST → `ASP.NET_SessionId` cookie yönetimi, yenileme

2. **ViewStateExtractor** — Her POST öncesi GET ile `__VIEWSTATE`, `__EVENTVALIDATION`, `__VIEWSTATEGENERATOR` parse etme

3. **MeterQueryBuilder** — Tarih → Unix ms, OBIS kodu → VI index, tüm form parametrelerini birleştirme

4. **ResponseParser** — DevExpress grid HTML/CallbackState → `EnergyDataPoint[]` dönüşümü

5. **ExcelExporter** — `ButtonExportExcel` ile senkron download tetikleme

6. **DeltaCalculator** — `FIXED_VALUE[t-1] - FIXED_VALUE[t]` ile saatlik tüketim hesabı

---

## 5. Strategy Gereksinimleri

Her iki adapter için ortak `Strategy` interface'i:

```
interface EnergyPortalStrategy {
  authenticate(credentials: Credentials): Promise<Session>
  listPlants(): Promise<Plant[]>
  fetchDailyData(plantId: string, date: LocalDate): Promise<EnergyDataPoint[]>
  fetchHourlyData(plantId: string, date: LocalDate): Promise<EnergyDataPoint[]>
  fetchMeterData(meterId: string, range: DateRange): Promise<MeterReading[]>
  exportToExcel(params: ExportParams): Promise<Buffer>
  logout(): Promise<void>
}
```

**Adapter içinde kalması gerekenler (portal-özel):**

- iSolar: AES+RSA şifreleme, appKey yönetimi, psKey/pointId mapping, export task polling
- GAOSB: VIEWSTATE yönetimi, DevExpress form building, CallbackState parsing, OBIS multiplier uygulaması

---

## 6. Canonical Model Önerileri

### Ortak Alanlar

```typescript
interface EnergyDataPoint {
  plantId: string           // portal-agnostic ID
  plantName: string
  timestamp: string         // ISO 8601
  sourcePortal: "isolar" | "gaosb"
  intervalMinutes: number   // 5, 15, 60, vb.
  generationKwh: number | null
  consumptionKwh: number | null
  gridExportKwh: number | null
  gridImportKwh: number | null
  isCumulative: boolean     // true ise delta hesabı yapılması gerekiyor
}

interface MeterReading {
  meterId: string
  timestamp: string         // ISO 8601
  obisCode: string          // örn. P.01.1.9
  rawValue: number          // ham sayaç değeri
  multiplier: number        // trafo/CT oranı
  fixedValue: number        // rawValue × multiplier
  deltaKwh: number | null   // bir önceki okumaya göre fark
}
```

### Portal-Özel Metadata (canonical'a dahil edilmemeli)

**iSolar:** `psId`, `psKey`, `pointId`, `deviceType`, `deviceCode`  
**GAOSB:** `aspnetSessionId`, `viewStateToken`, `devExpressVI`, `callbackState`

---

## 7. Capability Önerileri

| Capability Flag | iSolarCloud | GAOSB |
|---|---|---|
| `HOURLY_GENERATION` | ✅ Doğrulandı | ❌ Yalnızca çekiş |
| `HOURLY_CONSUMPTION` | ✅ p83011 | ✅ P.01.1.9 |
| `DAILY_METER_INDEX` | ✅ device_type:7 | ✅ Ana işlev |
| `SETTLEMENT_DATA` | ⚠️ Ayrı hesap gerekir | ✅ Direkt mevcut |
| `REAL_TIME_DATA` | ✅ 5 dk granülarite | ❌ Log tabanlı |
| `MULTI_PLANT` | ✅ 8+ santral | ⚠️ Tek sayaç sorgusu |
| `DELTA_COMPUTATION` | Gerekli | Gerekli |
| `ASYNC_EXPORT` | ✅ Task polling | ❌ Senkron |
| `NATIVE_EXCEL_EXPORT` | ❌ JSON → adapter üretir | ✅ Yerleşik |

---

## 8. GAOSB ↔ iSolarCloud Eşleştirme Önerileri

| Canonical Alan | iSolarCloud Kaynak | GAOSB Kaynak |
|---|---|---|
| `generationKwh` | `p83006` (Meter Daily Yield) delta | Yok — üretim verisi mevcut değil |
| `consumptionKwh` | `p83011` (E-daily Consumption) | `FIXED_VALUE` delta (P.01.1.9) |
| `gridExportKwh` | `p83004` (Total Yield) delta | Yok — hesaplama gerekir |
| `gridImportKwh` | Consumption - Generation | `FIXED_VALUE` (doğrudan çekiş) |
| `timestamp` | `"YYYYMMDDHHMMSS"` → ISO 8601 | Unix ms → ISO 8601 |
| `plantId` | `psId` (integer string) | Sayaç kimliği (OBIS + VI index) |
| `meterId` | `psKey` + `device_type: 7` | `cIndexer` değeri |
| `multiplier` | Yok (API normalize edilmiş döndürür) | `MULTIPLIER` kolonundan dinamik okunmalı |
| `intervalMinutes` | 5/60/120 (parametrik) | 15 (sabit, LoadProfile) |

**Temel uyumsuzluk:** iSolar üretim verir, GAOSB tüketim çekişi verir. Mahsuplaşma hesabı için her iki kaynak birleştirilmeli; `timestamp` senkronizasyonu kritik (iSolar 5 dk, GAOSB 15 dk).

---

## 9. Önerilen Adapter Akışı

### iSolarCloud Veri Çekme Akışı

```
1. EncryptionService.init(appKey, rsaPublicKey)
2. SessionManager.login(email, password) → token
3. PlantResolver.listPlants() → psId[]
4. PointMapper.load(psId) → pointId mapping
5. For each santral:
   a. ReportDataFetcher.fetch(psId, startDate, endDate, interval)
      → v2/getCusReportData (AES+RSA şifreli POST)
   b. DeltaCalculator.compute(rawPoints) → EnergyDataPoint[]
6. ExportTaskPoller.poll(taskId, timeout=120s) → download URL
```

### GAOSB Veri Çekme Akışı

```
1. GET /MeterQuery.aspx → __VIEWSTATE, __EVENTVALIDATION parse
2. SessionManager.login(user, pass) → ASP.NET_SessionId
3. ViewStateExtractor.refresh() → güncel token'lar
4. MeterQueryBuilder.build(date, obisCode) → form params
5. POST /MeterQuery.aspx → DevExpress grid HTML
6. ResponseParser.parse(html) → MeterReading[]
7. DeltaCalculator.compute(readings) → EnergyDataPoint[]
8. (Opsiyonel) POST /MeterQuery.aspx?export → XLSX download
```

---

## 10. Açık Sorular ve Sonraki Adımlar

| # | Soru | Öncelik | Yöntem |
|---|---|---|---|
| 1 | `queryMutiPointDataList` parametreleri (interval, pointId listesi) | Yüksek | iSolar canlı test |
| 2 | GAOSB `FIXED_VALUE` kümülatif mi yoksa dönemsel mi? | Yüksek | İki ardışık gün karşılaştırması |
| 3 | GAOSB'de başka OBIS kodları var mı? (Verim, ihracat) | Orta | `cIndexer` dropdown tüm seçenekleri |
| 4 | iSolar RSA public key endpoint'i nerede? | Yüksek | Login akışı analizi |
| 5 | GAOSB `Sayaç özet` sayfası hangi veriyi gösteriyor? | Orta | Ekran görüntüsü |
| 6 | GAOSB multi-sayaç desteği var mı? | Orta | Dropdown seçenekleri |
| 7 | iSolar `p83004` ile `p83006` arasındaki fark nedir? | Orta | Aynı dönem, iki point karşılaştırması |
| 8 | iSolar export task'ı tamamlanma süresi ne kadar? | Düşük | Polling log analizi |

---

*Bu rapor yalnızca keşif ve mimari analiz içermektedir. Hiçbir production kodu, dosya değişikliği veya git işlemi yapılmamıştır.*