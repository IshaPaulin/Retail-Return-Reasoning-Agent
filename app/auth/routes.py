from fastapi import APIRouter, HTTPException

from app.auth.hashing import verify_password
from app.auth.jwt import create_access_token
from app.database.connection import legacy_sellers_collection, sellers_collection
from app.models.seller import LoginRequest, LoginResponse

router = APIRouter()


def _find_seller(username: str):
    seller = sellers_collection.find_one({"username": username})
    if seller is None:
        seller = legacy_sellers_collection.find_one({"username": username})
    return seller

@router.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest):
    seller = _find_seller(request.username)
    if not seller:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(request.password, seller["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"seller_id": str(seller["_id"])})
    return {
        "access_token": token,
        "token_type": "bearer"
    }
