from database import Base
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
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
    email_verified = Column(Boolean, nullable=False, server_default="false")
    email_verification_token = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_users_email_verification_token", "email_verification_token"),
    )


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
    is_high_value = Column(Boolean, nullable=False, server_default="false")
    serial_number = Column(String, nullable=True)
    distinctive_marks = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default="available")  # available | in_process | at_desk | processed
    claimed_by_lost_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_found_items_status", "status"),
        Index("ix_found_items_finder_email", "finder_email"),
        Index("ix_found_items_finder_user_id", "finder_user_id"),
    )


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
    is_high_value = Column(Boolean, nullable=False, server_default="false")
    serial_number = Column(String, nullable=True)
    distinctive_marks = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default="open")  # open | in_process | at_desk | processed
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_lost_items_status", "status"),
        Index("ix_lost_items_email", "email"),
        Index("ix_lost_items_owner_user_id", "owner_user_id"),
    )


class Claim(Base):
    __tablename__ = "claims"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    found_item_id = Column(String, ForeignKey("found_items.id"), nullable=False)
    lost_item_id = Column(String, ForeignKey("lost_items.id"), nullable=False)
    claimed_by_email = Column(String, nullable=True)
    claimed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, server_default="in_process")  # in_process | at_desk | processed | cancelled
    owner_confirmed = Column(Boolean, nullable=False, server_default="false")
    finder_confirmed = Column(Boolean, nullable=False, server_default="false")
    desk_received = Column(Boolean, nullable=False, server_default="false")
    desk_released = Column(Boolean, nullable=False, server_default="false")
    owner_confirm_token = Column(String, nullable=True)
    finder_confirm_token = Column(String, nullable=True)
    notify_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_claims_found_item_id", "found_item_id"),
        Index("ix_claims_lost_item_id", "lost_item_id"),
        Index("ix_claims_status", "status"),
        Index("ix_claims_claimed_by_email", "claimed_by_email"),
        Index("ix_claims_owner_confirm_token", "owner_confirm_token"),
        Index("ix_claims_finder_confirm_token", "finder_confirm_token"),
    )