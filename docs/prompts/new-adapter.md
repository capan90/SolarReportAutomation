# Prompt: Yeni Adapter Geliştirme

## Kullanım
iSolar veya GAOSB adapter'ı geliştirirken plan session'da kullan.

---

Aşağıdaki adapter'ı planlamana ihtiyacım var.

**Adapter:** [iSolar / GAOSB / SMA / ...]

**Hedef:**
[Bu sprintte ne yapılacak? Örn: "GAOSB SessionManager + VIEWSTATE yönetimi"]

**Kısıtlar:**
- Canonical Layer (EnergyDataPoint, MeterReading) değiştirilmez
- Mevcut çalışan adapter'lar bozulmaz
- Portal-özel logic adapter içinde kalır, platform katmanına sızmaz
- [Varsa ek kısıt]

**Bilinen teknik detaylar:**
[Auth yöntemi, endpoint, veri formatı — bilmiyorsam "bilmiyorum" de]

Şunları yap:
1. CLAUDE.md ve ARCHITECTURE.md oku
2. Etkilenecek dosyaları listele
3. Capability flags belirle
4. Adım adım plan çıkar — her adım max ~300 satır
5. Risk ve ADR gereksinimi belirt
6. KOD YAZMA — onaylayayım, sonra /execute ile başlarız
