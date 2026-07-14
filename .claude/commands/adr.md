# /adr

Yeni mimari karar kaydı oluştur.

## Adımlar

1. `docs/adr/` klasöründeki dosyaları listele → son numarayı bul.
2. Kullanıcının konusunu netleştir — belirsizlik varsa tek soru sor.
3. Şablonu doldur, `docs/adr/ADR-[XXXX]-[konu].md` olarak kaydet.
4. Kullanıcıya göster, onay iste.

## ADR Şablonu

```markdown
# ADR-[XXXX]: [Başlık]
Tarih  : [YYYY-MM-DD]
Durum  : Önerilen

## Bağlam
[Neden bu karar gerekti?]

## Karar
[Ne yapılacak?]

## Gerekçe
- [Neden bu seçenek?]

## Alternatifler
- [Alternatif 1] — neden elendi
- [Alternatif 2] — neden elendi

## Sonuçlar
Olumlu:
- ...
Trade-off:
- ...

## Solar Bağlamı
Etkilenen katman  : [Adapter / Canonical / Settlement / Dashboard / Infra]
Mevcut ETL etkisi : [Bozar / Bozmaz / Genişletir]

## İlgili ADR'ler
- ADR-0001 (Excel Export önceliği)
```
