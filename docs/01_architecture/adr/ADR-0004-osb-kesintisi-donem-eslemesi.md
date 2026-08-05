# ADR-0004: OSB Kesintisinde Dönem Eşlemesinin Düzeltilmesi

## Durum

ADR-0002 §Durum şu kuralı kayda geçirmişti: *"Değişken katsayı her ay OSB'nin
BİR ÖNCEKİ AYA ait gerçek faturasındaki birim fiyattır."* Uygulama bunu
`monthly_electricity_price` tablosunda `source M → target M+1` eşlemesiyle
gerçekleştirdi: M ayının faturasından okunan fiyat, M+1 ayının katsayısı oldu.

2026-08-05'te iki gerçek GAOSB faturası bu kuralı sınadı. Her ikisinde de
"EPYS Bedelli Üretim Miktarı" kalemi şunu gösterdi:

| Belge | Faturadaki kWh | Sistemdeki karşılığı | Fark | Fiyat |
|---|---|---|---|---|
| Haziran 2026 | 2.334.046,2750 | kWh(**Mayıs**) 2.335.232,7 | %0,05 | 0,810049 |
| Temmuz 2026  | 3.570.216,493  | kWh(**Haziran**) 3.554.333,1 | %0,45 | 1,452381 |

Yani bir fatura İKİ DÖNEMİ birlikte taşıyor: Aktif Enerji kalemi cari ayın
tüketimi, EPYS kalemi ise BİR ÖNCEKİ ayın üretimidir. Kesinti kaleminde miktar
ve fiyat aynı döneme aittir; sistem ise miktarı cari aydan, fiyatı bir önceki
aydan alıyordu.

Hata büyüklüğü: `hata(M) = kWh(M) × (E(M−1) − E(M))`. Nisan ve Mayıs fiyatları
eşit olduğu için (0,810049) hata aylarca tam SIFIR kaldı ve görünmedi; ancak
fiyat sıçrayınca (0,810049 → 1,452381) Haziran'da 2.283.061,89 TL'ye ulaştı.

2026-08-03'te Haziran'ın katsayısı override ile 1,452381 → 0,810049 yapılmıştı.
Bu override ADR-0002'nin kuralını doğru uyguluyordu; ancak kuralın kendisi
yanlış olduğu için kayıtlı tutarı gerçekten UZAKLAŞTIRDI. Override öncesindeki
değer (elle girilmiş olan 1,452381) faturayla %0,45 farkla eşleşiyordu.

Ayrıca kütükteki `source` alanının ne anlama geldiği doğrulandı: kullanıcı
"Haziran faturası" olarak kaydettiği 1,452381 değerini, üzerinde "Temmuz"
yazan belgeden okumuştu — çünkü o belgedeki EPYS kalemi Haziran'ın üretimini
değerliyor. `source` alanı, belgenin kendi etiketini değil, **değerlediği üretim
dönemini** taşıyor ve bu hâliyle DOĞRU.

## Karar

1. **Kaydırma kaldırılır.** Bir ayın OSB katsayısı, O AYIN üretimini
   değerleyen fiyattır: `osb_unit_price_try[M] = E(M)`. `monthly_electricity_price`
   eşlemesi `source M → target M` olur; `next_month()` katsayı hedeflemesinde
   KULLANILMAZ.

2. **Bir ay geriden gelen tek şey TAHSİLAT ZAMANIDIR.** M ayının kesintisi,
   M+1 etiketli faturada düşülür. Bu bir GÖSTERİM bilgisidir; hesaba girmez.
   `next_month()` yalnızca bu etiket için kullanılmaya devam eder.

3. **`compute()` ve mahsuplaşma motoru DEĞİŞMEZ.** `osb_deduction_try[M] =
   kWh(M) × osb_unit_price_try[M]` formülü doğrudur; yanlış olan
   `osb_unit_price_try[M]`'e hangi değerin yazıldığıydı. Düzeltme yalnızca
   kütüğün hedef eşlemesinde ve bir kerelik veri düzeltmesindedir.

4. **`source` alanının anlamı netleştirilir: ÜRETİM DÖNEMİ.** Kullanıcı
   "Haziran faturası" derken elindeki belge "Temmuz" etiketli olabilir; kastettiği,
   EPYS kalemindeki kWh'in ait olduğu üretim dönemidir. Arayüz "Fatura Ayı"
   yerine "Üretim Dönemi" der ve hangi belgeden okunacağını yazar.

5. **Kütükteki mevcut DEĞERLER doğrudur, yeniden okunmaz.** `source` alanı
   zaten üretim dönemini taşıdığı için düzeltme mekaniktir: `target := source`.

6. **Katsayısı henüz bilinmeyen ay PENDING_RATE'te bırakılır.** M ayının
   katsayısı M+1 etiketli fatura elde olana kadar bilinemez. O ana kadar
   `osb_unit_price_try` NULL ve tutar "Bekleniyor"dur — tahmini bir değerle
   doldurulmaz (ADR-0002 §6 ile aynı ilke).

7. **Kilitli ayların düzeltmesi denetlenir.** Mevcut tek kilit delme yolu
   (`BillingRepository.override_locked_month`) kullanılır; ikinci bir bypass
   açılmaz. Katsayıyı NULL'a çekmek için gereken dar kapsamlı yol YALNIZCA
   migration script'i tarafından çağrılır ve arayüze BAĞLANMAZ. Her değişen ay
   `audit_log`'a `billing_period_remap` eylemiyle eski→yeni değerleriyle yazılır.
   Önce dry-run, sonra yedek, sonra uygulama.

