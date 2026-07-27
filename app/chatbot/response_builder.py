import re
from datetime import datetime

class ResponseBuilder:

    METRIC_LABELS = {
        "production": "üretim",
        "consumption": "tüketim",
        "settled": "mahsup edilen",
        "grid_import": "şebekeden çekiş",
        "grid_export": "fazla satış"
    }

    # Neden: Faturalama metrikleri kWh değil TL döndürür ve yalnızca aylık dönemde
    # anlamlıdır (ADR-0002). Ayrı bir sözlükte tutulur ki kWh cevap şablonları
    # yanlışlıkla "TL" değerine "kWh" birimi yazmasın.
    BILLING_LABELS = {
        "excess_sale_invoice": "fazla satış faturası",
        "osb_deduction": "OSB kesintisi",
    }

    def _fmt_try(self, val) -> str:
        """Neden: Türkçe para biçimi — 11250 -> '11.250,00'."""
        try:
            return f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(val)

    def _billing_answer(self, metric: str, period: str, label: str, data: dict) -> str:
        """
        Neden: TL sorularının tek cevap noktası. Üç durum ayrılır ve hiçbirinde
        sayı uydurulmaz:
          1. Aylık olmayan dönem  -> TL yok, kullanıcıya ay sorması söylenir
          2. Kayıt/değer yok      -> "birim fiyat girilmedi", 0 TL DENMEZ
          3. Değer var            -> tutar + KDV hariç notu
        """
        metric_label = self.BILLING_LABELS[metric]

        if period != "month":
            # Neden: capitalize() kullanılmaz — "OSB kesintisi"ni "Osb kesintisi"
            # yapıyordu. Etiket cümle başına konmaz.
            return (
                f"📌 Bu tutar ({metric_label}) yalnızca aylık dönem için hesaplanır "
                f"(günlük raporda TL yer almaz).\n"
                f"Örneğin: *bu ay {metric_label}* veya *geçen ay {metric_label}*"
            )

        if metric not in data:
            return (
                f"⚠️ {label} dönemi için faturalama kaydı bulunamadı. "
                f"Bu aya ait aylık mahsuplaşma raporu henüz hazırlanmamış olabilir."
            )

        value = data.get(metric)
        if value is None:
            if metric == "osb_deduction":
                return (
                    f"⏳ {label} dönemi için OSB kesintisi henüz hesaplanmadı — "
                    f"OSB birim fiyatı girilmemiş.\n"
                    f"Dashboard'daki uyarı bandından birim fiyatı girebilirsiniz."
                )
            return (
                f"⏳ {label} dönemi için {metric_label} henüz hesaplanmadı — "
                f"fazla satış katsayısı tanımlı değil.\n"
                f"Sistem Ayarları → Faturalama Katsayısı bölümünden tanımlayabilirsiniz."
            )

        return (
            f"💵 {label} dönemi {metric_label}: {self._fmt_try(value)} TL "
            f"(KDV hariç)"
        )

    def _fmt(self, val) -> str:
        if val is None or val == "":
            return "0"
        try:
            val = float(val)
            if val.is_integer():
                return f"{int(val):,}".replace(",", ".")
            else:
                parts = f"{val:.1f}".split(".")
                integer_part = f"{int(parts[0]):,}".replace(",", ".")
                return f"{integer_part},{parts[1]}"
        except Exception:
            return str(val)

    def _fmt_date_tr(self, date_str: str) -> str:
        # date_str: "2026-05-15" -> "15 Mayıs 2026"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            months = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
            return f"{dt.day} {months[dt.month]} {dt.year}"
        except Exception:
            return date_str

    def build(self, question: str, date_info: dict, metric_info: dict, data: dict) -> str:
        """
        Soruya ve verilere göre doğal Türkçe cevap üretir.
        """
        if not date_info or not metric_info:
            return self._unrecognized_response()

        if not data:
            label = date_info.get("label", "")
            return f"⚠️ {label} tarihine/dönemine ait mahsuplaşma verisi bulunamadı."

        metrics = metric_info.get("metrics", [])
        period = date_info.get("type", "day")
        comparison = metric_info.get("comparison")
        label = date_info.get("label", "")

        # 1. SANTRAL DURUMU CEVABI
        if "plant_status" in metrics:
            plants = data.get("plants", [])
            anomaly_count = data.get("anomaly_count", 0)
            last_check = data.get("last_check", "-")
            
            if not plants:
                return "ℹ️ Sistemde kayıtlı santral bilgisi bulunamadı."
                
            if anomaly_count == 0:
                return f"✅ Tüm santraller normal çalışıyor.\nSon kontrol: {last_check}"
            else:
                plant_lines = []
                for p in plants:
                    if p["status"] != "Normal":
                        plant_lines.append(f"• {p['name']}: {p['status']}")
                plant_list_str = "\n".join(plant_lines)
                return f"⚠️ {anomaly_count} santralde sorun tespit edildi!\n{plant_list_str}\nSon kontrol: {last_check}"

        # 2. EN İYİ / EN KÖTÜ GÜN CEVABI
        if comparison:
            metric = data.get("metric", "production")
            metric_label = self.METRIC_LABELS.get(metric, "üretim")
            val_str = self._fmt(data.get("value", 0))
            day_name = data.get("day_name", "")
            date_tr = self._fmt_date_tr(data.get("date", ""))
            
            if comparison == "best":
                return f"🏆 Son 3 ayın en yüksek {metric_label} günü {date_tr} ({day_name}) — {val_str} kWh"
            else:
                return f"📉 Son 3 ayın en düşük {metric_label} günü {date_tr} ({day_name}) — {val_str} kWh"

        # 3a. FATURALAMA (TL) SORGUSU
        # Neden: kWh şablonlarından ÖNCE ele alınır — "fazla satış faturası" ifadesi
        # hem grid_export hem excess_sale_invoice metriğini tetikler; kullanıcı
        # "fatura" dediyse TL istiyordur, kWh değil.
        billing_asked = [m for m in metrics if m in self.BILLING_LABELS]
        if billing_asked and len(metrics) <= 2:
            return self._billing_answer(billing_asked[0], period, label, data)

        # 3. TEK BİR METRİK SORGUSU CEVABI
        # Eğer sadece tek bir metrik sorulduysa (örn: "dün üretim ne kadar")
        if len(metrics) == 1 and metrics[0] in self.METRIC_LABELS:
            metric = metrics[0]
            metric_label = self.METRIC_LABELS[metric]
            val_str = self._fmt(data.get(metric, 0))
            
            if period == "day":
                return f"📊 {label} tarihinde toplam {metric_label} {val_str} kWh olarak gerçekleşti."
            else:
                return f"📊 {label} döneminde toplam {metric_label} {val_str} kWh olarak gerçekleşti."

        # 4. GENEL MAHSUPLAŞMA ÖZETİ CEVABI
        # Çoklu metrik veya genel özet
        prod_val = self._fmt(data.get("production", 0))
        cons_val = self._fmt(data.get("consumption", 0))
        settled_val = self._fmt(data.get("settled", 0))
        import_val = self._fmt(data.get("grid_import", 0))
        export_val = self._fmt(data.get("grid_export", 0))

        summary = (
            f"📅 {label} mahsuplaşma özeti:\n"
            f"• Toplam Üretim: {prod_val} kWh\n"
            f"• Toplam Tüketim: {cons_val} kWh\n"
            f"• Mahsup Edilen: {settled_val} kWh\n"
            f"• Şebekeden Çekiş: {import_val} kWh\n"
            f"• Fazla Satış: {export_val} kWh"
        )

        # Neden: TL satırları yalnızca aylık özette ve faturalama kaydı varsa eklenir.
        # Hesaplanmamış tutar "Bekleniyor" yazar — 0 TL olarak gösterilmez.
        if period == "month" and ("excess_sale_invoice" in data or "osb_deduction" in data):
            def _tl(key):
                val = data.get(key)
                return f"{self._fmt_try(val)} TL" if val is not None else "Bekleniyor"

            summary += (
                f"\n\n💵 Faturalama (KDV hariç):\n"
                f"• Fazla Satış Faturası: {_tl('excess_sale_invoice')}\n"
                f"• OSB Kesintisi: {_tl('osb_deduction')}"
            )

        return summary

    # ------------------------------------------------------------------
    # Yönlendirme cevapları (veri sorgusu olmayan durumlar)
    # ------------------------------------------------------------------
    EXAMPLES = (
        "• *Dün üretim ne kadar?*\n"
        "• *Bu ay mahsup özeti*\n"
        "• *Geçen ay tüketim*\n"
        "• *En çok üretim hangi günde?*\n"
        "• *Bu ay OSB kesintisi ne kadar?*\n"
        "• *Santral durumu nasıl?*"
    )

    def greeting(self) -> str:
        return (
            "Merhaba! 👋 GES verileriniz hakkında size yardımcı olabilirim — "
            "üretim, tüketim ve mahsuplaşma rakamlarınızı sorabilirsiniz.\n\n"
            "Örneğin:\n" + self.EXAMPLES
        )

    def help_menu(self) -> str:
        return (
            "🧭 Şunları sorabilirsiniz:\n\n"
            "*Dönem seçin:* dün, bugün, bu hafta, geçen hafta, bu ay, geçen ay, "
            "son 7 gün, son 30 gün, mayıs 2026 gibi.\n"
            "*Kalem seçin:* üretim, tüketim, mahsup, şebekeden çekiş, fazla satış "
            "veya genel özet.\n"
            "*Faturalama (yalnızca aylık, KDV hariç):* fazla satış faturası, OSB kesintisi.\n"
            "*Diğer:* santral durumu, en çok/en az üretim günü.\n\n"
            "Örnekler:\n" + self.EXAMPLES
        )

    def comparison_guidance(self) -> str:
        return (
            "Şu an iki değeri doğrudan kıyaslayamıyorum, ama her birini ayrı ayrı "
            "gösterebilirim. Örneğin:\n"
            "• *Bu ay üretim*\n"
            "• *Bu ay tüketim*\n\n"
            "Aradaki farkı bu iki sonuçtan görebilirsiniz. En yüksek/en düşük günü "
            "sormak isterseniz: *En çok üretim hangi günde?*"
        )

    def _unrecognized_response(self) -> str:
        return (
            "🤔 Bu soruyu tam anlayamadım. Bir dönem ve bir kalem belirtmeyi deneyin.\n\n"
            "Örneğin:\n" + self.EXAMPLES
        )
