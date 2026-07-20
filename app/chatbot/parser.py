import re
from datetime import datetime, date, timedelta


class DateParser:
    """
    Türkçe doğal dil tarih parser sınıfı.
    Eşleşme bulunamazsa None döner (çağıran taraf yönlendirme yapabilir);
    eskiden sessizce "dün"e düşüyordu.
    """

    TURKISH_NUMBERS = {
        "bir": 1, "tek": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5,
        "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10
    }

    TURKISH_MONTHS = {
        "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
        "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12
    }

    TURKISH_WEEKDAYS = {
        "pazartesi": 0, "salı": 1, "çarşamba": 2, "perşembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6
    }

    def __init__(self, reference_date: date = None):
        self.today = reference_date if reference_date is not None else date.today()

    def _parse_turkish_number(self, text: str) -> int:
        text = text.lower().strip()
        if text.isdigit():
            return int(text)
        return self.TURKISH_NUMBERS.get(text, 1)

    def _day(self, d: date, label: str) -> dict:
        return {"type": "day", "date": d.isoformat(), "label": label}

    def yesterday(self) -> dict:
        """Neden: Metrik belirtilmiş ama tarih belirtilmemiş sorgularda makul varsayılan."""
        d = self.today - timedelta(days=1)
        return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

    def parse(self, text: str):
        text = text.lower().strip()

        # Gelecek zaman kontrolü (Yarın reddedilir)
        if "yarın" in text or "gelecek" in text:
            raise ValueError("Gelecek tarihli sorgular desteklenmemektedir.")

        # 1. BUGÜN
        if re.search(r"\bbugün\w*\b|\bbu gün\b", text):
            d = self.today
            return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

        # 1b. DÜN
        if re.search(r"\bdün\w*\b", text):
            d = self.today - timedelta(days=1)
            return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

        # 1c. ÖNCEKİ / EVVELKİ GÜN (2 gün önce)
        if re.search(r"\b(önceki|evvelki|evvelsi)\s+gün\b", text):
            d = self.today - timedelta(days=2)
            return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

        # 2. X GÜN ÖNCE
        day_ago_match = re.search(r"(\d+|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)\s+gün\s+önce", text)
        if day_ago_match:
            n = self._parse_turkish_number(day_ago_match.group(1))
            d = self.today - timedelta(days=n)
            return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

        # 3. GEÇEN / ÖNCEKİ HAFTA ("haftaki" eki dahil)
        if re.search(r"\b(geçen|önceki|evvelki)\s+hafta(ki)?\b", text):
            monday = self.today - timedelta(days=self.today.weekday())
            date_from = monday - timedelta(days=7)
            date_to = date_from + timedelta(days=6)
            return {
                "type": "week", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "label": f"Geçen Hafta ({date_from.day} {self._get_month_name(date_from.month)} - {date_to.day} {self._get_month_name(date_to.month)} {date_to.year})"
            }

        if re.search(r"\bbu hafta(ki)?\b", text):
            monday = self.today - timedelta(days=self.today.weekday())
            date_from = monday
            date_to = self.today
            return {
                "type": "week", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "label": f"Bu Hafta ({date_from.day} {self._get_month_name(date_from.month)} - {date_to.day} {self._get_month_name(date_to.month)} {date_to.year})"
            }

        # X HAFTA ÖNCE
        week_ago_match = re.search(r"(\d+|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)\s+hafta\s+önce", text)
        if week_ago_match:
            n = self._parse_turkish_number(week_ago_match.group(1))
            monday = self.today - timedelta(days=self.today.weekday())
            date_from = monday - timedelta(days=7 * n)
            date_to = date_from + timedelta(days=6)
            return {
                "type": "week", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "label": f"{n} Hafta Önce ({date_from.day} {self._get_month_name(date_from.month)} - {date_to.day} {self._get_month_name(date_to.month)} {date_to.year})"
            }

        # 4. GEÇEN HAFTA PAZARTESİ / CUMA (ve diğer günler)
        last_week_day_match = re.search(r"geçen\s+hafta\s+(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar)", text)
        if last_week_day_match:
            day_name = last_week_day_match.group(1)
            target_weekday = self.TURKISH_WEEKDAYS[day_name]
            monday = self.today - timedelta(days=self.today.weekday())
            last_monday = monday - timedelta(days=7)
            d = last_monday + timedelta(days=target_weekday)
            return self._day(d, f"Geçen Hafta {day_name.capitalize()} ({d.day} {self._get_month_name(d.month)} {d.year})")

        # GEÇEN / SON PAZARTESİ / SALI...
        last_day_match = re.search(r"(geçen|son)\s+(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar)", text)
        if last_day_match:
            day_name = last_day_match.group(2)
            target_weekday = self.TURKISH_WEEKDAYS[day_name]
            ref_weekday = self.today.weekday()
            diff = ref_weekday - target_weekday
            if diff <= 0:
                diff += 7
            d = self.today - timedelta(days=diff)
            return self._day(d, f"Geçen {day_name.capitalize()} ({d.day} {self._get_month_name(d.month)} {d.year})")

        # BU HAFTANIN PAZARTESİ / SALI...
        this_week_day_match = re.search(r"bu\s+haftanın\s+(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar)", text)
        if this_week_day_match:
            day_name = this_week_day_match.group(1)
            target_weekday = self.TURKISH_WEEKDAYS[day_name]
            monday = self.today - timedelta(days=self.today.weekday())
            d = monday + timedelta(days=target_weekday)
            return self._day(d, f"Bu Haftanın {day_name.capitalize()} Günü ({d.day} {self._get_month_name(d.month)} {d.year})")

        # 5. GEÇEN / ÖNCEKİ AY ("ayki", "ayın" ekleri dahil)
        if re.search(r"\b(geçen|önceki|evvelki)\s+ay(ki|ın|a)?\b", text):
            first_day_this_month = self.today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            return {
                "type": "month", "date_from": first_day_last_month.isoformat(), "date_to": last_day_last_month.isoformat(),
                "label": f"Geçen Ay ({self._get_month_name(first_day_last_month.month)} {first_day_last_month.year})"
            }

        # GEÇEN AYIN BAŞI / SONU (aydan önce kontrol edilmeli)
        if re.search(r"geçen\s+ayın\s+başı", text):
            first_day_this_month = self.today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            return self._day(first_day_last_month, f"Geçen Ayın Başı (1 {self._get_month_name(first_day_last_month.month)} {first_day_last_month.year})")

        if re.search(r"geçen\s+ayın\s+sonu", text):
            first_day_this_month = self.today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            return self._day(last_day_last_month, f"Geçen Ayın Sonu ({last_day_last_month.day} {self._get_month_name(last_day_last_month.month)} {last_day_last_month.year})")

        # BU AY ("ayki", "ayın", "aya ait" ekleri dahil)
        if re.search(r"\bbu ay(ki|ın|a|ının)?\b", text):
            first_day = self.today.replace(day=1)
            return {
                "type": "month", "date_from": first_day.isoformat(), "date_to": self.today.isoformat(),
                "label": f"Bu Ay ({self._get_month_name(first_day.month)} {first_day.year})"
            }

        # X AY ÖNCE
        month_ago_match = re.search(r"(\d+|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)\s+ay\s+önce", text)
        if month_ago_match:
            n = self._parse_turkish_number(month_ago_match.group(1))
            target_date = self.today
            for _ in range(n):
                target_date = target_date.replace(day=1) - timedelta(days=1)
            first_day = target_date.replace(day=1)
            last_day = target_date
            return {
                "type": "month", "date_from": first_day.isoformat(), "date_to": last_day.isoformat(),
                "label": f"{n} Ay Önce ({self._get_month_name(first_day.month)} {first_day.year})"
            }

        # 6. DÖNEM: SON X GÜN / SON X HAFTA / SON X AY
        last_days_match = re.search(r"son\s+(\d+|yedi|otuz)\s+gün", text)
        if last_days_match:
            n_str = last_days_match.group(1)
            n = 7 if n_str == "yedi" else (30 if n_str == "otuz" else int(n_str))
            date_from = self.today - timedelta(days=n)
            date_to = self.today - timedelta(days=1)
            return {
                "type": "range", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "label": f"Son {n} Gün"
            }

        last_weeks_match = re.search(r"son\s+(\d+|iki|üç|dört)\s+hafta", text)
        if last_weeks_match:
            n = self._parse_turkish_number(last_weeks_match.group(1))
            date_from = self.today - timedelta(days=7 * n)
            date_to = self.today - timedelta(days=1)
            return {
                "type": "range", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "label": f"Son {n} Hafta"
            }

        last_months_match = re.search(r"son\s+(\d+|üç)\s+ay", text)
        if last_months_match:
            n_str = last_months_match.group(1)
            n = 3 if n_str == "üç" else int(n_str)
            target_date = self.today
            for _ in range(n - 1):
                target_date = target_date.replace(day=1) - timedelta(days=1)
            date_from = target_date.replace(day=1)
            return {
                "type": "range", "date_from": date_from.isoformat(), "date_to": self.today.isoformat(),
                "label": f"Son {n} Ay"
            }

        if re.search(r"\bbu yıl\b|\bbu sene\b|yılbaşından\s+beri", text):
            date_from = date(self.today.year, 1, 1)
            return {
                "type": "range", "date_from": date_from.isoformat(), "date_to": self.today.isoformat(),
                "label": f"Bu Yıl ({self.today.year})"
            }

        if re.search(r"\b(geçen|önceki|evvelki)\s+(yıl|sene)\b", text):
            date_from = date(self.today.year - 1, 1, 1)
            date_to = date(self.today.year - 1, 12, 31)
            return {
                "type": "range", "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "label": f"Geçen Yıl ({self.today.year - 1})"
            }

        # 7. AY İSİMLERİ & YIL (Örn: ocak 2026, mayıs 2025)
        for month_name, month_num in self.TURKISH_MONTHS.items():
            month_year_match = re.search(rf"\b{month_name}\w*\s+(\d{{4}})\b", text)
            if month_year_match:
                year = int(month_year_match.group(1))
                first_day = date(year, month_num, 1)
                last_day = self._get_last_day_of_month(first_day)
                return {
                    "type": "month", "date_from": first_day.isoformat(), "date_to": last_day.isoformat(),
                    "label": f"{month_name.capitalize()} {year}"
                }

        # Sadece Ay ismi (yıl yoksa) — "ocak", "ocakta", "ocak ayında", "5 ocak"
        for month_name, month_num in self.TURKISH_MONTHS.items():
            if re.search(rf"\b{month_name}[a-zçğıöşü]*\b", text):
                day_month_match = re.search(rf"(\d+)\s+{month_name}", text)
                if day_month_match:
                    day_num = int(day_month_match.group(1))
                    try:
                        d = date(self.today.year, month_num, day_num)
                        if d > self.today:
                            d = date(self.today.year - 1, month_num, day_num)
                    except ValueError:
                        d = date(self.today.year - 1, month_num, 1)
                    return self._day(d, f"{d.day} {month_name.capitalize()} {d.year}")

                year = self.today.year
                if month_num > self.today.month:
                    year -= 1
                first_day = date(year, month_num, 1)
                last_day = self._get_last_day_of_month(first_day)
                return {
                    "type": "month", "date_from": first_day.isoformat(), "date_to": last_day.isoformat(),
                    "label": f"{month_name.capitalize()} {year}"
                }

        # 8. DD.MM.YYYY veya YYYY-MM-DD formatında TARİH
        date_pattern1 = re.search(r"(\d{1,2})[.\/](\d{1,2})[.\/](\d{4})", text)
        if date_pattern1:
            day = int(date_pattern1.group(1))
            month = int(date_pattern1.group(2))
            year = int(date_pattern1.group(3))
            d = date(year, month, day)
            return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

        date_pattern2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if date_pattern2:
            year = int(date_pattern2.group(1))
            month = int(date_pattern2.group(2))
            day = int(date_pattern2.group(3))
            d = date(year, month, day)
            return self._day(d, f"{d.day} {self._get_month_name(d.month)} {d.year}")

        # Eşleşme yok → None (çağıran taraf yönlendirme yapar)
        return None

    def _get_month_name(self, month: int) -> str:
        names = {
            1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
            7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
        }
        return names.get(month, "")

    def _get_last_day_of_month(self, d: date) -> date:
        next_month = d.replace(day=28) + timedelta(days=4)
        return next_month - timedelta(days=next_month.day)


