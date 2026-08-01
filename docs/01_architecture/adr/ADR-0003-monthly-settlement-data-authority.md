# ADR-0003: Aylık Mahsuplaşma Verisinde Otorite — Günlük ETL mi, Aylık Yeniden Çekim mi?

## Durum

Bugün bir ayın saatlik mahsuplaşma verisi **iki bağımsız yoldan** üretiliyor ve
ikisi de aynı tablolara yazıyor:

- **`DailySettlementJob`** her gün 09:00'da koşar, **dünü** işler
  (`daily_settlement_job.py:43`), iSolar + GAOSB'den o güne ait veriyi çeker ve
  `settlement_hourly` + `settlement_daily` tablolarına upsert eder.
- **`MonthlySettlementJob`** her ayın 1'inde 08:30'da koşar, önceki **ayın tamamını**
  portallardan yeniden çeker ve `settlement_hourly` + gün gün `settlement_daily` +
  `settlement_monthly` üzerine upsert eder (`monthly_settlement_job.py:561-575`).

`models.py:140` bu paylaşımı belgeliyor: *"günlük ve aylık job'lar aynı tabloya
upsert eder (date+hour benzersizdir)"*. Sonuç: **ayın 1'inde önceki ayın ~30 günlük
günlük-iş verisi sessizce yeniden yazılıyor** ve iki yolun aynı sayıyı üretip
üretmediği bugüne kadar hiç ölçülmedi — ikincisi birincisini ezdiği için fark
görünmüyor. Bu, "sessiz hata kabul edilmez" ilkesiyle gerilim halinde.

**Bu bir tasarım kararı değil, tarihsel miras.** Aylık iş, DB tablolarıyla **aynı
commit'te** (`cac11f7`, 2026-07-07) günlük işin kopyası olarak doğdu — sınıf
docstring'i: *"DailySettlementJob'un aylık versiyonu"*. O sırada güvenilecek bir
günlük veri geçmişi henüz yoktu, dolayısıyla scraping tek seçenekti; DB baştan
**çıktı (sink)** olarak konumlandı, girdi olarak değil. `_load_gaosb_month`
docstring'i (satır 41) aynı hikâyeyi anlatıyor: `SettlementEngine.load_gaosb()`
günlük akış için tasarlanmıştı ve aylık akış için yeniden yazılmak zorunda kaldı.
Kod tabanında aylık scraping'in günlükteki boşlukları telafi ettiğine dair **hiçbir
yorum, ADR veya test yok** — telafi kazara gerçekleşen bir yan etki.

### Bugünkü davranış bir arıza değil

"Aylık iş 08:30'da koşuyorsa ayın son gününün verisi nereden geliyor? O gün günlük
iş tarafından ancak 09:00'da yazılacak" sorusunun cevabı: **aylık iş DB'yi hiç
okumuyor.** Son gün dahil tüm ayı kendi bağımsız çekimiyle topluyor, günlük işin
09:00 koşusuna bağımlı değil. Yani bugünkü scraping, istenmeden de olsa **fiilen bir
bağımsızlık garantisi** sağlıyor. Bu ayrım, aşağıdaki ön koşulun neden var olduğunu
anlamak için kritiktir.

### Ölçüm verisi (2026-08-01)

