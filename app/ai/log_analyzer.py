import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests


class LogAnalyzer:
    """
    Neden: Log kayıtlarını analiz ederek olası sebep ve çözüm önerileri üretmek.
    Önce yerel pattern eşleştirmesi dener (API maliyeti sıfır), sonra önbelleği
    kontrol eder, son çare olarak Gemini API'sini çağırır.
    """

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.project_id = os.environ.get("GEMINI_PROJECT_ID", "")
        self.location = os.environ.get("GEMINI_LOCATION", "us-central1")
        # Model seçimi — .env'den okunur; varsayılan: gemini-3.1-flash-lite
        self.model = os.getenv("GEMINI_MODEL_DEFAULT", "gemini-3.1-flash-lite")
        self.fallback_model = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-3.5-flash")

        # Önbellek: aynı hata tekrar gelince API'ye sorma
        self.cache_file = Path("config/log_analysis_cache.json")
        self.cache = self._load_cache()

    # ------------------------------------------------------------------
    # Önbellek yardımcıları
    # ------------------------------------------------------------------
    def _load_cache(self) -> dict:
        try:
            if self.cache_file.exists():
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_cache(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(
                json.dumps(self.cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _get_cache_key(self, error_message: str) -> str:
        return hashlib.md5(error_message.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Ana analiz metodu
    # ------------------------------------------------------------------
    def analyze(self, log_entry: dict) -> dict | None:
        """
        Log kaydını analiz et, öneri döndür.

        Returns:
            {
                "source":   "cache" | "ai" | "pattern",
                "severity": "critical" | "warning" | "info",
                "cause":    "Muhtemel sebep",
                "solution": "Önerilen çözüm",
            }
            veya None (INFO seviyesinde ya da analiz başarısız ise)
        """
        message = log_entry.get("message", "")
        level = log_entry.get("level", "INFO")
        module = log_entry.get("module", "")

        # Sadece ERROR ve WARNING analiz et
        if level not in ("ERROR", "WARNING"):
            return None

        # 1) Yerel pattern eşleştirmesi (token maliyeti yok)
        pattern_result = self._check_patterns(message, module)
        if pattern_result:
            return {**pattern_result, "source": "pattern"}

        # 2) Önbellekte var mı?
        cache_key = self._get_cache_key(message[:200])
        if cache_key in self.cache:
            return {**self.cache[cache_key], "source": "cache"}

        # 3) Gemini API
        ai_result = self._ask_gemini(log_entry)
        if ai_result:
            self.cache[cache_key] = ai_result
            self._save_cache()
            return {**ai_result, "source": "ai"}

        return None

    # ------------------------------------------------------------------
    # Yerel pattern eşleştirme
    # ------------------------------------------------------------------
    def _check_patterns(self, message: str, module: str) -> dict | None:
        """Bilinen hata pattern'larını kontrol et — API çağrısı yapmaz."""
        patterns = [
            {
                "keywords": ["captcha", "BotGuard", "güvenlik doğrulaması", "bot guard"],
                "cause": "GAOSB BotGuard captcha engeli",
                "solution": "Dashboard'dan GAOSB Güvenlik Doğrulaması yapın",
                "severity": "warning",
            },
            {
                "keywords": ["Timeout", "timeout", "zaman aşımı", "timed out", "ReadTimeout"],
                "cause": "Bağlantı zaman aşımı",
                "solution": "İnternet bağlantısını kontrol edin, birkaç dakika sonra tekrar deneyin",
                "severity": "warning",
            },
            {
                "keywords": ["Authentication", "kimlik doğrulama", "login failed", "şifre", "Unauthorized", "401"],
                "cause": "Kimlik doğrulama hatası",
                "solution": ".env dosyasındaki kullanıcı adı ve şifreyi kontrol edin",
                "severity": "critical",
            },
            {
                "keywords": ["MainPage", "mainpage", "navigation", "sayfa yüklenemedi"],
                "cause": "Portal sayfa navigasyon hatası",
                "solution": "Portal erişilebilir mi kontrol edin, session yenileyin",
                "severity": "warning",
            },
            {
                "keywords": ["database", "sqlite", "postgresql", "DB", "OperationalError", "IntegrityError"],
                "cause": "Veritabanı bağlantı hatası",
                "solution": "DATABASE_URL ayarını ve veritabanı erişimini kontrol edin",
                "severity": "critical",
            },
            {
                "keywords": ["smtp", "email", "mail", "SMTP", "SMTPException", "Connection refused"],
                "cause": "Email gönderim hatası",
                "solution": "SMTP ayarlarını Sistem Ayarları'ndan kontrol edin",
                "severity": "warning",
            },
            {
                "keywords": ["iSolar", "isolar", "isolarcloud"],
                "cause": "iSolar portal bağlantı sorunu",
                "solution": "iSolar portalının erişilebilir olduğunu kontrol edin, credentials'ları doğrulayın",
                "severity": "warning",
            },
            {
                "keywords": ["FileNotFoundError", "dosya bulunamadı", "No such file"],
                "cause": "Gerekli dosya veya dizin bulunamadı",
                "solution": "outputs/ ve config/ dizinlerinin varlığını kontrol edin",
                "severity": "critical",
            },
        ]

        msg_lower = message.lower()
        for pattern in patterns:
            if any(kw.lower() in msg_lower for kw in pattern["keywords"]):
                return {
                    "cause": pattern["cause"],
                    "solution": pattern["solution"],
                    "severity": pattern["severity"],
                }
        return None

    # ------------------------------------------------------------------
    # Gemini API çağrısı
    # ------------------------------------------------------------------
    def _ask_gemini(self, log_entry: dict) -> dict | None:
        """Gemini REST API'sine doğrudan istek gönder (SDK bağımlılığı yok).

        - Auth: x-goog-api-key header (query param kullanılmaz)
        - Hata yönetimi:
            400 / 403 / 404 → retry yok
            429             → 3 retry: 5 / 15 / 30 saniye
            5xx             → exponential backoff (5s × 2^attempt, max 5 deneme)
        - Token kullanımı loglanır; API key'i asla loglanmaz.
        """
        if not self.api_key:
            return None

        prompt = (
            "Sen bir yazılım sisteminin log analistisisin.\n"
            "Aşağıdaki log kaydını analiz et ve Türkçe yanıt ver.\n\n"
            f"Log Kaydı:\n"
            f"- Zaman: {log_entry.get('timestamp', '-')}\n"
            f"- Seviye: {log_entry.get('level', '-')}\n"
            f"- Modül: {log_entry.get('module', '-')}\n"
            f"- Mesaj: {log_entry.get('message', '-')}\n\n"
            "Bu bir GES (Güneş Enerji Santrali) otomasyon sistemidir.\n"
            "iSolar ve GAOSB portallarından veri çeker, mahsuplaşma hesaplar.\n\n"
            "Yanıtı SADECE şu JSON formatında ver, başka hiçbir şey yazma:\n"
            '{{\n'
            '  "cause": "Kısa muhtemel sebep (max 100 karakter)",\n'
            '  "solution": "Önerilen çözüm adımları (max 200 karakter)",\n'
            '  "severity": "critical veya warning veya info"\n'
            '}}'
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 256,
            },
        }

        # ---- iç yardımcılar ----

        def _post(model_name: str):
            """API isteği gönder; hata olursa None döndür (key loglanmaz)."""
            url = (
                f"https://generativelanguage.googleapis.com/v1beta"
                f"/models/{model_name}:generateContent"
            )
            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            }
            try:
                return requests.post(url, json=payload, headers=headers, timeout=10)
            except requests.RequestException as exc:
                logging.warning("Gemini isteği başarısız (network): %s", type(exc).__name__)
                return None

        def _parse(response) -> dict | int | None:
            """
            Yanıtı işle.
            - Başarı  → dict (result)
            - 400/403/404 → None  (retry yok)
            - 429 / 5xx → int (status kodu, retry edilecek)
            - Diğer hata → None
            """
            if response is None:
                return None

            status = response.status_code

            if status == 200:
                try:
                    data = response.json()
                except Exception:
                    return None

                # Token kullanımını logla (key loglanmaz!)
                usage = data.get("usageMetadata", {})
                if usage:
                    logging.info(
                        "Gemini token kullanımı — prompt: %s, candidates: %s, toplam: %s",
                        usage.get("promptTokenCount"),
                        usage.get("candidatesTokenCount"),
                        usage.get("totalTokenCount"),
                    )

                try:
                    raw_text = (
                        data["candidates"][0]["content"]["parts"][0]["text"]
                        .strip()
                        .removeprefix("```json")
                        .removeprefix("```")
                        .removesuffix("```")
                        .strip()
                    )
                    result = json.loads(raw_text)
                except Exception:
                    return None

                if all(k in result for k in ("cause", "solution", "severity")):
                    return result
                return None

            if status in (400, 403, 404):
                logging.warning(
                    "Gemini isteği %s hatası aldı — retry yapılmayacak", status
                )
                return None

            if status == 429 or 500 <= status < 600:
                return status  # retry için status kodu döndür

            logging.warning("Gemini beklenmeyen HTTP durumu: %s", status)
            return None

        # ---- retry döngüsü ----

        retry_429_delays = [5, 15, 30]
        max_5xx_attempts = 5
        backoff_base = 5  # saniye

        for model_name in (self.model, self.fallback_model):
            attempt = 0
            while True:
                resp = _post(model_name)
                outcome = _parse(resp)

                if isinstance(outcome, dict):
                    return outcome  # başarı

                if outcome is None:
                    break  # kalıcı hata veya network hatası — fallback'e geç

                # outcome = retry'a uygun HTTP durum kodu
                status = outcome

                if status == 429:
                    if attempt < len(retry_429_delays):
                        delay = retry_429_delays[attempt]
                        logging.warning(
                            "Gemini rate-limit (429) — retry %d/%d, %ds bekleniyor",
                            attempt + 1, len(retry_429_delays), delay,
                        )
                        time.sleep(delay)
                        attempt += 1
                        continue
                    logging.error("Gemini 429 retry limiti aşıldı")
                    break

                if 500 <= status < 600:
                    if attempt < max_5xx_attempts:
                        delay = backoff_base * (2 ** attempt)
                        logging.warning(
                            "Gemini sunucu hatası %s — exponential backoff retry %d/%d, %ds bekleniyor",
                            status, attempt + 1, max_5xx_attempts, delay,
                        )
                        time.sleep(delay)
                        attempt += 1
                        continue
                    logging.error("Gemini 5xx retry limiti aşıldı")
                    break

                break  # beklenmeyen durum — fallback'e geç

        return None
