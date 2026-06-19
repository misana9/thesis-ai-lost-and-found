from database import Base
from sqlalchemy import Column,Integer,String


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String,nullable=False)
    full_name = Column(String, nullable=False)