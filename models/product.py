from sqlalchemy import Column, BigInteger, Date

from database import Base


class Product(Base):
    __tablename__ = "products"

    wid = Column(BigInteger, primary_key=True, index=True)
    ean = Column(BigInteger, nullable=False)
    manufacturing_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
