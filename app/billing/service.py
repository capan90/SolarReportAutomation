"""
Neden: Faturalama iş kuralları (ADR-0002). Settlement Engine'e eklenmedi çünkü
engine saf ve DB'siz kalmalı; ayrıca mahsuplaşma kuralı hiç değişmezken tarife her
ay değişir — farklı değişim hızındaki iki sorumluluk ayrı sınıflarda tutulur.

Hesaplar (her ikisi de KDV HARİÇ / net TL):
  Fazla Satış Faturası = Fazla Satış (kWh)                × sabit katsayı (TL/kWh)
  OSB Kesintisi        = (Üretim - Fazla Satış) (kWh)     × değişken katsayı (TL/kWh)
"""
import calendar
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from app.billing.models import (
    PRICE_STATUS_APPLIED,
    PRICE_STATUS_CORRECTION_PENDING,
    PRICE_STATUS_PENDING,
    RATE_TYPE_EXCESS_SALE,
    STATUS_LOCKED,
    STATUS_PENDING_RATE,
    BillingRateDto,
    BillingValidationError,
    MonthlyBillingResult,
)
from app.core.logger import setup_logger

logger = setup_logger("BillingService")

# Neden: Tutarlar kuruşa yuvarlanır; bankacılık varsayılanı ROUND_HALF_EVEN fatura
# tutarında beklenmedik aşağı yuvarlama üretir, ROUND_HALF_UP fatura pratiğine uyar.
_MONEY_QUANT = Decimal("0.01")


