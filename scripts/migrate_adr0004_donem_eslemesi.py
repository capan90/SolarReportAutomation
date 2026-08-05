"""
Neden: ADR-0004 — OSB kesintisinin dönem eşlemesini düzeltir.

İki gerçek GAOSB faturası, bir ayın OSB katsayısının O AYIN kendi üretimini
değerleyen fiyat olduğunu gösterdi. Sistem ise katsayıyı bir önceki aydan
alıyordu. Düzeltme mekanik: kütükte `target := source`.

DOKUNULMAYANLAR
- `compute()`, mahsuplaşma motoru ve `monthly_billing` şeması DEĞİŞMEZ.
  Tutarlar mevcut `BillingService.compute()` ile yeniden türetilir; ikinci bir
  matematik yolu açılmaz (override akışının aynı gerekçesi).
- `settlement_*` tablolarına yalnızca dolaylı OKUMA yapılır (kWh snapshot'ları
  zaten monthly_billing'de). Portala çıkılmaz, tarayıcı açılmaz.

PLAN VERİDEN TÜRETİLİR, AY ADI GÖMÜLMEZ
Her monthly_billing ayı için yeni katsayı = kütükte `source == o ay` olan
satırın fiyatı. Kaynağı olmayan ay PENDING_RATE'e döner (ADR-0004 Karar 6:
tahmini değerle doldurulmaz). Böylece script prod'da beklenmedik bir ay
bulursa da doğru davranır.

id=4 (source=2026-07) BİLEREK DIŞARIDA — KUTUK_HARIC
O satırdaki 2,972196 değeri faturanın **Aktif Enerji** satırından okunmuş;
oysa katsayı **EPYS Bedelli Üretim Miktarı** satırından okunur (ADR-0004
§Durum). Değeri yanlış olduğu için hedefi Temmuz'a çevrilmez. Çevrilseydi:

    compute(2026,7) -> apply_pending_electricity_price(2026,7)
      source id=4, status BEKLIYOR                      -> geçer
      monthly_billing[2026-07].osb_unit_price_try NULL  -> geçer
      set_osb_unit_price(2,972196) -> TEMMUZ KİLİTLENİRDİ

Satır silinmez, durumu değiştirilmez (BEKLIYOR kalır). Ağustos faturası
gelince `source = Temmuz` girişi, UNIQUE(source_year, source_month) sayesinde
bu satırın değerini üzerine yazacak ve yanlış değer kendiliğinden düzelecek.

KİLİT DELME
Kilitli ayın katsayısı `BillingRepository.override_locked_month` ile yazılır —
sistemdeki TEK kilit delme yolu; ikinci bir bypass açılmaz. Tek istisna, bir ayı
PENDING_RATE'e geri döndürmektir: override_locked_month bir DEĞER yazmak için
tasarlandı, NULL'a çekemez. Bu yol bilerek script'in İÇİNDE tutuldu ve
production koduna EKLENMEDİ (ADR-0004 Karar 7: "yalnızca migration script'i
tarafından çağrılır ve arayüze bağlanmaz").

DENETİM
Değişen her ay `audit_log`'a `billing_period_remap` eylemiyle eski→yeni
değerleriyle yazılır. `billing_override`'dan bilerek AYRI: dashboard'daki
"Düzeltildi" rozeti bu remap'i kullanıcı hatası gibi göstermemeli.

Kullanım:
    python scripts/migrate_adr0004_donem_eslemesi.py            # dry-run
    python scripts/migrate_adr0004_donem_eslemesi.py --apply    # gerçekten yaz

ÖNCE YEDEK ALIN. --apply geri dönüşsüzdür (audit_log'daki eski değerlerle
elle geri alınabilir, ama yedek asıl güvencedir).
"""
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Neden: Kütükte hedefi DEĞİŞTİRİLMEYECEK kaynaklar (üretim dönemi anahtarıyla).
# Gerekçe yukarıda; kısaca: değeri yanlış fatura satırından okunmuş.
KUTUK_HARIC = {(2026, 7)}

AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
      "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

REMAP_ACTION = "billing_period_remap"
REMAP_USER = "migration (ADR-0004)"


