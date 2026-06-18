import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
EXPIRY_HOURS = 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
security = HTTPBearer(auto_error=False)


def create_access_token(data: dict) -> str:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set")

    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=EXPIRY_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_token(seller_id: str) -> str:
    payload = {
        "seller_id": seller_id,
        "exp": datetime.utcnow() + timedelta(hours=EXPIRY_HOURS)
    }
    return create_access_token(payload)


def decode_access_token(token: str) -> dict:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        seller_id = payload.get("seller_id")
        if not seller_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_seller(token: str = Depends(oauth2_scheme)) -> str:
    payload = decode_access_token(token)
    return payload["seller_id"]

def validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    return payload["seller_id"]