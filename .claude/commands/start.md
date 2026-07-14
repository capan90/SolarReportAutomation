# /start

Her yeni session'ın ilk komutu. Bağlamı kur, durumu özetle.

## Adımlar

1. CLAUDE.md oku — kuralları ve kısıtları belleğe al.
2. Şu dosyaları sırayla oku:
   - CHANGELOG.md (son 20 satır) → mevcut release durumu
   - ROADMAP.md → hangi sprint'teyiz
   - docs/sprints/ → en son PLAN-*.md varsa oku
3. `git log --oneline -5` çalıştır → son commit'ler
4. `python main.py --health` çalıştır → sistem sağlıklı mı
5. Kullanıcıya kısa durum özeti sun:

```
## Session Durumu

Release  : [RC-X, Sprint Y]
Son commit: [mesaj]
Açık plan : [varsa PLAN-XX.md başlığı, yoksa "yok"]
Sağlık   : [✓ Sağlıklı / ✗ Sorun var — açıkla]

Ne yapmak istersiniz?
```

Kullanıcı cevap vermeden hiçbir şey yapma.
