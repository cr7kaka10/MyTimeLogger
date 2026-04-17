from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SessionBase(BaseModel):
    start_time: datetime
    end_time: datetime
    net_duration_minutes: float
    date: str
    day_of_week: Optional[str] = None
    pause_count: int = 0
    pause_reasons: Optional[str] = None
    session_summary: Optional[str] = None
    category_id: Optional[str] = None

class SessionCreate(SessionBase):
    pass

class SessionResponse(SessionBase):
    id: int

    class Config:
        orm_mode = True