class MetricParser:
    """
    Türkçe doğal dil metrik parser sınıfı. Geniş eş anlamlı/ifade kapsamı.
    'explicit' bayrağı: metin gerçekten bir metrik/özet/santral sinyali içeriyor mu?
    """

    METRIC_KEYWORDS = {
        "production": ["üretim", "ürettik", "ürettiğimiz", "üretti", "üretilen", "üretim miktarı",
                       "solar üretim", "ges üretimi", "güneş üretimi", "panel üretimi",
                       "ne ürettik", "kaç kwh ürettik", "uretim"],
        "consumption": ["tüketim", "tükettik", "tükettiğimiz", "tüketilen", "tüketim miktarı",
                        "fabrika tüketimi", "enerji tüketimi", "ne harcadık", "ne kadar harcadık",
                        "ne kullandık", "kullandığımız", "tuketim"],
        "settled": ["mahsup", "mahsuplaşma", "mahsuplaştırma", "mahsup edilen", "mahsuplaşan",
                    "netleştirme", "mahsuplasmalarim"],
        "grid_import": ["şebekeden çekiş", "şebekeden aldık", "şebekeden çektik", "grid çekiş",
                        "dışarıdan aldık", "dışarıdan çektik", "şebeke alımı", "çekiş",
                        "sebekeden cekis", "cekis"],
        "grid_export": ["fazla satış", "şebekeye verdik", "şebekeye sattık", "ihraç",
                        "satış", "sattığımız", "fazla satis", "satis"],
    }

    SUMMARY_KEYWORDS = ["özet", "rapor", "nasıl gitti", "nasıl geçti", "ne oldu", "ne var",
                        "genel", "hepsi", "tümü", "tamamı", "bilanço", "sonuç", "sonuçlar",
                        "ozet", "durum raporu"]

    PLANT_KEYWORDS = ["santral", "ges durumu", "ges'ler", "arıza", "sorun var mı", "sorun",
                      "normal mi", "çalışıyor mu", "aktif mi", "panel durumu", "tesis durumu",
                      "ariza"]

    ALL_METRICS = ["production", "consumption", "settled", "grid_import", "grid_export"]

    def parse(self, text: str) -> dict:
        text = text.lower().strip()

        is_plant = any(x in text for x in self.PLANT_KEYWORDS)
        is_summary = any(x in text for x in self.SUMMARY_KEYWORDS)

        metrics = []
        for metric, keywords in self.METRIC_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                metrics.append(metric)

        explicit = bool(metrics) or is_plant or is_summary

        if is_plant:
            metrics = ["plant_status"]
        elif is_summary and not metrics:
            metrics = list(self.ALL_METRICS)
        elif not metrics:
            metrics = list(self.ALL_METRICS)

        aggregation = "sum"
        comparison = None

        if any(x in text for x in ["en çok", "en fazla", "en yüksek", "en iyi", "rekor", "zirve", "maksimum", "en verimli"]):
            aggregation = "max"
            comparison = "best"
        elif any(x in text for x in ["en az", "en düşük", "en kötü", "minimum", "en verimsiz"]):
            aggregation = "min"
            comparison = "worst"
        elif any(x in text for x in ["ortalama", "ortalaması", "vasati"]):
            aggregation = "avg"

        return {
            "metrics": metrics,
            "aggregation": aggregation,
            "comparison": comparison,
            "explicit": explicit,
        }


