from sqlalchemy import Column, String, Integer
from app.models.base import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    icon = Column(String(10), default="📖")
    color = Column(String(10), default="#5E81AC")
    group_name = Column(String(50), default="输入")
    sort_order = Column(Integer, default=0)
    is_active = Column(Integer, default=1)
    created_at = Column(String(30), nullable=False)
