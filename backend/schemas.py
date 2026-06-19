from pydantic import BaseModel

class user(BaseModel):
    email : str
    password : str

class userRegister(user):
    full_name : str

class token(BaseModel):
    access_token : str  
    token_type : str

class tokenData(BaseModel):
    id: int

class UserInDB(user):
    hashed_password: str