
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token
)
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest,
    InitialPasswordSetup,
    LoginRequest,
    TokenResponse
)
from app.schemas.user import UserRead


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """Create a new user account and log the user in."""

    full_name = data.full_name.strip()
    email = data.email.strip().lower()

    if len(full_name) < 2:
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid full name"
        )

    if (
        "@" not in email
        or "." not in email.split("@")[-1]
    ):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid email address"
        )

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists"
        )

    new_user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(data.password),
        is_active=True
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists"
        )

    token = create_access_token(new_user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserRead.model_validate(new_user)
    }


@router.post("/initial-setup")
def initial_password_setup(
    data: InitialPasswordSetup,
    setup_key: str = Header(..., alias="X-RelayMap-Setup-Key"),
    db: Session = Depends(get_db)
):
    """
    Set the initial password for an existing team member.
    Requires the private setup key and only works once per account.
    """

    if not secrets.compare_digest(
        setup_key,
        settings.AUTH_SETUP_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid setup key"
        )

    email = data.email.strip().lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found"
        )

    if user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password has already been configured"
        )

    user.password_hash = hash_password(data.password)

    db.commit()
    db.refresh(user)

    return {
        "message": "Password configured successfully. You can now log in."
    }


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Authenticate a user and generate a JWT token."""

    email = data.email.strip().lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if (
        user is None
        or not user.is_active
        or not user.password_hash
        or not verify_password(data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserRead.model_validate(user)
    }


@router.get("/me", response_model=UserRead)
def get_my_account(
    current_user: User = Depends(get_current_user)
):
    """Return the currently authenticated user's details."""

    return current_user