class IntentParser:
    """
    Neden: Kullanıcı mesajını üst düzey niyete göre sınıflandırıp, veri sorgusu
    olmayan durumlarda (selam, yardım, desteklenmeyen kıyas, tanınmayan) doğru
    yönlendirmeyi seçmek. Sessizce yanlış cevap üretmeyi engeller.
    """

    GREETINGS = ["merhabalar", "merhaba", "selamlar", "selamün aleyküm", "selam",
                 "günaydın", "iyi günler", "iyi akşamlar", "iyi geceler",
                 "nasılsın", "naber", "hey", "alo", "hello", "hi"]

    HELP = ["yardım", "ne sorabilirim", "neler sorabilirim", "ne yapabilirsin",
            "neler yapabilirsin", "nasıl kullan", "komut", "örnek", "menü",
            "ne biliyorsun", "ne işe yarıyorsun"]

    DIFF = ["arasındaki fark", "farkı", "fark ", "kıyasla", "kıyas", "karşılaştır",
            "karşılaştırma", " vs ", "versus"]

    BEST_WORST = ["en çok", "en az", "en fazla", "en yüksek", "en düşük", "en iyi", "en kötü"]

    DATE_SIGNAL = re.compile(
        r"\b(bugün|dün|gün|hafta|ay|yıl|sene|tarih|ocak|şubat|mart|nisan|mayıs|haziran|"
        r"temmuz|ağustos|eylül|ekim|kasım|aralık)\w*\b|"
        r"\d{1,2}[.\/]\d{1,2}[.\/]\d{4}|\d{4}-\d{2}-\d{2}"
    )

    def _has_metric_signal(self, text: str) -> bool:
        for kws in MetricParser.METRIC_KEYWORDS.values():
            if any(kw in text for kw in kws):
                return True
        return any(x in text for x in MetricParser.SUMMARY_KEYWORDS)

    def classify(self, text: str) -> dict:
        t = text.lower().strip()

        normalized = t.strip(" .!?,")
        has_metric = self._has_metric_signal(t)
        has_plant = any(x in t for x in MetricParser.PLANT_KEYWORDS)
        has_date = bool(self.DATE_SIGNAL.search(t))
        best_worst = any(x in t for x in self.BEST_WORST)
        is_diff = any(x in t for x in self.DIFF) and not best_worst

        # Tam selam ("günaydın", "iyi günler") tarih sinyaline takılsa da selamdır.
        is_pure_greeting = normalized in self.GREETINGS or (
            any(normalized.startswith(g) for g in self.GREETINGS)
            and not (has_metric or has_plant or has_date)
        )

        if is_pure_greeting:
            kind = "greeting"
        elif any(x in t for x in self.HELP) and not (has_metric or has_plant):
            kind = "help"
        elif is_diff:
            kind = "comparison_diff"
        elif has_metric or has_plant or has_date or best_worst:
            kind = "data"
        else:
            kind = "unknown"

        return {
            "kind": kind,
            "has_metric": has_metric,
            "has_plant": has_plant,
            "has_date": has_date,
        }
