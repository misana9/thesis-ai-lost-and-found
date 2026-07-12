from database import Base
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
import uuid


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)


class FoundItem(Base):
    __tablename__ = "found_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(String, nullable=True)
    category = Column(String, nullable=False)
    location = Column(String, nullable=True)
    date_found = Column(String, nullable=True)
    time_found = Column(String, nullable=True)
    reported_by = Column(String, nullable=True)
    finder_email = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    image_embedding = Column(JSON, nullable=True)
    text_embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LostItem(Base):
    __tablename__ = "lost_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    location = Column(String, nullable=True)
    date_lost = Column(String, nullable=True)
    email = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    image_embedding = Column(JSON, nullable=True)
    text_embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())