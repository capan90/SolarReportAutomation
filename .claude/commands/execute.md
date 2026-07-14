# /execute

Onaylanmış sprint planını uygula.

## Kullanım

```
/execute PLAN-S17
```

## Adımlar

1. `docs/sprints/PLAN-[NO].md` dosyasını oku.
2. CLAUDE.md'deki değişmez kuralları tekrar oku.
3. "Etkilenecek Dosyalar" ve "Yeni Dosyalar" listesini kontrol et.
4. Uygulama adımlarını sırayla yürüt:
   - Her adım sonrası kısa ilerleme notu yaz.
   - Bir adım beklenmedik bir sorunla karşılaşırsa dur, kullanıcıya sor.
5. Tüm adımlar bittikten sonra:
   - `python main.py --health` çalıştır
   - `pytest tests/smoke/ -x -q` çalıştır
6. Test sonuçlarını kullanıcıya göster.
7. `/review` komutunu çalıştır.
8. Review sonucuna göre:
   - **Geç** → `/commit` komutuna yönlendir
   - **Bekle** → sorunları listele, düzeltme için onay iste
   - **Engelle** → dur, kullanıcıya açıkla

## Kurallar

- Canonical Layer'a dokunma — plan bunu içerse dur ve sor.
- 10 dosya / ~300 satır sınırını aş → dur ve böl.
- Her dosyayı değiştirmeden önce oku.
- Discovery kodu scratch/ klasörüne yaz, production'a karıştırma.
