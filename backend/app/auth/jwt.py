from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import SECRET_KEY

ALGORITHM = "HS256"
EXPIRY_HOURS = 24

security = HTTPBearer()

def create_token(seller_id: str) -> str:
    payload = {
        "seller_id": seller_id,
        "exp": datetime.utcnow() + timedelta(hours=EXPIRY_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        seller_id = payload.get("seller_id")
        if not seller_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return seller_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")