def _to_decimal(value: Any, field: str) -> Decimal:
    """
    Neden: float kWh değerleri Decimal'e str üzerinden çevrilir; doğrudan
    Decimal(float) ikili gösterim artığı taşır (0.1 -> 0.1000000000000000055...).
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as e:
        raise BillingValidationError(f"{field} sayıya çevrilemedi: {value!r}") from e


def _money(value: Decimal) -> Decimal:
    """Neden: Tutar alanları 2 haneye ROUND_HALF_UP ile sabitlenir."""
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _month_end(year: int, month: int) -> date:
    """Neden: Tarife araması ayın son gününe göre yapılır (ADR-0002 §3)."""
    return date(year, month, calendar.monthrange(year, month)[1])


class BillingService:
    """
    Neden: Faturalama hesaplarının tek giriş noktası. Persistans ve kilit
    garantileri BillingRepository'de; iş kuralları ve yuvarlama burada.
    """

    def __init__(self, repository=None):
        # Neden: Testler sahte repository enjekte edebilsin (DB'siz birim test).
        if repository is None:
            from app.database.billing_repository import BillingRepository

            repository = BillingRepository()
        self.repo = repository

    # ------------------------------------------------------------------
    # Sabit katsayı
    # ------------------------------------------------------------------
    def get_current_rate(self, as_of: Optional[date] = None) -> Optional[BillingRateDto]:
        """
        Neden: Verilen tarihte (varsayılan: bugün) geçerli sabit katsayıyı döner.
        Hiç tarife tanımlanmamışsa None — çağıran taraf bunu "tanımsız" olarak
        göstermeli, 0 olarak değil.
        """
        as_of = as_of or date.today()
        row = self.repo.get_effective_rate(RATE_TYPE_EXCESS_SALE, as_of)
        if row is None:
            logger.warning("%s için geçerli tarife bulunamadı (as_of=%s).", RATE_TYPE_EXCESS_SALE, as_of)
            return None
        return BillingRateDto(
            id=row["id"],
            rate_type=row["rate_type"],
            unit_price_try=row["unit_price_try"],
            valid_from=row["valid_from"],
            created_by=row["created_by"],
            created_at=row.get("created_at"),
            note=row.get("note"),
        )

    def set_rate(
        self,
        unit_price_try: Any,
        valid_from: date,
        created_by: str,
        note: Optional[str] = None,
    ) -> BillingRateDto:
        """
        Neden: Yeni sabit katsayı kaydeder (append-only). Geçmiş aylara etki etmez —
        her ayın katsayısı monthly_billing'e snapshot olarak kilitlenmiştir.

        valid_from ayın İLK GÜNÜ olmak zorundadır (ADR-0002 §2): tarife ay ortasında
        değişemez, aksi halde bir ayın hangi katsayıyla faturalandığı belirsizleşir.
        """
        price = _to_decimal(unit_price_try, "unit_price_try")
        if price <= 0:
            raise BillingValidationError(f"Birim fiyat pozitif olmalıdır: {price}")
        if not isinstance(valid_from, date):
            raise BillingValidationError(f"valid_from bir tarih olmalıdır: {valid_from!r}")
        if valid_from.day != 1:
            raise BillingValidationError(
                f"valid_from ayın ilk günü olmalıdır (verilen: {valid_from.isoformat()})."
            )
        if not str(created_by).strip():
            raise BillingValidationError("created_by boş olamaz (denetim izi zorunlu).")

        row = self.repo.add_rate(
            rate_type=RATE_TYPE_EXCESS_SALE,
            unit_price_try=price,
            valid_from=valid_from,
            created_by=str(created_by).strip(),
            note=note,
        )
        return BillingRateDto(
            id=row["id"],
            rate_type=row["rate_type"],
            unit_price_try=row["unit_price_try"],
            valid_from=row["valid_from"],
            created_by=row["created_by"],
            created_at=row.get("created_at"),
            note=row.get("note"),
        )

    def list_rate_history(self, limit: int = 50) -> List[BillingRateDto]:
        """Neden: Dashboard katsayı geçmişi (Sprint B'de kullanılacak)."""
        return [
            BillingRateDto(
                id=r["id"],
                rate_type=r["rate_type"],
                unit_price_try=r["unit_price_try"],
                valid_from=r["valid_from"],
                created_by=r["created_by"],
                created_at=r.get("created_at"),
                note=r.get("note"),
            )
            for r in self.repo.list_rates(RATE_TYPE_EXCESS_SALE, limit=limit)
        ]

    # ------------------------------------------------------------------
    # Aylık hesap
    # ------------------------------------------------------------------
    def compute(
        self,
        year: int,
        month: int,
        production_kwh: Any,
        excess_sale_kwh: Any,
    ) -> MonthlyBillingResult:
        """
        Neden: Ayın finansal satırını oluşturur/günceller.

        - Satır ilk kez oluşuyorsa o ay için geçerli sabit katsayı snapshot'lanır ve
          bir daha değişmez. Zaten snapshot varsa yeniden okunmaz.
        - Veri tutarsızsa (negatif değer veya fazla satış > üretim) HİÇBİR tutar
          hesaplanmaz; ay PENDING_RATE'te bırakılır ve hata loglanır (ADR-0002 §7).
          Sessizce sıfıra kırpma yapılmaz.
        - OSB birim fiyatı girilmişse kesinti de kilitli fiyatla yeniden türetilir.
        """
        production = _to_decimal(production_kwh, "production_kwh")
        excess = _to_decimal(excess_sale_kwh, "excess_sale_kwh")

        existing = self.repo.get_monthly(year, month)

        # 1. Katsayı snapshot'ı — yalnızca henüz kilitlenmemişse okunur.
        rate_snapshot: Optional[Decimal] = existing.get("excess_sale_rate_try") if existing else None
        rate_id: Optional[int] = existing.get("excess_sale_rate_id") if existing else None
        if rate_snapshot is None:
            current = self.get_current_rate(as_of=_month_end(year, month))
            if current is not None:
                rate_snapshot = current.unit_price_try
                rate_id = current.id
            else:
                logger.error(
                    "%04d-%02d için fazla satış katsayısı tanımlı değil; fatura tutarı "
                    "hesaplanamadı. Dashboard'dan katsayı tanımlanmalı.",
                    year, month,
                )

        # 2. Veri tutarlılığı — kırpma yok, hesap yapılmaz.
        self_consumed: Optional[Decimal] = None
        data_ok = True
        if production < 0 or excess < 0:
            logger.error(
                "%04d-%02d faturalama girdisi negatif (üretim=%s, fazla satış=%s); "
                "tutar hesaplanmadı, ay PENDING_RATE bırakıldı.",
                year, month, production, excess,
            )
            data_ok = False
        elif excess > production:
            logger.error(
                "%04d-%02d fazla satış (%s kWh) üretimden (%s kWh) büyük — veri tutarsız; "
                "tutar hesaplanmadı, ay PENDING_RATE bırakıldı.",
                year, month, excess, production,
            )
            data_ok = False
        else:
            self_consumed = production - excess

        # 3. Tutarları türet.
        invoice_try: Optional[Decimal] = None
        deduction_try: Optional[Decimal] = None
        if data_ok and rate_snapshot is not None:
            invoice_try = _money(excess * rate_snapshot)

        osb_price = existing.get("osb_unit_price_try") if existing else None
        if data_ok and osb_price is not None and self_consumed is not None:
            deduction_try = _money(self_consumed * osb_price)

        row = self.repo.upsert_monthly(
            year=year,
            month=month,
            production_kwh=production if data_ok else None,
            excess_sale_kwh=excess if data_ok else None,
            excess_sale_invoice_try=invoice_try,
            osb_deduction_try=deduction_try,
            rate_snapshot_try=rate_snapshot,
            rate_id=rate_id,
        )

        # Neden: Satır AZ ÖNCE oluştu; bu aya beslenmeyi bekleyen bir fatura fiyatı
        # varsa şimdi uygulanır. BEST-EFFORT — kaynak kütüğündeki bir hata
        # mahsuplaşma yazımını ASLA düşürmemeli (ADR-0003 Faz 1'deki
        # _reconcile_best_effort ile aynı gerekçe). Hata sessizce yutulmuyor,
        # stack trace ile loglanıyor.
        applied = None
        try:
            applied = self.apply_pending_electricity_price(year, month)
        except Exception as e:
            logger.error(
                "%04d-%02d için bekleyen fatura fiyatı uygulanamadı (yazım etkilenmedi): "
                "%s: %s", year, month, type(e).__name__, e, exc_info=True,
            )
        if applied is not None:
            row = self.repo.get_monthly(year, month) or row

        return self._to_result(row)

    def set_osb_unit_price(
        self,
        year: int,
        month: int,
        unit_price_try: Any,
        entered_by: str,
    ) -> MonthlyBillingResult:
        """
        Neden: Bir önceki ayın gerçek OSB faturasından okunan birim fiyatı girer,
        kesintiyi hesaplar ve ayı kilitler. Kilitli ayda BillingLockedError fırlar
        (düzeltme için override akışı gerekir — ADR-0002'de kapsam dışı).
        """
        price = _to_decimal(unit_price_try, "osb_unit_price_try")
        if price <= 0:
            raise BillingValidationError(f"OSB birim fiyatı pozitif olmalıdır: {price}")
        if not str(entered_by).strip():
            raise BillingValidationError("entered_by boş olamaz (denetim izi zorunlu).")

        existing = self.repo.get_monthly(year, month)
        deduction_try: Optional[Decimal] = None
        if existing:
            production = existing.get("production_kwh_snapshot")
            excess = existing.get("excess_sale_kwh_snapshot")
            if production is not None and excess is not None:
                deduction_try = _money((production - excess) * price)
            else:
                # Neden: kWh snapshot'ı yoksa (tutarsız veri) tutar üretilemez; ay
                # kilitlenir ama kesinti bir sonraki hesapta türetilir.
                logger.warning(
                    "%04d-%02d kWh snapshot'ı yok; OSB kesintisi şimdilik hesaplanamadı.",
                    year, month,
                )

        row = self.repo.set_osb_price(
            year=year,
            month=month,
            unit_price_try=price,
            entered_by=str(entered_by).strip(),
            osb_deduction_try=deduction_try,
        )
        return self._to_result(row)

    # ------------------------------------------------------------------
    # Fatura elektrik birim fiyatı — OSB katsayısının kaynağı
    # ------------------------------------------------------------------
    @staticmethod
    def next_month(year: int, month: int) -> tuple:
        """
        Neden: N faturası → N+1 katsayısı kuralının TEK uygulandığı yer. Ay kaydırması
        bu işin en tehlikeli hata sınıfı; aritmetik tek noktada tutulur ve Aralık→Ocak
        yıl dönümü tek yerde doğrulanır.
        """
        return (year + 1, 1) if month == 12 else (year, month + 1)

    def set_electricity_price(self, source_year: int, source_month: int,
                              unit_price_try: Any, created_by: str,
                              note: Optional[str] = None) -> Dict[str, Any]:
        """
        Neden: Kullanıcı OSB katsayısını değil, elindeki faturadaki elektrik birim
        fiyatını girer; hedef ayın katsayısı bundan türetilir (dönüşüm YOK, değer
        aynen aktarılır).

        Hedef ayın durumuna göre üç yol:
        - Hedef satır yok        -> BEKLIYOR (compute() kancası hazır olduğunda uygular)
        - Hedef var, kilitsiz    -> hemen uygulanır, ay kilitlenir
        - Hedef KİLİTLİ + değer değişti -> DUZELTME_BEKLIYOR; monthly_billing'e
          DOKUNULMAZ. Kilitli ayın tutarı şifre + gerekçe olmadan değişmemeli —
          override akışının üç koruması (şifre, 15 karakter gerekçe, denetim kaydı)
          otomatik bir zincirlemeyle baypas edilemez.
        """
        price = _to_decimal(unit_price_try, "unit_price_try")
        if price <= 0:
            raise BillingValidationError(f"Birim fiyat pozitif olmalıdır: {price}")
        if not 1 <= int(source_month) <= 12:
            raise BillingValidationError(f"Geçersiz ay: {source_month}")
        if not str(created_by).strip():
            raise BillingValidationError("created_by boş olamaz (denetim izi zorunlu).")

        target_year, target_month = self.next_month(int(source_year), int(source_month))
        existing_target = self.repo.get_monthly(target_year, target_month)

        status = PRICE_STATUS_PENDING
        if existing_target is not None and existing_target.get("status") == STATUS_LOCKED:
            current = existing_target.get("osb_unit_price_try")
            # Neden: Aynı değer yeniden girildiyse ortada düzeltilecek bir şey yok;
            # gereksiz "onay bekliyor" uyarısı üretmek kullanıcıyı köreltir.
            status = (PRICE_STATUS_APPLIED if current is not None and
                      Decimal(str(current)) == price else PRICE_STATUS_CORRECTION_PENDING)

        saved = self.repo.upsert_electricity_price(
            source_year=int(source_year), source_month=int(source_month),
            unit_price_try=price, target_year=target_year, target_month=target_month,
            created_by=str(created_by).strip(), note=note, status=status,
        )

        # Hedef hazır ve kilitsizse hemen uygula (bekletmeye gerek yok).
        if existing_target is not None and existing_target.get("status") != STATUS_LOCKED:
            self.apply_pending_electricity_price(target_year, target_month,
                                                 applied_by=str(created_by).strip())
            saved = self.repo.get_electricity_price_for_target(target_year, target_month)

        logger.info(
            "Fatura elektrik birim fiyatı kaydedildi: %04d-%02d = %s TL/kWh -> hedef "
            "%04d-%02d (durum: %s)",
            source_year, source_month, price, target_year, target_month, saved["status"],
        )
        return saved

    def apply_pending_electricity_price(self, year: int, month: int,
                                        applied_by: str = "otomatik") -> Optional[Dict[str, Any]]:
        """
        Neden: compute() kancası — bir ayın monthly_billing satırı OLUŞTUĞU anda,
        o aya beslenmeyi bekleyen kaynak varsa otomatik uygular.

        Kanca compute()'ta, MonthlySettlementJob'da DEĞİL: 2026-08-03'te Mayıs'ın
        satırı job ile değil izole bir script ile oluşturuldu; kanca job'da olsaydı
        kuyruk sessizce atlanırdı. compute() satır yazan tek boğaz.

        İdempotan: ayın osb_unit_price_try'ı doluysa hiç girmez.
        Uygulama ayı KİLİTLER (set_osb_unit_price'ın davranışı) — otomasyonun amacı bu.
        """
        source = self.repo.get_electricity_price_for_target(year, month)
        if source is None or source["status"] != PRICE_STATUS_PENDING:
            return None

        target = self.repo.get_monthly(year, month)
        if target is None or target.get("osb_unit_price_try") is not None:
            return None

        self.set_osb_unit_price(
            year=year, month=month,
            unit_price_try=source["unit_price_try"],
            entered_by=f"{applied_by} ({source['source_year']}-{source['source_month']:02d} faturası)",
        )
        updated = self.repo.mark_electricity_price_status(
            source["source_year"], source["source_month"],
            PRICE_STATUS_APPLIED, applied_by=applied_by,
        )
        logger.info(
            "%04d-%02d OSB katsayısı %04d-%02d faturasından OTOMATİK uygulandı: %s TL/kWh",
            year, month, source["source_year"], source["source_month"],
            source["unit_price_try"],
        )
        return updated

    def list_electricity_prices(self, limit: int = 24) -> List[Dict[str, Any]]:
        return self.repo.list_electricity_prices(limit=limit)

    def get_own_electricity_price(self, year: int, month: int) -> Optional[Decimal]:
        """
        Neden: Bir ayın KENDİ faturasındaki elektrik birim fiyatı — o ayın OSB
        katsayısı (osb_unit_price_try) DEĞİLDİR. Katsayı bir ÖNCEKİ ayın fiyatıdır;
        ayın kendi fiyatı ise bir SONRAKİ aya beslenen değerdir. İki kavram bugüne
        kadar Excel'de aynı satırda gösteriliyordu ve hangi fiyatın hangi aya ait
        olduğu bulanıktı.

        Okuma önceliği:
        1. monthly_billing[M+1].osb_unit_price_try — GERÇEKTE uygulanan değer.
           Kilitli ay override ile düzeltilmişse doğru olan budur; kaynak kütüğü
           düzeltmeyi taşımayabilir (DUZELTME_BEKLIYOR akışı).
        2. monthly_electricity_price(kaynak=M) — hedef ayın satırı henüz yoksa
           (mahsuplaşma hesaplanmadıysa) girilmiş kaynak değer.
        Hiçbiri yoksa None; çağıran taraf bunu "Bekleniyor" gösterir, 0 değil.

        Ay aritmetiği next_month() ile — ikinci bir "+1 ay" yolu açılmaz.
        """
        target_year, target_month = self.next_month(int(year), int(month))

        applied = self.repo.get_monthly(target_year, target_month)
        if applied is not None and applied.get("osb_unit_price_try") is not None:
            return _to_decimal(applied["osb_unit_price_try"], "osb_unit_price_try")

        source = self.repo.get_electricity_price_for_target(target_year, target_month)
        if source is not None and source.get("unit_price_try") is not None:
            return _to_decimal(source["unit_price_try"], "unit_price_try")

        logger.info(
            "%04d-%02d ayının kendi elektrik birim fiyatı henüz bilinmiyor "
            "(hedef ay %04d-%02d); önizleme hesaplanamayacak.",
            year, month, target_year, target_month,
        )
        return None

    def get_preview_deduction(self, year: int, month: int) -> Optional[Decimal]:
        """
        Neden: "Gelecek ay için önizleme" — ayın OSB'ye kalan kWh'i, ayın KENDİ
        elektrik fiyatıyla çarpılmış hali. SALT GÖSTERİMDİR:

        - Veritabanına YAZILMAZ, monthly_billing'e dokunmaz.
        - Resmi kesintiyi (osb_deduction_try) DEĞİŞTİRMEZ; resmi tutar bir önceki
          ayın fiyatıyla hesaplanır ve doğru olan odur (ADR-0002 §4).

        Amaç, fiyat gecikmesinin tutarı ne kadar kaydırdığını raporu okuyan kişinin
        önceden görmesi. kWh snapshot'ı veya ayın kendi fiyatı yoksa None döner —
        uydurulmuş bir sayı ile "önizleme yok" birbirine karışmamalı.
        """
        row = self.repo.get_monthly(int(year), int(month))
        if row is None:
            return None

        production = row.get("production_kwh_snapshot")
        excess = row.get("excess_sale_kwh_snapshot")
        price = self.get_own_electricity_price(year, month)
        if production is None or excess is None or price is None:
            return None

        # Neden: Resmi kesintiyle AYNI formül ve aynı yuvarlama; yalnızca fiyat
        # farklı. İki tutarın karşılaştırılabilir olması bu satıra bağlı.
        return _money((_to_decimal(production, "production_kwh_snapshot")
                       - _to_decimal(excess, "excess_sale_kwh_snapshot")) * price)

    # Neden: Gerekçe zorunlu VE anlamlı olmalı. Yalnızca "boş olamaz" denseydi "x" veya
    # "düzeltme" gibi kayıtlar denetim izini doldurur ama hiçbir soruyu cevaplamazdı;
    # override'ın tek koruması bu metin.
    MIN_OVERRIDE_REASON_LENGTH = 15

    def override_locked_month(
        self,
        year: int,
        month: int,
        reason: str,
        changed_by: str,
        osb_unit_price_try: Any = None,
        excess_sale_rate_try: Any = None,
    ) -> Dict[str, Any]:
        """
        Neden: Kilitli bir ayın katsayısını düzeltir (ADR-0002'de kapsam dışıydı).
        Kilidin kendisi kalkmaz — bu, gerekçesi ve deneticisi olan tek kaçış kapısıdır.

        Akış: kilidi delerek yaz -> MEVCUT compute() ile tutarları yeniden türet.
        compute() snapshot doluyken gelen katsayıyı yok saydığı için, override'ı ÖNCE
        yazmak yeni değeri korur ve tutarlar ondan hesaplanır; ikinci bir matematik
        yolu doğmaz.

        Dönüş: eski/yeni değerleri ve yeniden hesaplanmış tutarları içeren sözlük
        (çağıran taraf audit kaydını bundan üretir).
        """
        reason = str(reason or "").strip()
        if len(reason) < self.MIN_OVERRIDE_REASON_LENGTH:
            raise BillingValidationError(
                f"Düzeltme gerekçesi en az {self.MIN_OVERRIDE_REASON_LENGTH} karakter "
                f"olmalıdır (verilen: {len(reason)}). Gerekçe, denetimde 'neden "
                f"değiştirildi' sorusunun tek cevabıdır."
            )
        if not str(changed_by).strip():
            raise BillingValidationError("changed_by boş olamaz (denetim izi zorunlu).")

        osb = _to_decimal(osb_unit_price_try, "osb_unit_price_try") \
            if osb_unit_price_try is not None else None
        rate = _to_decimal(excess_sale_rate_try, "excess_sale_rate_try") \
            if excess_sale_rate_try is not None else None
        for label, value in (("osb_unit_price_try", osb), ("excess_sale_rate_try", rate)):
            if value is not None and value <= 0:
                raise BillingValidationError(f"{label} pozitif olmalıdır: {value}")

        before = self.repo.override_locked_month(
            year=year, month=month,
            osb_unit_price_try=osb, excess_sale_rate_try=rate,
        )

        # Neden: kWh snapshot'ları değişmiyor; tutarlar yeni katsayıyla yeniden türetilsin
        # diye compute() aynı girdilerle çağrılır. Snapshot yoksa (tutarsız veri) compute
        # zaten tutar üretmez ve ayı olduğu gibi bırakır (ADR-0002 §7).
        production = before.get("production_kwh_snapshot") or Decimal("0")
        excess = before.get("excess_sale_kwh_snapshot") or Decimal("0")
        after = self.compute(year=year, month=month,
                             production_kwh=production, excess_sale_kwh=excess)

        kind = "osb_unit_price_try" if osb is not None else "excess_sale_rate_try"

        # Neden: Zincirin kapanışı. Kaynak fatura fiyatı düzeltilip hedef ay kilitli
        # olduğu için DUZELTME_BEKLIYOR'da kalmıştı; kullanıcı override'ı onayladıysa
        # ve uygulanan değer kaynakla aynıysa kaynak UYGULANDI'ya döner. Değer farklıysa
        # (kullanıcı başka bir sayı yazdıysa) kaynak beklemede KALIR — ekranda tutarsızlık
        # görünmeye devam etmeli, sessizce "tamam" denmemeli.
        if osb is not None:
            try:
                source = self.repo.get_electricity_price_for_target(year, month)
                if source and source["status"] == PRICE_STATUS_CORRECTION_PENDING \
                        and Decimal(str(source["unit_price_try"])) == osb:
                    self.repo.mark_electricity_price_status(
                        source["source_year"], source["source_month"],
                        PRICE_STATUS_APPLIED, applied_by=changed_by,
                    )
            except Exception as e:
                logger.error("Kaynak fatura kaydı güncellenemedi (best-effort): %s", e)

        logger.warning(
            "%04d-%02d OVERRIDE (%s) uygulandı — gerekçe: %s (yapan: %s)",
            year, month, kind, reason, changed_by,
        )
        return {
            "year": year,
            "month": month,
            "kind": kind,
            "reason": reason,
            "changed_by": changed_by,
            "old_value": str(before[f"_previous_{kind}"]) if before[f"_previous_{kind}"] is not None else None,
            "new_value": str(osb if osb is not None else rate),
            "previous_rate_id": before["_previous_excess_sale_rate_id"],
            "old_invoice_try": str(before["_previous_excess_sale_invoice_try"])
            if before["_previous_excess_sale_invoice_try"] is not None else None,
            "new_invoice_try": str(after.excess_sale_invoice_try)
            if after.excess_sale_invoice_try is not None else None,
            "old_deduction_try": str(before["_previous_osb_deduction_try"])
            if before["_previous_osb_deduction_try"] is not None else None,
            "new_deduction_try": str(after.osb_deduction_try)
            if after.osb_deduction_try is not None else None,
            "result": after,
        }

    def get_monthly(self, year: int, month: int) -> Optional[MonthlyBillingResult]:
        row = self.repo.get_monthly(year, month)
        return self._to_result(row) if row else None

    def list_pending_months(self, limit: int = 24) -> List[MonthlyBillingResult]:
        """
        Neden: OSB birim fiyatı bekleyen aylar (dashboard banner'ı). En yeni başta.
        Tümü döner; kaç tanesinin gösterileceğine sunum katmanı karar verir.
        """
        return [self._to_result(r) for r in self.repo.list_pending_months(limit=limit)]

    def list_months(self, limit: int = 24) -> List[MonthlyBillingResult]:
        """
        Neden: OSB birim fiyatının geçmişi hiçbir ekranda görünmüyordu — giriş yalnızca
        bekleyen ay varken banner'dan açılan modaldan yapılabiliyor, girildikten sonra
        "hangi aya hangi fiyat, kim, ne zaman girdi" sorusunun cevabı kayboluyordu.
        Enerjisa katsayısının append-only geçmiş tablosu vardı, OSB'nin karşılığı yoktu.

        Bekleyen ve kilitli TÜM ayları en yeniden eskiye döner (salt-okunur).
        """
        return [self._to_result(r) for r in self.repo.list_months(limit=limit)]

    @staticmethod
    def _to_result(row: Dict[str, Any]) -> MonthlyBillingResult:
        return MonthlyBillingResult(
            year=row["year"],
            month=row["month"],
            status=row.get("status") or STATUS_PENDING_RATE,
            excess_sale_rate_try=row.get("excess_sale_rate_try"),
            osb_unit_price_try=row.get("osb_unit_price_try"),
            production_kwh=row.get("production_kwh_snapshot"),
            excess_sale_kwh=row.get("excess_sale_kwh_snapshot"),
            excess_sale_invoice_try=row.get("excess_sale_invoice_try"),
            osb_deduction_try=row.get("osb_deduction_try"),
            locked_at=row.get("locked_at"),
            osb_price_entered_by=row.get("osb_price_entered_by"),
            osb_price_entered_at=row.get("osb_price_entered_at"),
        )


__all__ = ["BillingService", "STATUS_LOCKED", "STATUS_PENDING_RATE"]
