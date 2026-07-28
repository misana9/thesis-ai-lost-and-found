import jwt
from jwt.exceptions import InvalidTokenError
from datetime import timedelta, datetime, timezone
from config import settings
import schemas, models
from fastapi import Depends, HTTPException, status
from database import get_db
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str, credential_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id = payload.get("user_id")
        if id is None:
            raise credential_exception
        token_data = schemas.tokenData(id=id)
    except InvalidTokenError:
        raise credential_exception
    return token_data


def get_user(db: Session, username: str):
    return db.query(models.Users).filter(models.Users.email == username).first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verify_access_token(token, credentials_exception)


def user_from_token(db: Session, token_data: schemas.tokenData) -> models.Users | None:
    return db.query(models.Users).filter(models.Users.id == token_data.id).first()


def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> models.Users | None:
    if not token:
        return None
    try:
        token_data = verify_access_token(
            token,
            HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"),
        )
    except HTTPException:
        return None
    return user_from_token(db, token_data)


def get_admin_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Users:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_access_token(token, credentials_exception)
    user = user_from_token(db, token_data)
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