def ay_adi(year, month):
    return "%s %d" % (AY[month - 1], year)


def dec(v):
    return Decimal(str(v)) if v is not None else None


def para(v):
    if v is None:
        return "Bekleniyor"
    return "{:,.2f}".format(float(v)).replace(",", "X").replace(".", ",").replace("X", ".")


def kat(v):
    return "—" if v is None else "{:.6f}".format(float(v)).replace(".", ",")


def kwh_str(v):
    if v is None:
        return "—"
    return "{:,.1f}".format(float(v)).replace(",", "X").replace(".", ",").replace("X", ".")


def cizgi(n=100):
    print("-" * n)


def plani_kur(session, models):
    """
    Neden: Planı VERİDEN türetir; hem dry-run hem --apply aynı fonksiyonu çağırır,
    böylece "gördüğün şeyden başkası uygulanamaz".
    """
    MonthlyBilling, MonthlyElectricityPrice = models

    prices = (session.query(MonthlyElectricityPrice)
              .order_by(MonthlyElectricityPrice.source_year,
                        MonthlyElectricityPrice.source_month).all())
    months = (session.query(MonthlyBilling)
              .order_by(MonthlyBilling.year, MonthlyBilling.month).all())

    kutuk = []
    kaynak_by_ay = {}
    for p in prices:
        anahtar = (p.source_year, p.source_month)
        haric = anahtar in KUTUK_HARIC
        kutuk.append({
            "id": p.id, "source": anahtar, "fiyat": dec(p.unit_price_try),
            "mevcut_hedef": (p.target_year, p.target_month),
            "yeni_hedef": anahtar, "status": p.status, "haric": haric,
            "degisiyor": (not haric) and (p.target_year, p.target_month) != anahtar,
        })
        if not haric:
            kaynak_by_ay[anahtar] = p

    from app.billing.service import _money  # migration ile aynı yuvarlama

    aylar = []
    for m in months:
        uretim, fazla = dec(m.production_kwh_snapshot), dec(m.excess_sale_kwh_snapshot)
        osb_kwh = (uretim - fazla) if (uretim is not None and fazla is not None) else None
        mevcut_kat, mevcut_ded = dec(m.osb_unit_price_try), dec(m.osb_deduction_try)

        src = kaynak_by_ay.get((m.year, m.month))
        yeni_kat = dec(src.unit_price_try) if src is not None else None
        yeni_ded = _money(osb_kwh * yeni_kat) if (yeni_kat is not None and osb_kwh is not None) else None

        if yeni_kat is None:
            islem = "PENDING"
        elif mevcut_kat is not None and yeni_kat == mevcut_kat:
            islem = "DOKUNMA"
        else:
            islem = "OVERRIDE"

        aylar.append({
            "year": m.year, "month": m.month, "status": m.status, "osb_kwh": osb_kwh,
            "mevcut_kat": mevcut_kat, "yeni_kat": yeni_kat,
            "mevcut_ded": mevcut_ded, "yeni_ded": yeni_ded,
            "kaynak_id": src.id if src is not None else None, "islem": islem,
        })
    return kutuk, aylar


