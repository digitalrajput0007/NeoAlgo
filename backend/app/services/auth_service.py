from datetime import datetime, timedelta
from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.config import settings
import logging

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

ph = PasswordHasher()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.neoalgo_session_timeout_hours)
    
    # Session invalidation: embed part of the current password hash to invalidate old tokens when password changes
    pwd_rev = settings.neoalgo_admin_password_hash[-8:] if settings.neoalgo_admin_password_hash else "default"
    
    to_encode.update({"exp": expire, "pwd_rev": pwd_rev})
    
    if not settings.neoalgo_auth_secret:
        logger.warning("NEOALGO_AUTH_SECRET not set, using default insecure secret")
        secret = "INSECURE_DEFAULT_SECRET"
    else:
        secret = settings.neoalgo_auth_secret

    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict | None:
    try:
        secret = settings.neoalgo_auth_secret or "INSECURE_DEFAULT_SECRET"
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
