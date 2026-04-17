from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from app.models.base import Base

class Session(Base):
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    net_duration_minutes = Column(Float, nullable=False)
    date = Column(String(10), nullable=False)
    day_of_week = Column(String(20))
    pause_count = Column(Integer, default=0)
    pause_reasons = Column(Text)
    session_summary = Column(Text)
    category_id = Column(String(36), index=True)
