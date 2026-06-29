# ADR-0001: İsOlar Verisi İçin Öncelikli Kaynak Olarak Excel Export Kullanımı

## Durum

İsOlar sisteminde üretim verileri filtrelenerek Excel formatında dışa aktarılabiliyor. Proje kapsamında günlük ve saatlik kırılımda üretim verileri alınarak yönetici raporları, dashboard ekranları ve aylık mahsuplaşma kontrol raporları üretilecektir.

## Karar

İlk geliştirme aşamasında HTML tablo scraping veya doğrudan sayfa DOM okuma yerine, İsOlar sisteminin sunduğu Excel export özelliği kullanılacaktır.

## Gerekçe

- Daha kararlı veri kaynağı sağlar.
- Sayfa tasarımı değişikliklerinden daha az etkilenir.
- Büyük veri setleri için daha uygundur.
- Denetlenebilir ham veri dosyası saklanabilir.
- Aylık mahsuplaşma kontrollerinde izlenebilirlik sağlar.
- Yönetici raporları için tekrar üretilebilir veri akışı oluşturur.

## Alternatifler

- HTML tablo scraping
- Browser DOM parsing
- Gizli API çağrılarını doğrudan kullanma
- Manuel Excel yükleme

## Sonuç

İlk sürümde otomasyon şu akışa göre geliştirilecektir:

Login → Bölge seçimi → Tarih filtresi → Excel export → Ham dosya arşivi → Validasyon → PostgreSQL → Raporlama