# /sprint-plan

Kullanıcının hedefinden eksiksiz sprint planı üret.

## Adımlar

1. CLAUDE.md, ARCHITECTURE.md, ROADMAP.md oku.
2. docs/sprints/ klasöründeki son plan numarasını bul → yeni numara belirle.
3. Kullanıcının hedefini netleştir — belirsizlik varsa tek soru sor.
4. Aşağıdaki şablonu doldur.
5. `docs/sprints/PLAN-S[NO].md` olarak kaydet.
6. Kullanıcıya göster, onay iste.
7. **Onay gelmeden kod yazma.**

## Plan Şablonu

```markdown
# Sprint [NO] — [BAŞLIK]
Tarih: [YYYY-MM-DD]

## Hedef
[Tek cümle — ne teslim edilecek]

## Kapsam Dışı (yapılmayacaklar)
- ...

## Etkilenecek Dosyalar
| Dosya | Değişiklik türü |
|---|---|
| app/... | güncelleme |

## Yeni Dosyalar
| Dosya | Amaç |
|---|---|
| app/... | ... |

## Uygulama Adımları
1. ...
2. ...
3. ...

## Başarı Kriterleri
- [ ] python main.py --health yeşil
- [ ] Smoke test geçiyor
- [ ] Canonical Layer değişmedi
- [ ] ...

## Riskler
| Risk | Olasılık | Önlem |
|---|---|---|
| ... | Orta | ... |

## ADR Gerekiyor mu?
[ ] Evet → başlık: ...
[x] Hayır

## Tahmini Dosya / Satır
Dosya sayısı: X (max 10)
Satır tahmini: ~XXX (max ~300)
```
