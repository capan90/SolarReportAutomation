from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class NotificationEvent:
    """
    Neden: Bildirim sistemine gönderilen olay verisini (event) 
    standart ve değiştirilemez (immutable) bir nesne olarak temsil etmek.
    """
    run_id: str
    event_type: str  # SUCCESS, FAILED, VALIDATION_FAILED, LOGIN_FAILED, DOWNLOAD_FAILED, CONFIG_ERROR, LOCK_EXISTS
    exit_code: int
    duration_ms: int
    machine_name: str
    git_commit: str
    stage_summary: str
    validation_summary: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    attachment_path: Optional[str] = None  # E-postaya eklenecek dosyanın yolu (ör. mahsup raporu)