8. **Ölçüm farkı tolere edilir, gizlenmez.** Faturadaki EPYS kWh ile sistemin
   kWh'i %0,05–0,45 arasında farklıdır (OSB'nin EPYS'e kayıtlı miktarı ile
   santral tarafı ölçümü aynı sınırdan okunmaz). Sistem KENDİ ölçümünü kullanmaya
   devam eder; fatura teyidi kullanıcının işidir.

## Gerekçe

- İki bağımsız fatura, iki farklı fiyat seviyesinde aynı kuralı gösteriyor.
- Kaydırmanın kaldırılması modeli SADELEŞTİRİR: kesinti, üretimi yapan aya ait
  kalır. Aylık raporun tamamı zaten "M ayının kWh'i ve M ayının TL'si" üzerine
  kurulu; alternatif model bu bütünlüğü bozardı.
- `compute()`'a dokunulmaması, sistemin en riskli ve en çok test edilmiş kodunu
  değişiklik dışında bırakır.
- Hatanın aylarca görünmemesinin sebebi (sabit fiyat) kayda geçer; benzer
  "iki hata birbirini götürüyor" durumlarında tolerans değil ölçüm istenir.
- 2026-08-05'te eklenen "Önizleme — ayın kendi fiyatıyla" satırı (`kWh(M) × E(M)`),
  farkında olmadan bu ADR'nin doğru formülünü hesaplıyordu ve Temmuz faturasını
  %0,45 hatayla önceden bildi. Düzeltmeden sonra "Resmi" ile aynı sayı olur.

## Alternatifler

- **`compute()` kWh'i M−1'den alsın** — sayısal sonuç aynı, ama
  `osb_deduction_try[M]` artık M ayının üretimiyle ilgisiz bir sayı olurdu;
  aylık raporda M'nin kWh'i ile başka bir ayın TL'si yan yana dururdu. Ayrıca
  en riskli kod değişmiş olurdu. REDDEDİLDİ.
- **ADR-0002'yi yerinde düzeltmek** — yanlış modelin neden benimsendiği ve neyin
  çürüttüğü bilginin kendisi; 2026-08-03 override'ı ancak iki belge yan yana
  okununca anlaşılıyor. ADR'ler append-only karar günlüğüdür. REDDEDİLDİ.
- **Geçmişi olduğu gibi bırakıp yalnızca bundan sonrasını düzeltmek** — Haziran
  2,28 milyon TL yanlış kayıtlı kalırdı; faturayla karşılaştırma yapan kullanıcı
  her ay aynı farkla karşılaşırdı. REDDEDİLDİ.
- **Faturadaki kWh'i sisteme yazmak (ölçümü OSB'den almak)** — ETL'in ölçüm
  otoritesini dışarı taşırdı (ADR-0003'ün tam tersi yön). REDDEDİLDİ.
- **Temmuz'a tahmini bir katsayı yazmak** — "hesaplanmadı" ile "sıfır/tahmin"
  arasındaki ayrım ADR-0002 §6'nın temel ilkesi. REDDEDİLDİ.

## Sonuç

ADR-0002'nin §Durum'daki "bir önceki ayın faturasındaki birim fiyat" ifadesi ve
§Karar 3'ün buna dayanan eşlemesi bu ADR ile GEÇERSİZ KILINIR. ADR-0002'nin
diğer kararları (ayrı katman, append-only tarife, snapshot kilidi, Numeric para
tipi, "katsayı eksikse rapor beklemez") yürürlüktedir.

Yeni akış:

```
OSB faturası (M+1 etiketli belge) elde
   → EPYS satırındaki birim fiyat girilir, ÜRETİM DÖNEMİ = M
   → monthly_billing[M].osb_unit_price_try = E(M)  [LOCKED]
   → osb_deduction_try[M] = kWh(M) × E(M)
   → Excel: "Bu tutar M+1 faturasından düşülür" (yalnızca etiket)
```

Etkilenen kilitli aylar ve düzeltme yönü (dry-run ile kesinleşir):

| Ay | Katsayı | Kesinti | İşlem |
|---|---|---|---|
| Mayıs 2026 | 0,810049 → 0,810049 | ≈1.891.653 → aynı | dokunulmaz (fiyat sabitti) |
| Haziran 2026 | 0,810049 → 1,452381 | 2.879.183,97 → 5.162.245,86 | override yolundan yaz |
| Temmuz 2026 | 1,452381 → (bilinmiyor) | 5.311.711,99 → Bekleniyor | PENDING_RATE'e döndür |

Takip işleri:
- Commit 1'deki "Resmi / Önizleme" iki görünümü tek satıra iner — düzeltmeden
  sonra ikisi aynı sayıdır.
- Arayüzdeki "Fatura Ayı → N+1 katsayısı olur" yönlendirmesi güncellenir.
- Düzeltilmiş Haziran rakamı, o ay gönderilmiş e-postadakinden farklıdır;
  alıcılara bilgi verilmesi kullanıcının kararıdır.

**Kapsam dışı:** Nisan öncesi aylar için geriye dönük doldurma; faturadaki
diğer kalemlerin (dağıtım, YEKDEM, iletim, reaktif, belediye vergisi) sisteme
alınması; OSB'nin EPYS miktarı ile sistemin kWh'i arasındaki %0,05–0,45 farkın
kaynağının araştırılması.
