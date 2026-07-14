from database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid

EMBEDDING_DIM = 512


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, server_default="false")


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
    finder_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    image_path = Column(String, nullable=True)
    image_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    text_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    status = Column(String, nullable=False, server_default="available")  # available | claimed
    claimed_by_lost_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LostItem(Base):
    __tablename__ = "lost_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    location = Column(String, nullable=True)
    date_lost = Column(String, nullable=True)
    email = Column(String, nullable=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    image_path = Column(String, nullable=True)
    image_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    text_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    status = Column(String, nullable=False, server_default="open")  # open | claimed | notified
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Claim(Base):
    __tablename__ = "claims"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    found_item_id = Column(String, ForeignKey("found_items.id"), nullable=False)
    lost_item_id = Column(String, ForeignKey("lost_items.id"), nullable=False)
    claimed_by_email = Column(String, nullable=True)
    claimed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, server_default="pending")  # pending | confirmed | rejected
    notify_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
