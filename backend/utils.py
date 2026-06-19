from pwdlib import PasswordHash
import schemas

password_hash = PasswordHash.recommended()

def hash_password(plain):
    return password_hash.hash(plain)

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def authenticate_user(db, user : schemas.user, password):
    if not verify_password(password, user.password):
        return False
    return True
