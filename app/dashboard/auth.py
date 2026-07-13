import os
import uuid
import bcrypt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.database.db_session import SessionLocal
from app.database.models import DashboardUser, AuditLog
from app.core.logger import setup_logger

logger = setup_logger("DashboardAuth")

# In-memory session store: {token: {"username": username, "ip": ip, "expires_at": datetime}}
_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_TIMEOUT_HOURS = 8

class DashboardAuth:
    def create_user(self, username: str, password: str, display_name: str) -> bool:
        """Yeni kullanıcı oluştur (şifreyi bcrypt ile hash'leyerek)"""
        db = SessionLocal()
        try:
            # Kullanıcı adının benzersiz olduğunu kontrol et
            existing = db.query(DashboardUser).filter(DashboardUser.username == username).first()
            if existing:
                logger.warning(f"Kullanıcı oluşturma başarısız: '{username}' zaten mevcut.")
                return False

            # Şifreyi hash'le
            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

            user = DashboardUser(
                username=username,
                password_hash=password_hash,
                display_name=display_name,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
            logger.info(f"Yeni kullanıcı oluşturuldu: '{username}' ({display_name})")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Kullanıcı oluşturulurken veritabanı hatası: {e}")
            return False
        finally:
            db.close()

    def verify_user(self, username: str, password: str) -> bool:
        """Kullanıcı doğrula"""
        db = SessionLocal()
        try:
            user = db.query(DashboardUser).filter(DashboardUser.username == username).first()
            if not user or not user.is_active:
                return False

            # Şifreyi doğrula
            if bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
                # Son giriş tarihini güncelle
                user.last_login = datetime.utcnow()
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Kullanıcı doğrulanırken hata: {e}")
            return False
        finally:
            db.close()

    def create_session(self, username: str, ip: str) -> str:
        """Session token üret (UUID), bellekte sakla"""
        token = str(uuid.uuid4())
        _SESSIONS[token] = {
            "username": username,
            "ip": ip,
            "expires_at": datetime.utcnow() + timedelta(hours=SESSION_TIMEOUT_HOURS)
        }
        return token

    def verify_session(self, token: str) -> Optional[str]:
        """Token geçerli mi? → username döndür"""
        if not token or token not in _SESSIONS:
            return None

        session = _SESSIONS[token]
        if datetime.utcnow() > session["expires_at"]:
            # Süresi geçmiş session'ı sil
            _SESSIONS.pop(token, None)
            return None

        # Session geçerlilik süresini uzatabiliriz (opsiyonel, şimdilik sabit 8 saat kalabilir)
        return session["username"]

    def destroy_session(self, token: str) -> None:
        """Logout: Session'ı bellekten sil"""
        _SESSIONS.pop(token, None)

    def log_action(self, username: str, ip: Optional[str], action: str, details: Optional[str] = None, success: bool = True) -> None:
        """Denetim günlüğüne (audit_log) kaydet"""
        db = SessionLocal()
        try:
            log = AuditLog(
                timestamp=datetime.utcnow(),
                username=username,
                ip_address=ip,
                action=action,
                details=details,
                success=success
            )
            db.add(log)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Audit log kaydedilirken hata: {e}")
        finally:
            db.close()
