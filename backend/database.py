from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

SQLALCHEMY_DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=settings.database_username,
    password=settings.database_password,
    host=settings.database_hostname,
    port=settings.database_port,
    database=settings.database_name,
    query={"sslmode": settings.database_sslmode},
)

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
