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
    def create_user(self, username: str, password: str, display_name: str, update_if_exists: bool = False) -> bool:
        """Yeni kullanıcı oluştur (şifreyi bcrypt ile hash'leyerek)"""
        db = SessionLocal()
        try:
            # Şifreyi hash'le
            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

            # Kullanıcı adının benzersiz olduğunu kontrol et
            existing = db.query(DashboardUser).filter(DashboardUser.username == username).first()
            if existing:
                if update_if_exists:
                    existing.password_hash = password_hash
                    existing.display_name = display_name
                    existing.is_active = True
                    db.commit()
                    logger.info(f"Kullanıcı şifresi/bilgileri güncellendi: '{username}' ({display_name})")
                    return True
                else:
                    logger.warning(f"Kullanıcı oluşturma başarısız: '{username}' zaten mevcut.")
                    return False

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
                # Son giriş tarihini güncelle (hata alırsa girişi engellemesin)
                try:
                    user.last_login = datetime.utcnow()
                    db.commit()
                except Exception as db_err:
                    db.rollback()
                    logger.error(f"Son giriş tarihi güncellenemedi: {db_err}")
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

    def update_user(self, username: str, display_name: str, is_active: bool, password: Optional[str] = None,
                    actor: Optional[str] = None, ip: Optional[str] = None) -> bool:
        """Kullanıcı bilgilerini güncelle (ve varsa şifresini bcrypt ile hash'leyerek değiştir)"""
        db = SessionLocal()
        success = False
        details = ""
        try:
            user = db.query(DashboardUser).filter(DashboardUser.username == username).first()
            if not user:
                logger.warning(f"Kullanıcı güncelleme başarısız: '{username}' bulunamadı.")
                details = f"Kullanıcı bulunamadı: '{username}'"
            else:
                user.display_name = display_name
                user.is_active = is_active

                if password:
                    salt = bcrypt.gensalt()
                    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
                    user.password_hash = password_hash

                db.commit()
                logger.info(f"Kullanıcı güncellendi: '{username}'")
                details = f"Kullanıcı güncellendi: '{username}'" + (" (şifre değiştirildi)" if password else "")
                success = True
        except Exception as e:
            db.rollback()
            logger.error(f"Kullanıcı güncellenirken hata: {e}")
            details = f"Kullanıcı güncellenemedi: '{username}' — {e}"
        finally:
            db.close()

        # Denetim günlüğü zorunlu: session kapandıktan sonra yazılır (SQLite kilit riski yok)
        self.log_action(actor or username, ip, "user_update", details=details, success=success)
        return success

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Kullanıcının kendi şifresini değiştirir (önce eski şifreyi doğrula)"""
        # 1. Eski şifreyi doğrula
        # verify_user contains db session handling and checks password via bcrypt
        if not self.verify_user(username, old_password):
            return False

        # 2. Yeni şifreyi hash'le ve kaydet
        db = SessionLocal()
        try:
            user = db.query(DashboardUser).filter(DashboardUser.username == username).first()
            if not user:
                return False

            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(new_password.encode("utf-8"), salt).decode("utf-8")
            user.password_hash = password_hash
            db.commit()
            logger.info(f"Kullanıcı kendi şifresini değiştirdi: '{username}'")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Şifre değiştirilirken hata: {e}")
            return False
        finally:
            db.close()

    def delete_user(self, username: str, actor: Optional[str] = None, ip: Optional[str] = None) -> bool:
        """Kullanıcı sil"""
        db = SessionLocal()
        success = False
        details = ""
        try:
            user = db.query(DashboardUser).filter(DashboardUser.username == username).first()
            if not user:
                logger.warning(f"Kullanıcı silme başarısız: '{username}' bulunamadı.")
                details = f"Kullanıcı bulunamadı: '{username}'"
            else:
                db.delete(user)
                db.commit()
                logger.info(f"Kullanıcı silindi: '{username}'")
                details = f"Kullanıcı silindi: '{username}'"
                success = True
        except Exception as e:
            db.rollback()
            logger.error(f"Kullanıcı silinirken hata: {e}")
            details = f"Kullanıcı silinemedi: '{username}' — {e}"
        finally:
            db.close()

        # Denetim günlüğü zorunlu: session kapandıktan sonra yazılır
        self.log_action(actor or username, ip, "user_delete", details=details, success=success)
        return success
