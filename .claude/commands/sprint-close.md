# /sprint-close

Sprint'i kapat, release notu hazırla, tag öner.

## Kullanım

```
/sprint-close S17
```

## Adımlar

1. `docs/sprints/PLAN-S[NO].md` dosyasını oku.
2. `git log --oneline` ile sprint süresindeki commit'leri al.
3. CHANGELOG.md'de bu sprint'e ait satırları bul.
4. Başarı kriterlerini tek tek kontrol et:
   - `python main.py --health` çalıştır
   - Her kriteri [✓] veya [✗] olarak işaretle
5. Sprint kapanış özeti yaz ve `docs/sprints/CLOSE-S[NO].md` olarak kaydet.
6. Release notu taslağı hazırla.
7. Kullanıcıya göster:

```
## Sprint [NO] Kapanış

Başarı Kriterleri:
- [✓/✗] ...

Özet:
[Ne tamamlandı, ne kaldı]

Önerilen tag: v[X.Y.Z]-rc[N]
Önerilen release notu: [taslak]

Tag oluşturulsun mu? (evet / hayır)
```

8. Onay gelince: `git tag -a v[X.Y.Z]-rc[N] -m "[mesaj]"`
9. Push için ayrıca sor.

**GIT İŞLEMİ KULLANICI ONAYI OLMADAN YAPILMAZ.**