def plani_bas(kutuk, aylar):
    print()
    print("FAZ 1 — KÜTÜK EŞLEMESİ (monthly_electricity_price): target := source")
    cizgi()
    print("%-4s %-15s %-12s %-15s %-15s %-11s %s"
          % ("id", "KAYNAK", "FİYAT", "HEDEF (mevcut)", "HEDEF (yeni)", "DURUM", "İŞLEM"))
    cizgi()
    for k in kutuk:
        if k["haric"]:
            islem = "DIŞARIDA — değeri yanlış fatura satırından (KUTUK_HARIC)"
            yeni = "(değişmez)"
        else:
            islem = "GÜNCELLENECEK" if k["degisiyor"] else "değişmiyor"
            yeni = ay_adi(*k["yeni_hedef"])
        print("%-4s %-15s %-12s %-15s %-15s %-11s %s"
              % (k["id"], ay_adi(*k["source"]), kat(k["fiyat"]),
                 ay_adi(*k["mevcut_hedef"]), yeni, k["status"], islem))

    print()
    print("FAZ 2 — AYLIK KAYITLAR (monthly_billing)")
    cizgi()
    for a in aylar:
        print("%s  [%s]  OSB kWh: %s" % (ay_adi(a["year"], a["month"]), a["status"],
                                         kwh_str(a["osb_kwh"])))
        print("    katsayı : %s -> %s%s"
              % (kat(a["mevcut_kat"]), kat(a["yeni_kat"]),
                 ("   (kaynak id=%s)" % a["kaynak_id"]) if a["kaynak_id"] else "   (kaynak YOK)"))
        print("    kesinti : %s -> %s" % (para(a["mevcut_ded"]), para(a["yeni_ded"])))
        if a["mevcut_ded"] is not None and a["yeni_ded"] is not None:
            print("    fark    : %s TL" % para(a["yeni_ded"] - a["mevcut_ded"]))
        elif a["mevcut_ded"] is not None:
            print("    fark    : %s TL (tutar SİLİNİYOR)" % para(-a["mevcut_ded"]))
        etiket = {"OVERRIDE": "OVERRIDE — override_locked_month ile yazılacak",
                  "PENDING": "PENDING_RATE'E DÖNDÜRÜLECEK (kaynak yok)",
                  "DOKUNMA": "DOKUNULMAYACAK"}[a["islem"]]
        print("    işlem   : %s" % etiket)
        print()


def audit_detay(a):
    """audit_log.details — dashboard rozetleriyle aynı JSON kalıbı."""
    return json.dumps({
        "year": a["year"], "month": a["month"], "kind": "period_remap", "adr": "ADR-0004",
        "old_coefficient": str(a["mevcut_kat"]) if a["mevcut_kat"] is not None else None,
        "new_coefficient": str(a["yeni_kat"]) if a["yeni_kat"] is not None else None,
        "old_deduction": str(a["mevcut_ded"]) if a["mevcut_ded"] is not None else None,
        "new_deduction": str(a["yeni_ded"]) if a["yeni_ded"] is not None else None,
        "reason": ("Donem eslemesi duzeltildi: katsayi artik o ayin KENDI uretimini "
                   "degerleyen fiyattir (ADR-0004)."),
    }, ensure_ascii=False)


def audit_onizle(aylar):
    print("FAZ 3 — audit_log ÖNİZLEMESİ (action=%s)" % REMAP_ACTION)
    cizgi()
    yazilacak = [a for a in aylar if a["islem"] in ("OVERRIDE", "PENDING")]
    if not yazilacak:
        print("   (yazılacak kayıt yok)")
    for a in yazilacak:
        print("   %s | %s" % (REMAP_USER, ay_adi(a["year"], a["month"])))
        print("      %s" % audit_detay(a))
    print()


