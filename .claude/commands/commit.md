# /commit

Güvenli commit akışı — kullanıcı onayı olmadan hiçbir şey yapılmaz.

## Adımlar

1. `git diff --cached` çalıştır — staged değişiklik yoksa bildir, dur.
2. Staged dosyaları listele, kullanıcıya göster.
3. CHANGELOG.md'yi güncelle:
   - Uygun versiyona (unreleased veya mevcut RC) ekle
   - Değişiklik tipine göre: Added / Fixed / Changed / Removed
4. Commit mesajını oluştur (aşağıdaki format).
5. Kullanıcıya şunu göster:

```
## Commit Özeti

Staged dosyalar:
- [liste]

Changelog eki:
- [eklenen satır]

Commit mesajı:
[mesaj]

Onaylıyor musunuz? (evet / hayır / düzenle)
```

6. "evet" gelince: `git commit -m "..."` çalıştır.
7. Push için ayrıca sor: "Push da yapılsın mı?"

## Mesaj Formatı

```
<fiil>(<kapsam>): <ne değişti — neden>

Fiiller  : add / fix / refactor / docs / test / chore
Kapsam   : adapter / canonical / settlement / dashboard / etl / infra / docs
Dil      : Türkçe, teknik terimler İngilizce
Max uzunluk: 72 karakter
```

Örnekler:
```
add(adapter): GAOSB VIEWSTATE yönetimi eklendi
fix(settlement): gece saati delta hesabı sıfır dönüyordu
refactor(canonical): EnergyDataPoint nullable alanlar temizlendi
docs(adr): ADR-0003 REST API kararı eklendi
```

**GIT İŞLEMİ KULLANICI ONAYI OLMADAN YAPILMAZ.**
