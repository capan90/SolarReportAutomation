import hashlib
import json
import os
import requests
from pathlib import Path


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
        self.model = "gemini-2.0-flash"

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
        """Gemini REST API'sine doğrudan istek gönder (SDK bağımlılığı yok)."""
        if not self.api_key:
            return None

        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{self.model}:generateContent"
                f"?key={self.api_key}"
            )

            prompt = f"""Sen bir yazılım sisteminin log analistisisin.
Aşağıdaki log kaydını analiz et ve Türkçe yanıt ver.

Log Kaydı:
- Zaman: {log_entry.get('timestamp', '-')}
- Seviye: {log_entry.get('level', '-')}
- Modül: {log_entry.get('module', '-')}
- Mesaj: {log_entry.get('message', '-')}

Bu bir GES (Güneş Enerji Santrali) otomasyon sistemidir.
iSolar ve GAOSB portallarından veri çeker, mahsuplaşma hesaplar.

Yanıtı SADECE şu JSON formatında ver, başka hiçbir şey yazma:
{{
  "cause": "Kısa muhtemel sebep (max 100 karakter)",
  "solution": "Önerilen çözüm adımları (max 200 karakter)",
  "severity": "critical veya warning veya info"
}}"""

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 256,
                },
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                text = (
                    data["candidates"][0]["content"]["parts"][0]["text"]
                    .strip()
                    .removeprefix("```json")
                    .removeprefix("```")
                    .removesuffix("```")
                    .strip()
                )
                result = json.loads(text)
                # Validate required keys
                if all(k in result for k in ("cause", "solution", "severity")):
                    return result
            return None

        except Exception:
            return None