| Ortam | Koşu | Toplam | iSolar | GAOSB |
| :--- | :--- | ---: | ---: | ---: |
| **Prod** (sunucu, headless, güncel kod) | 2026-08-01 başarılı koşu | **1 dk 44 sn** | 73 sn | 27 sn |
| Laptop (headed, 4 temiz koşu) | 2026-07-17 / 07-20 | 61–69 sn | 37–45 sn | 21–23 sn |
| Laptop — **kuyruk** | 2026-07-17 15:38 (#7) | **tamamlanmadı** | **1319 sn (22 dk)** | 19 sn |

Okuma: **GAOSB düşük risk** — süre ay boyutuyla büyümüyor, neredeyse tamamen
tarayıcı açma + login sabiti. **Asıl kuyruk riski iSolar'da** — nadir ama gerçek bir
yavaşlama/takılma potansiyeli var ve tek gözlem 22 dakika. Marj hesabı tipik süreye
değil bu kuyruğa göre yapılmalıdır.

## Karar

1. **Otorite günlük ETL'e devredilir.** Bir ayın saatlik mahsuplaşma verisinde
   otorite `DailySettlementJob`'un yazdığı `settlement_hourly` kayıtlarıdır. Aylık
   iş, üretici olmaktan çıkıp **türetici** hâline gelir.

2. **Geçiş tek adımda yapılmaz — önce Seçenek (d), sonra hibrit.**

   **Faz 1 — Karşılaştır-ve-uyar (`compare-and-warn`).** Aylık iş bugünkü gibi
   çekmeye devam eder, ancak `settlement_hourly` üzerine yazmadan **önce** DB'deki
   mevcut ayı okur ve çektiğiyle karşılaştırır. Fark varsa (gün/saat kapsamı veya
   metrik toplamları) log + rapor + e-postaya **uyarı** düşer. Ezme davranışı bu
   fazda değişmez.

   Gerekçe: Faz 1 bugünkü bağımsızlık garantisini **bozmaz**, zamanlama ön koşulunu
   **tetiklemez**, risksizdir ve "iki yol aynı sayıyı veriyor mu" sorusunu ilk kez
   ölçülebilir hale getirir. Hibrit kararı bu veriyle desteklenir.

   **Faz 2 — Boşluk-farkında hibrit.** En az üç tam ay Faz 1 verisi toplandıktan ve
   uzlaşmazlık oranı kabul eşiğinin altında kaldıktan sonra: aylık iş ayın saat
   envanterini çıkarır, **tam günleri DB'den türetir**, yalnızca **eksik veya kısmi**
   günleri hedefli olarak yeniden çeker.

3. **Ön koşul — zamanlama (Faz 2 için, ertelenemez).** Günlük iş dünü işler ve
   09:00'da koşar; aylık iş ayın 1'inde 08:30'da. Bugün zararsızdır (aylık iş DB'ye
   bağımlı değildir), ancak **Faz 2'ye geçildiği anda** aylık iş ayın son günü için
   DB'ye bağımlı hale gelir ve o gün henüz yazılmamış olur — yani her ay son gün
   sessizce düşer. Sıra düzeltmesi Faz 2 koduyla **aynı sprintte ve ondan önce**
   devreye alınmalıdır; opsiyonel bir iyileştirme olarak ele alınamaz.

   Somut değer: aylık iş **10:00**'a alınır (günlük işe 60 dakika pay). Bu, tipik
   süreye (~2 dk) değil gözlenen en kötü duruma (22 dk) göre seçilmiştir, ~3×
   güvenlik payı bırakır.

4. **Saat aralığı geçici çözümdür; kalıcı çözüm kilit veya zincirlemedir.** İki işi
   sabit saat aralığıyla ayırmak kırılgandır — payı aşan tek bir yavaş koşu
   çakışmayı geri getirir ve iki job paylaşılan Chromium profilini
   (`config/gaosb_browser_profile/`) kullandığı için sonuç profil kilidi / launch
   timeout'tur (2026-07-23 prod olayının sınıfı). Kalıcı çözüm ikisinden biridir:
   (a) paylaşılan profil için **kilit** (ikinci iş kilidi bekler veya net hata verir),
   (b) **zincirleme** — günlük iş bittiğinde aylık iş tetiklenir. Faz 2 ile birlikte
   ele alınır; saat aralığı o zamana kadar köprüdür.

5. **"Tam gün" tanımı ve boşluk politikası.** Bir gün, `settlement_hourly`'de **24
   kayıt** varsa tamdır (Türkiye sabit UTC+3, DST yok — bu varsayım ADR'de kayıtlıdır
   ve değişirse buraya dönülür). 24'ten az kayıt **kısmi** gündür ve tam sayılmaz;
   hiç kaydı olmayan gün **eksik**tir. Kısmi ve eksik günler aynı şekilde ele alınır:
   hedefli yeniden çekim.

6. **Sessiz tamamlama yasak.** Aylık iş her koşuda envanteri log'a ve Excel raporuna
   yazar: kaç gün DB'den türetildi, kaç gün yeniden çekildi, hangi günler.
   Yeniden çekim başarısız olursa rapor **üretilmez** ya da eksikliği raporun içinde
   açıkça taşır — "her şey yolunda görünen eksik rapor" kabul edilmez (CLAUDE.md).