def main():
    parser = argparse.ArgumentParser(description="ADR-0004 dönem eşlemesi düzeltmesi")
    parser.add_argument("--apply", action="store_true", help="Gerçekten yaz (yoksa dry-run)")
    parser.add_argument("--database-url", default=None, help="Hedef DB (varsayılan: .env)")
    args = parser.parse_args()

    if args.database_url:
        import os
        os.environ["DATABASE_URL"] = args.database_url

    import app.core.config  # noqa: F401  (.env yükler)
    from app.database.db_config import DATABASE_URL
    from app.database.db_session import SessionLocal
    from app.database.models import AuditLog, MonthlyBilling, MonthlyElectricityPrice

    hedef = DATABASE_URL
    if "://" in hedef and "@" in hedef.split("://", 1)[1]:
        bas, son = hedef.split("://", 1)
        hedef = bas + "://***@" + son.split("@", 1)[1]

    mod = "UYGULAMA (--apply)" if args.apply else "KURU KOŞU (dry-run)"
    print("=" * 100)
    print("ADR-0004 DÖNEM EŞLEMESİ DÜZELTMESİ — %s" % mod)
    print("Veritabanı: %s" % hedef)
    print("=" * 100)

    session = SessionLocal()
    try:
        kutuk, aylar = plani_kur(session, (MonthlyBilling, MonthlyElectricityPrice))
        plani_bas(kutuk, aylar)
        audit_onizle(aylar)

        override_sayisi = len([a for a in aylar if a["islem"] == "OVERRIDE"])
        pending_sayisi = len([a for a in aylar if a["islem"] == "PENDING"])
        kutuk_sayisi = len([k for k in kutuk if k["degisiyor"]])

        print("=" * 100)
        print("ÖZET")
        cizgi()
        print("   Kütükte hedefi değişecek satır : %d" % kutuk_sayisi)
        print("   Kütükte dışarıda bırakılan     : %d" % len([k for k in kutuk if k["haric"]]))
        print("   OVERRIDE edilecek ay           : %d" % override_sayisi)
        print("   PENDING'e döndürülecek ay      : %d" % pending_sayisi)
        print("   DOKUNULMAYACAK ay              : %d"
              % len([a for a in aylar if a["islem"] == "DOKUNMA"]))
        print("=" * 100)

        if not args.apply:
            print()
            print("KURU KOŞU — hiçbir şey yazılmadı.")
            print("Uygulamak için: python scripts/migrate_adr0004_donem_eslemesi.py --apply")
            print("ÖNCE YEDEK ALIN.")
            session.rollback()
            return

        # ------------------------------------------------------------------
        # UYGULAMA
        # ------------------------------------------------------------------
        print()
        print(">>> UYGULANIYOR")
        cizgi()

        # FAZ 1 — kütük
        for k in kutuk:
            if not k["degisiyor"]:
                continue
            row = (session.query(MonthlyElectricityPrice)
                   .filter(MonthlyElectricityPrice.id == k["id"]).first())
            row.target_year, row.target_month = k["yeni_hedef"]
            print("   [kütük] id=%s hedef: %s -> %s"
                  % (k["id"], ay_adi(*k["mevcut_hedef"]), ay_adi(*k["yeni_hedef"])))
        session.commit()

        # FAZ 2 — aylar
        from app.billing import BillingService
        service = BillingService()

        for a in aylar:
            if a["islem"] == "DOKUNMA":
                print("   [ay] %s dokunulmadı" % ay_adi(a["year"], a["month"]))
                continue

            if a["islem"] == "OVERRIDE":
                # Neden: TEK kilit delme yolu. Tutarları compute() yeniden türetir.
                service.override_locked_month(
                    year=a["year"], month=a["month"],
                    reason="ADR-0004 donem eslemesi duzeltmesi (migration)",
                    changed_by=REMAP_USER,
                    osb_unit_price_try=a["yeni_kat"],
                )
                sonuc = service.get_monthly(a["year"], a["month"])
                print("   [ay] %s OVERRIDE: katsayı %s, kesinti %s"
                      % (ay_adi(a["year"], a["month"]),
                         kat(sonuc.osb_unit_price_try), para(sonuc.osb_deduction_try)))

            elif a["islem"] == "PENDING":
                # Neden: override_locked_month bir DEĞER yazmak içindir, NULL'a çekemez.
                # Bu yol bilerek script'in içinde; production koduna eklenmedi
                # (ADR-0004 Karar 7).
                row = (session.query(MonthlyBilling)
                       .filter(MonthlyBilling.year == a["year"],
                               MonthlyBilling.month == a["month"]).first())
                row.osb_unit_price_try = None
                row.osb_deduction_try = None
                row.osb_price_entered_by = None
                row.osb_price_entered_at = None
                row.locked_at = None
                row.status = "PENDING_RATE"
                session.commit()
                print("   [ay] %s PENDING_RATE'e döndürüldü (katsayı ve tutar NULL)"
                      % ay_adi(a["year"], a["month"]))

            # FAZ 3 — denetim
            session.add(AuditLog(
                username=REMAP_USER, ip_address="localhost",
                action=REMAP_ACTION, details=audit_detay(a), success=True,
            ))
            session.commit()

        print()
        print(">>> TAMAMLANDI. Raporlar bayatladı; tazelik mekanizması yeniden üretecek.")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
