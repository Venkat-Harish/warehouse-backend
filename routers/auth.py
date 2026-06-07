from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserOut
from core.security import hash_password, verify_password, create_access_token
from core.logger import get_logger, sanitize, mask_token

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    logger.info("register | Entering | input: %s", sanitize({"username": payload.username, "password": payload.password}))

    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        logger.warning("register | Username already exists | username=%s", payload.username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("register | Success | new user_id=%d username=%s", user.id, user.username)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    logger.info("login | Entering | input: %s", sanitize({"username": payload.username, "password": payload.password}))

    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        logger.warning("login | User not found | username=%s", payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if not verify_password(payload.password, user.password_hash):
        logger.warning("login | Password mismatch | username=%s", payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token(data={"sub": str(user.id)})
    logger.info("login | Success | user_id=%d username=%s token=%s", user.id, user.username, mask_token(token))
    return {"access_token": token, "token_type": "bearer"}