7. **Geçmiş aylara dokunulmaz.** Karar ileriye dönüktür. Faz 2 öncesi üretilmiş aylar
   yeniden hesaplanmaz; `force` ile yeniden üretim istenirse mevcut davranış korunur.

## Gerekçe

**Neden otorite günlük ETL?** Günlük iş veriyi kaynağa en yakın zamanda, günde bir
kez, dar bir pencerede çeker; hata olduğunda o gün fark edilir ve düzeltilebilir.
Aylık yeniden çekim ise ayda bir kez, geniş bir pencerede, 30 günlük veriyi tek
seferde alır — bir arıza tüm ayı götürür. 2026-08-01'de tam olarak bu oldu: GAOSB
login hatası aylık raporu düşürdü, oysa ayın 30 gününün verisi DB'de zaten duruyordu.

**Neden kademeli geçiş?** İki yolun aynı sayıyı ürettiği hiç doğrulanmadı ve
doğrulanmadan otorite değiştirmek, faturalama tutarlarını (ADR-0002) doğrulanmamış
bir kaynağa bağlamak olur. Faz 1 bu doğrulamayı sıfır risk ile sağlar.

**Neden marj kuyruğa göre?** Tipik koşu ~2 dakika; 30 dakikalık mevcut aralık buna
15× pay bırakıyor gibi görünür. Ancak elimizdeki tek kuyruk gözlemi 22 dakikadır ve
o koşu hiç tamamlanmamıştır. Marj, ortalamayı değil kuyruğu karşılamalıdır.

**ADR-0002'ye etki.** Faturalama tutarları bu kWh rakamlarının üstüne oturuyor.
ADR-0002 §4 zaten "kilitlenen katsayıdır, tutar değildir; kWh sonradan tamamlanır
veya yeniden hesaplanırsa tutarlar kilitli katsayılarla yeniden türetilir" diyor —
yani bu kararın kWh tarafındaki değişikliği faturalama modeliyle uyumludur. Ancak
`LOCKED` bir ayın kWh verisinin sessizce değişmesi (bugün olan budur) faturalama
açısından da istenmeyen bir durumdur; Faz 1'in uyarısı bu riski görünür kılar.

## Alternatifler

**(a) Mevcut durumu koru, yalnızca ezme davranışını belgele.** Reddedildi: aylık
raporu, verisi DB'de zaten duran bir aydan bağımsız olarak scraping arızasına açık
bırakır (2026-08-01 olayı). Ayrıca ölçülmemiş sessiz veri değişimi sürer.

**(b) Doğrudan tam DB türetme (scraping tamamen kaldırılır).** Reddedildi: iki yolun
uyumu doğrulanmadan otorite değiştirmek riskli; ayrıca günlük işte eksik kalan gün
için hiçbir telafi yolu bırakmaz — bugün kazara sağlanan düzeltme tamamen kaybolur.

**(c) Boşluk-farkında hibrit, tek adımda.** Reddedildi (ama Faz 2 olarak kabul):
doğru hedef, ancak doğrulama verisi olmadan tek adımda geçmek (b)'nin riskini daha
küçük ölçekte tekrarlar.

**(d) Karşılaştır-ve-uyar.** **Kabul — Faz 1.** Scraping yükünü azaltmaz, ama
bağımsızlığı bozmadan, zamanlama ön koşulunu tetiklemeden ve hiçbir davranışı
değiştirmeden asıl bilinmeyeni ölçer.

## Sonuç

- Faz 1 (karşılaştır-ve-uyar) ayrı bir sprint olarak planlanacak; kod bu ADR
  onaylanmadan yazılmayacak.
- Faz 2 (hibrit) en az üç tam ay Faz 1 verisi biriktikten sonra, zamanlama ön koşulu
  ve kilit/zincirleme çözümüyle **birlikte** ele alınacak.
- Bu ADR onaylandığında `docs/ROADMAP.md`'deki "Aylık İş Günlük Veriyi Sessizce
  Eziyor" teknik borç maddesi bu belgeye referans verecek şekilde kısaltılabilir.
