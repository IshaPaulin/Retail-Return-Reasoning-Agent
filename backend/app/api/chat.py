from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.jwt import validate_token
from app.agent.chat_pipeline import run_chat

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1,
                         description="The seller's natural language query.")


class ChatResponse(BaseModel):
    seller_id: str
    message:   str
    response:  str


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@router.post("/", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    seller_id: str = Depends(validate_token),
) -> ChatResponse:
    """
    Accepts a natural language query from the authenticated seller,
    runs it through the LangGraph chatbot pipeline, and returns the
    agent's grounded response.

    - seller_id is always sourced from the validated JWT, never from the request body.
    - All tool calls inside the pipeline are automatically scoped to this seller_id.
    - Conversation history is persisted per seller via the MongoDB checkpointer
      using seller_id as the thread_id.
    """
    try:
        response_text = run_chat(
            user_message=body.message,
            seller_id=seller_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent pipeline failed: {exc}",
        )

    return ChatResponse(
        seller_id=seller_id,
        message=body.message,
        response=response_text,
    )
