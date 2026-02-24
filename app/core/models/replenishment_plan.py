from sqlalchemy import Column, Integer, Float
from app.core.models.base import Base

class ReplenishmentPlan(Base):
    __tablename__ = "replenishment_plan"

    id = Column(Integer, primary_key=True, index=True)
    reorder_qty = Column(Float)
    weeks_of_cover = Column(Float)