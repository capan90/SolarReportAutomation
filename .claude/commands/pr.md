# /pr

Sprint planından otomatik Pull Request oluştur.

## Kullanım

```
/pr S17
```

## Adımlar

1. `docs/sprints/PLAN-S[NO].md` oku — hedef ve başarı kriterlerini al.
2. `git branch --show-current` çalıştır — mevcut branch'i öğren.
3. `git log main..HEAD --oneline` çalıştır — bu branch'teki commit'leri listele.
4. GitHub MCP ile PR taslağı hazırla:

```
Başlık : [Sprint NO] [Plan başlığı]
Branch : [mevcut] → main
Body   :
  ## Hedef
  [Sprint hedefi]

  ## Değişiklikler
  [commit listesi]

  ## Test
  - [ ] python main.py --health geçti
  - [ ] Smoke test geçti
  - [ ] Canonical Layer değişmedi

  ## Sprint Planı
  docs/sprints/PLAN-S[NO].md
```

5. Kullanıcıya göster, onay iste.
6. Onay gelince GitHub MCP ile PR aç.

**PR KULLANICI ONAYI OLMADAN AÇILMAZ.**
