from fastapi import HTTPException, APIRouter
from backend.app.models.seller import LoginRequest, LoginResponse
from backend.app.auth.hashing import verify_password
from backend.app.auth.jwt import create_token
from backend.app.database.connection import sellers_collection

router =APIRouter()

@router.post("/auth/login",response_model=LoginResponse)
def login( request : LoginRequest):
    seller= sellers_collection.find_one({"username":request.username})
    if not seller:
        raise HTTPException(status_code=401, detail="Invalid Credentials")
    if not verify_password(request.password,seller["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid Credentials")
    token= create_token(str(seller["_id"]))
    return {
        "access_token" : token,
        "token_type" : "Bearer",
        "expires_in" : 86400
    }
