from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class SubmitResponse(BaseModel):
    activity_id: int
    message: str


class OcrStatusResponse(BaseModel):
    activity_id: int
    ocr_status: str          # pending | done | timeout | failed
    ocr_ean: Optional[int] = None
    ocr_mfg_date: Optional[date] = None
    ocr_expiry_date: Optional[date] = None


class ActivityOut(BaseModel):
    id: int
    wid: int
    wid_found_in_db: bool

    db_ean: Optional[int] = None
    db_mfg_date: Optional[date] = None
    db_expiry_date: Optional[date] = None

    ocr_ean: Optional[int] = None
    ocr_mfg_date: Optional[date] = None
    ocr_expiry_date: Optional[date] = None

    ocr_status: str
    verification_status: str
    checked_at: datetime
    confirmed_at: Optional[datetime] = None

    username: Optional[str] = None  # joined from users table in reports

    class Config:
        from_attributes = True
