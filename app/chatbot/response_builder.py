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

        return (
            f"📅 {label} mahsuplaşma özeti:\n"
            f"• Toplam Üretim: {prod_val} kWh\n"
            f"• Toplam Tüketim: {cons_val} kWh\n"
            f"• Mahsup Edilen: {settled_val} kWh\n"
            f"• Şebekeden Çekiş: {import_val} kWh\n"
            f"• Fazla Satış: {export_val} kWh"
        )

    def _unrecognized_response(self) -> str:
        return (
            "🤔 Bu soruyu anlayamadım. Şunları sorabilirsiniz:\n"
            "• 'Dün üretim ne kadar?'\n"
            "• 'Bu ay mahsup özeti'\n"
            "• 'En çok üretim hangi günde?'\n"
            "• 'Santral durumu nasıl?'"
        )
