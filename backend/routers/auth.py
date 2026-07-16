from datetime import timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import get_db
from config import settings
import schemas
import utils
import oauth2
import models

router = APIRouter(prefix="/auth", tags=["auth"])
legacy_router = APIRouter(tags=["auth-legacy"])

ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def build_user_token(user: models.Users) -> str:
    return oauth2.create_access_token(
        data={
            "user_id": user.id,
            "id": user.id,
            "email": user.email,
            "name": user.full_name,
            "email_verified": bool(user.email_verified),
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


@router.post("/register", response_model=schemas.AuthRegisterResponse)
async def register(body: schemas.AuthRegisterRequest, db: Session = Depends(get_db)):
    existing = oauth2.get_user(db, body.email.strip().lower())
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    verify_token = secrets.token_urlsafe(32)
    new_user = models.Users(
        email=body.email.strip().lower(),
        password=utils.hash_password(body.password),
        full_name=body.name.strip(),
        email_verified=False,
        email_verification_token=verify_token,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Prototype: no real email sender — expose a verify URL for local testing.
    return {
        "message": "Registration successful. Please verify your email.",
        "dev_verify_url": f"http://localhost:8000/auth/verify?token={verify_token}",
    }


@router.get("/verify", response_model=schemas.AuthVerifyResponse)
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = (
        db.query(models.Users)
        .filter(models.Users.email_verification_token == token)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link",
        )

    user.email_verified = True
    user.email_verification_token = None
    db.commit()

    return {
        "message": "Email verified successfully. You can sign in now.",
        "email": user.email,
    }


@router.post("/login", response_model=schemas.token)
async def login(body: schemas.AuthLoginRequest, db: Session = Depends(get_db)):
    user = oauth2.get_user(db, body.email.strip().lower())
    if not user or not utils.authenticate_user(db, user, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before signing in.",
        )

    return {
        "access_token": build_user_token(user),
        "token_type": "bearer",
    }


@legacy_router.post("/login", response_model=schemas.token)
async def legacy_login(
    user_credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = oauth2.get_user(db, user_credentials.username)
    if user and utils.authenticate_user(db, user, user_credentials.password):
        return {
            "access_token": build_user_token(user),
            "token_type": "bearer",
        }
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@legacy_router.post("/register")
async def legacy_register(user: schemas.userRegister, db: Session = Depends(get_db)):
    """Compatibility wrapper — prefer POST /auth/register."""
    return await register(
        schemas.AuthRegisterRequest(
            name=user.full_name,
            email=user.email,
            password=user.password,
        ),
        db,
    )
