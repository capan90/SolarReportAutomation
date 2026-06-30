import json
from pathlib import Path
from app.core.config import BASE_DIR
from app.core.logger import setup_logger

logger = setup_logger("NotificationPolicyEvaluator")

class NotificationPolicyEvaluator:
    """
    Neden: Bildirim gönderim kurallarının (Policy) koddan bağımsız olarak 
    dışarıdaki bir JSON dosyasından yönetilmesini ve çalışma anında değerlendirilmesini sağlamak.
    """
    def __init__(self, policy_path: Path = None):
        if policy_path is None:
            self.policy_path = BASE_DIR / "config" / "notification_policy.json"
        else:
            self.policy_path = policy_path
        
        self.default_policies = {
            "SUCCESS": False,
            "FAILED": True,
            "VALIDATION_FAILED": True,
            "LOGIN_FAILED": True,
            "DOWNLOAD_FAILED": True,
            "LOCK_EXISTS": False,
            "CONFIG_ERROR": True
        }

    def should_notify(self, event_type: str) -> bool:
        """
        Neden: Verilen olay tipinin bildirim tetikleyip tetiklemeyeceğini
        JSON kurallarına göre değerlendirmek. Dosya okunamazsa fallback kuralları devreye girer.
        """
        policies = self.default_policies
        
        if self.policy_path.exists():
            try:
                content = self.policy_path.read_text(encoding="utf-8")
                data = json.loads(content)
                policies = data.get("policies", self.default_policies)
            except Exception as e:
                logger.error(f"Bildirim kuralları dosyası okunamadı (Varsayılan politika kullanılacak): {e}")
        else:
            logger.warning(f"Bildirim kuralları dosyası bulunamadı, varsayılan kurallar aktif: {self.policy_path}")
            
        # Olay tipini büyük harfe dönüştürerek kontrol et
        key = str(event_type).upper()
        return policies.get(key, True)  # Varsayılan olarak bilinmeyen tipler için gönder
