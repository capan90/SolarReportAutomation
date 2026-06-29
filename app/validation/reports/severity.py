from enum import Enum

class Severity(Enum):
    """
    Neden: Doğrulama hatalarının kritiklik derecelerini sınıflandırmak ve
    hata yönetimini bu seviyelere göre şekillendirmek (örn. CRITICAL durumlarda akışı kesmek).
    """
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
