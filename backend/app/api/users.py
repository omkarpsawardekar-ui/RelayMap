from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead


router = APIRouter(
    prefix="/api/users",
    tags=["Users"]
)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    email = user_data.email.strip().lower()

    if "@" not in email:
        raise HTTPException(
            status_code=422,
            detail="Please provide a valid email address"
        )

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists"
        )

    new_user = User(
        full_name=user_data.full_name.strip(),
        email=email
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    except Exception:
        db.rollback()
        raise

    return new_user


@router.get("", response_model=list[UserRead])
def get_users(db: Session = Depends(get_db)):

    return db.query(User).order_by(User.id).all()