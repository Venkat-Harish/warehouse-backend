from datetime import date
from pydantic import BaseModel


class ProductOut(BaseModel):
    wid: int
    ean: int
    manufacturing_date: date
    expiry_date: date

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    imported: int
    skipped: int
    errors: int
    message: str
