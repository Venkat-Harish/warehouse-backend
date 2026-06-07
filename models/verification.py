from sqlalchemy import (
    Column, Integer, BigInteger, Boolean, Date,
    DateTime, String, LargeBinary, ForeignKey
)
from sqlalchemy.sql import func

from database import Base


class VerificationActivity(Base):
    __tablename__ = "verification_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    wid = Column(BigInteger, nullable=False, index=True)
    wid_found_in_db = Column(Boolean, default=True)

    # Data from DB at the time of verification
    db_ean = Column(BigInteger, nullable=True)
    db_mfg_date = Column(Date, nullable=True)
    db_expiry_date = Column(Date, nullable=True)

    # Data detected by OCR
    ocr_ean = Column(BigInteger, nullable=True)
    ocr_mfg_date = Column(Date, nullable=True)
    ocr_expiry_date = Column(Date, nullable=True)

    # Status
    # ocr_status: 'pending' | 'done' | 'timeout' | 'failed'
    ocr_status = Column(String(20), default="pending", nullable=False)
    # verification_status: 'submitted' | 'operator_confirmed'
    verification_status = Column(String(30), default="submitted", nullable=False)

    # Timestamps
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Photo stored as JPEG bytes
    photo_data = Column(LargeBinary, nullable=True)
    photo_mime_type = Column(String(20), default="image/jpeg")
