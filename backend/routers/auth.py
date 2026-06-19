from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy.orm import Session
from database import get_db
from fastapi.security import OAuth2PasswordRequestForm
import schemas, utils, oauth2, models
from datetime import timedelta
from config import settings

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

router = APIRouter()

@router.post("/login")
async def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db : Session = Depends(get_db) ):
    user = oauth2.get_user(db, user_credentials.username)
    if user:
        verified = utils.authenticate_user(db,user,user_credentials.password)
        if verified:
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = oauth2.create_access_token(
                data={"user_id": user.id}, expires_delta=access_token_expires
            )
            return {"access_token": access_token, "token_type" : "bearer"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

@router.post("/register")
async def register(user: schemas.userRegister,db : Session = Depends(get_db)):
    user_query = oauth2.get_user(db, user.email)
    if user_query:
        return HTTPException(status_code=status.HTTP_409_CONFLICT,detail="Email already registered")
    hashed_password = utils.hash_password(user.password)
    user.password = hashed_password
    new_user = models.Users(**user.model_dump())
    db.add(new_user)
    db.commit()