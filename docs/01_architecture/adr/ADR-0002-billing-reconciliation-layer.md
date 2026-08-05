# ADR-0002: Faturalama Hesaplarının Ayrı Bir Billing Katmanında Tutulması

## Durum

> **⚠️ KISMEN GEÇERSİZ — bkz. [ADR-0004](ADR-0004-osb-kesintisi-donem-eslemesi.md) (2026-08-05).**
> Aşağıdaki "değişken katsayı her ay OSB'nin **bir önceki aya** ait gerçek
> faturasındaki birim fiyattır" ifadesi ve §Karar 3'ün buna dayanan
> `source M → target M+1` eşlemesi, iki gerçek fatura ile çürütülmüştür.
> Doğrusu: bir ayın katsayısı **o ayın kendi üretimini değerleyen** fiyattır;
> bir ay geriden gelen tek şey tahsilat zamanıdır. Bu belgenin diğer kararları
> (ayrı katman, append-only tarife, snapshot kilidi, para tipi, "katsayı eksikse
> rapor beklemez") yürürlüktedir.

Aylık mahsuplaşma raporuna iki finansal hesap eklenecektir:

1. **Fazla Satış Faturası** (Enerjisa'ya kesilecek)
   = Aylık Toplam Fazla Satış (kWh) × sabit birim fiyat (TL/kWh)
2. **OSB Kesintisi** (tüketimden düşülecek)
   = (Aylık Toplam Üretim − Aylık Toplam Fazla Satış) × değişken birim fiyat (TL/kWh)

Her iki birim fiyat da **KDV HARİÇ (net)** TL/kWh olarak tanımlıdır. KDV hesabı,
KDV'li tutar üretimi ve fatura belgesi oluşturma bu kararın kapsamı dışındadır.

Sabit katsayı (~2,909687 TL/kWh) dashboard'dan yönetici şifresiyle
değiştirilebilmeli, ancak değişiklik geçmiş aylara etki etmemelidir. Değişken
katsayı her ay OSB'nin bir önceki aya ait gerçek faturasındaki birim fiyattır;
elle girilir ve girildikten sonra o ay için kilitlenir.

Mevcut mimaride Settlement Engine saf bir hesap katmanıdır (iki Excel dosyası →
saatlik kWh nesneleri; DB erişimi ve para kavramı yoktur). Konfigürasyon .env
dosyasında tutulur ve frozen bir Settings nesnesine yalnızca process başlangıcında
yüklenir — değişiklik restart gerektirir. Dashboard bugüne kadar ölçüm verisi
açısından salt-okunur olarak tasarlanmıştır.

## Karar

1. **Ayrı katman.** Faturalama hesapları Settlement Engine'e eklenmez; `app/billing/`
   altında ayrı bir Billing Service olarak konumlandırılır. Katman sırası:
   `Settlement Engine → Billing Service → Analytics / Dashboard / Excel / Chatbot`.

2. **Sabit katsayı DB'de, append-only.** .env'de değil `billing_rate` tablosunda
   tutulur (`rate_type`, `unit_price_try`, `valid_from`, `created_by`, `note`).
   Değişiklik UPDATE değil INSERT'tür. `valid_from` ayın ilk günü olmak zorundadır.

3. **Aya kilitlenen snapshot.** Her ay için `monthly_billing` tablosunda tek satır
   tutulur. Satır ilk oluşturulduğunda o ay için geçerli sabit katsayı
   (`valid_from <= ay sonu` olan en güncel kayıt) snapshot olarak yazılır ve bir daha
   değişmez. Değişken katsayı elle girildiğinde satır `LOCKED` durumuna geçer.

   > Bu maddenin **eşleme** kısmı (hangi ayın faturasının hangi aya besleneceği)
   > ADR-0004 ile değiştirilmiştir; snapshot ve kilit kuralları geçerlidir.

4. **Kilitlenen katsayıdır, tutar değildir.** kWh verisi sonradan tamamlanır veya
   yeniden hesaplanırsa tutarlar kilitli katsayılarla yeniden türetilir. Katsayı
   alanlarına `LOCKED` satırda yapılan UPDATE denemesi repository katmanında
   reddedilir ve loglanır.

5. **Dashboard referans verisine yazabilir.** Dashboard, katsayı verisine yönetici
   şifresi doğrulamasıyla ve `audit_log` kaydıyla YAZABİLİR. "Dashboard DB'ye yazmaz"
   kuralı şu şekilde keskinleştirilir: *Dashboard ölçüm/ETL verisine yazmaz;
   referans verisine (billing_rate, monthly_billing gibi) denetlenebilir şekilde
   yazabilir.* CLAUDE.md bu karara göre güncellenir.

6. **Katsayı eksikse rapor beklemez.** Değişken katsayı girilmemişse aylık rapor
   yine üretilir; satır `PENDING_RATE` durumunda açılır, ilgili TL alanları
   "Bekleniyor" olarak gösterilir ve dashboard'da uyarı kartı çıkar. Rapor üretimi
   hiçbir koşulda katsayı girişini beklemez.

7. **Tutarsız veride hesap yapılmaz.** `(üretim − fazla satış)` negatif çıkarsa
   (yalnızca eksik/bozuk veride mümkündür) değer sessizce sıfıra kırpılmaz; hata
   loglanır ve ay `PENDING_RATE` durumunda bırakılır.

8. **Para tipi.** Parasal alanlar `Numeric`'tir; `Float` kullanılmaz. Birim fiyatlar
   `Numeric(18,6)`, tutarlar `Numeric(18,2)`. Yuvarlama servis katmanında
   `Decimal` + `ROUND_HALF_UP` ile 2 haneye yapılır. Para birimi TL sabittir;
   ayrı bir `currency` kolonu eklenmez (YAGNI).

## Gerekçe

- Settlement Engine'in saflığı korunur: DB bağımlılığı almaz, mevcut dosya tabanlı
  testleri değişmeden çalışır.
- Mahsuplaşma kuralı hiç değişmez, tarife her ay değişir; farklı değişim hızındaki
  iki sorumluluk ayrı sınıflarda tutulur.
- Append-only katsayı geçmişi "kim, ne zaman, hangi değeri girdi" sorusunu
  denetlenebilir kılar — fatura kesilen bir parametre için zorunludur.
- `valid_from` alanı, dashboard'daki geçmiş ay yeniden hesaplama özelliğinin
  (`/api/settlement/trigger/monthly-date`) eski aylara güncel (yanlış) katsayı
  uygulamasını önler. Yalnızca `created_at`'e bakan bir "en son değer" mantığı bu
  senaryoda sessizce hatalı fatura üretirdi.
- Aya kilitlenen snapshot, "katsayı değişse de geçmiş aylar etkilenmesin" iş
  kuralını veri modelinin kendisinde garanti eder; uygulama koduna güvenmez.
- .env yerine DB seçimi katsayı değişikliğinde dashboard restart'ı gereksiz kılar
  ve değeri veritabanı yedeklerine dahil eder.
- Katsayı beklerken raporu bloklamamak, otomatik koşuda kullanıcı bulunmadığı ve
  OSB faturasının ay kapandıktan sonra geldiği gerçeğinden doğar.

## Alternatifler

- **Katsayıları .env'de tutmak** — restart gerektirir, geçmişi yoktur, yedeklenmez,
  aya kilitlenme sağlamaz.
- **Genel amaçlı `app_setting(key, value)` tablosu** — geçmiş ve aya kilitlenme
  sağlamaz; snapshot tablosu yine gerekirdi.
- **TL hesabını Settlement Engine içine almak** — saflığı ve test edilebilirliği bozar.
- **TL hesabını Analytics Engine'e almak** — Analytics türetilmiş salt-okunur
  istatistik üretir; faturalama kalıcı ve kilitlenen resmî kayıt üretir.
- **Değişken katsayı girilene kadar aylık raporu üretmemek** — kWh raporunun da
  kaybolmasına yol açar.
- **Tutarları da dondurmak** — kWh verisi sonradan tamamlandığında fatura tutarı
  gerçekle uyumsuz kalırdı.

## Sonuç

Aylık akış şu hâle gelir:

```
iSolar + GAOSB indirme
   → Settlement Engine (kWh)
   → settlement_hourly / daily / monthly
   → Billing Service (sabit katsayı snapshot + fazla satış faturası)
   → monthly_billing [PENDING_RATE]
   → Excel + e-posta (TL alanları "Bekleniyor")
   → kullanıcı dashboard'dan OSB birim fiyatını girer
   → [LOCKED] → tutarlar hesaplanır → rapor istenirse yeniden üretilir
```

Uygulama dosya sınırı (CLAUDE.md: tek task ≤ 10 dosya) gereği üç sprint'e bölünür:
**A)** veri modeli + servis + repository + job entegrasyonu + test,
**B)** dashboard akışı, **C)** Excel + e-posta + chatbot.

**Kapsam dışı** (ROADMAP.md teknik borç listesine taşınır):
- KDV hesabı ve KDV'li tutar üretimi — katsayılar net (KDV hariç) kabul edilir
- Kilitli ayın katsayısını düzeltmek için override akışı
- Rol bazlı yetkilendirme (şu an tek bir `DASHBOARD_ADMIN_PASSWORD`)
- Sistem devreye girmeden önceki aylar için geriye dönük doldurma (backfill)
