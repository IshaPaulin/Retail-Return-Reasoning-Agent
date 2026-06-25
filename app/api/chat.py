from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agent.chat_pipeline import run_chat
from app.auth.jwt import get_current_seller

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None


@router.post("")
def chat(request: ChatRequest, current_seller_id: str = Depends(get_current_seller)):
    return run_chat(request.query, current_seller_id, request.conversation_id)

