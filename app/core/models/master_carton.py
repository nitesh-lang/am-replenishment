from sqlalchemy import Column, String, Integer
from app.core.models.base import Base


class MasterCarton(Base):
    __tablename__ = "master_cartons"

    model = Column(String, primary_key=True, index=True)
    master_carton = Column(Integer)