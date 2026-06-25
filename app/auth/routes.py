from fastapi import APIRouter, HTTPException

from app.auth.hashing import verify_password
from app.auth.jwt import create_access_token
from app.database.connection import sellers_collection
from app.models.seller import LoginRequest, LoginResponse

router = APIRouter()


def _find_seller(username: str):
    return sellers_collection.find_one({"username": username})

@router.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest):
    seller = _find_seller(request.username)
    if not seller:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    hashed_password = seller.get("password_hash") or seller.get("hashed_password")
    if not hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(request.password, hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    seller_id=seller.get("seller_id") or str(seller.get("_id"))
    token=create_access_token({"seller_id": seller_id})

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
    }
