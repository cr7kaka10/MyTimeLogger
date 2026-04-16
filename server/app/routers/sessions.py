from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.db import get_db
from app.models.session import Session as StudySession
from app.schemas.session import SessionCreate, SessionResponse
from app.auth.security import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

@router.get("/", response_model=list[SessionResponse])
def get_sessions(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return db.query(StudySession).order_by(StudySession.start_time.asc()).all()

@router.post("/start", response_model=SessionResponse)
def log_session(session: SessionCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    new_session = StudySession(**session.dict())
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

@router.get("/timeline")
def get_timeline(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # Basic implementation, will evolve based on Android MVP requirements
    sessions = db.query(StudySession).order_by(StudySession.start_time.desc()).limit(50).all()
    return {"timeline": sessions}
