from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from app.db import get_db
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryResponse
from app.auth.security import get_current_user

router = APIRouter(prefix="/api/categories", tags=["categories"])

@router.get("/", response_model=list[CategoryResponse])
def get_categories(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return db.query(Category).all()

@router.post("/", response_model=CategoryResponse)
def create_category(category: CategoryCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    cat_id = category.id or str(uuid.uuid4())
    created_at = category.created_at or datetime.now().isoformat()
    new_cat = Category(
        id=cat_id,
        name=category.name,
        icon=category.icon,
        color=category.color,
        group_name=category.group_name,
        sort_order=category.sort_order,
        is_active=category.is_active,
        created_at=created_at
    )
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return new_cat
