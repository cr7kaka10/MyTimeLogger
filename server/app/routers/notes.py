from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.db import get_db
from app.models.note import Note
from app.schemas.note import NoteCreate, NoteResponse
from app.auth.security import get_current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])

@router.get("/", response_model=list[NoteResponse])
def get_notes(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return db.query(Note).order_by(Note.created_at.desc()).all()

@router.post("/", response_model=NoteResponse)
def create_note(note: NoteCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    new_note = Note(content=note.content, created_at=datetime.utcnow())
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note
