from pydantic import BaseModel
from typing import Optional

class CategoryBase(BaseModel):
    name: str
    icon: str = "📖"
    color: str = "#5E81AC"
    group_name: str = "输入"
    sort_order: int = 0
    is_active: int = 1

class CategoryCreate(CategoryBase):
    id: Optional[str] = None
    created_at: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: str
    created_at: str

    class Config:
        orm_mode = True
