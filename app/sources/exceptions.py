class SourceError(Exception):
    """Ortak taban kaynak hatası sınıfı."""
    pass

class UnknownSourceError(SourceError):
    """İstenen veri kaynağı registry'de kayıtlı olmadığında fırlatılır."""
    def __init__(self, source_name: str):
        super().__init__(f"Bilinmeyen veri kaynağı: '{source_name}'. Lütfen yapılandırmayı kontrol edin.")

class DisabledSourceError(SourceError):
    """Devre dışı bırakılmış (enabled: false) bir kaynak çağrıldığında fırlatılır."""
    def __init__(self, source_name: str):
        super().__init__(f"Veri kaynağı '{source_name}' şu anda devre dışı bırakılmıştır.")

class UnsupportedCapabilityError(SourceError):
    """Kaynağın desteklemediği bir yetenek istendiğinde fırlatılır."""
    def __init__(self, source_name: str, capability: str):
        super().__init__(f"'{source_name}' veri kaynağı '{capability}' yeteneğini desteklememektedir.")

class SourceConfigurationError(SourceError):
    """sources.json dosyasında şema veya yükleme hatası olduğunda fırlatılır."""
    def __init__(self, message: str):
        super().__init__(f"Kaynak yapılandırma hatası: {message}")

class SourceAuthenticationError(SourceError):
    """Veri kaynağı portalına/servisine girişte hata alındığında fırlatılır."""
    def __init__(self, source_name: str):
        super().__init__(f"'{source_name}' veri kaynağı için kimlik doğrulama başarısız oldu. Lütfen kimlik bilgilerinizi doğrulayın.")
