from sqlalchemy import Column, Integer, String, DateTime
from app.models.base import Base

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False)
