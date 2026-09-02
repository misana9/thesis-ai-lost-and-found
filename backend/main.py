from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
import models
import oauth2
from routers import auth, clip_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads_dir = Path(__file__).parent / "uploads"
uploads_dir.mkdir(exist_ok=True)

app.include_router(auth.router)
app.include_router(clip_router.router)


def _user_from_bearer_or_query(
    authorization: str | None,
    token: str | None,
    db: Session,
) -> models.Users:
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    elif token:
        raw = token.strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view uploads",
            headers={"WWW-Authenticate": "Bearer"},
        )
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = oauth2.verify_access_token(raw, credentials_exception)
    user = oauth2.user_from_token(db, token_data)
    if not user:
        raise credentials_exception
    return user


@app.get("/uploads/{filename}")
async def get_upload(
    filename: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """Serve uploaded images only to authenticated users.

    Browsers cannot send Authorization on <img src>, so ?token=<jwt> is accepted.
    """
    _user_from_bearer_or_query(authorization, token, db)

    # Prevent path traversal; only serve files directly under uploads/
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = uploads_dir / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.get("/")
def root():
    return {"message": "AMAlost API"}
