from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.config import settings
from core.logger import get_logger, mask_token

logger = get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    logger.debug("hash_password | Entering | input: password=***")
    hashed = pwd_context.hash(password)
    logger.debug("hash_password | Done | output: <bcrypt hash>")
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    logger.debug("verify_password | Entering | input: plain=*** hashed=<bcrypt hash>")
    result = pwd_context.verify(plain, hashed)
    logger.debug("verify_password | Result: %s", result)
    return result


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    logger.debug("create_access_token | Entering | input: sub=%s", data.get("sub"))
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logger.debug("create_access_token | Done | token=%s", mask_token(token))
    return token


def decode_access_token(token: str) -> Optional[dict]:
    logger.debug("decode_access_token | Entering | token=%s", mask_token(token))
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logger.debug("decode_access_token | Success | sub=%s", payload.get("sub"))
        return payload
    except JWTError as e:
        logger.warning("decode_access_token | JWTError: %s | token=%s", str(e), mask_token(token))
        return None


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    logger.debug("get_current_user_id | Entering | token=%s", mask_token(token))
    payload = decode_access_token(token)
    if not payload:
        logger.warning("get_current_user_id | Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id: int = payload.get("sub")
    if user_id is None:
        logger.warning("get_current_user_id | Token missing 'sub' claim")
        raise HTTPException(status_code=401, detail="Token missing subject")
    logger.debug("get_current_user_id | Resolved user_id=%s", user_id)
    return int(user_id)
