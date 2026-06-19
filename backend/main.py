from fastapi import FastAPI, Depends
from database import get_db
from sqlalchemy.orm import Session
from routers import auth
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://127.0.0.1:5500"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(auth.router)

@app.get("/")
def root():
    return {"message" : "Hello world"}



