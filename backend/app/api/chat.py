from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.auth.jwt import validate_token
from app.agent.chat_pipeline import run_chat

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatResponse(BaseModel):
    seller_id: str
    message:   str
    response:  str


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    seller_id: str = Depends(validate_token),
) -> ChatResponse:
    """
    Accepts a natural language query from the authenticated seller,
    runs it through the LangGraph chatbot pipeline, and returns the
    agent's response.

    - seller_id is always sourced from the validated JWT, never from the request body.
    - All tool calls inside the pipeline are automatically scoped to this seller_id.
    """
    try:
        response_text = await run_in_threadpool(
            run_chat,
            user_message=body.message,
            seller_id=seller_id,
        )
    except Exception as exc:
        detail = str(exc)
        if "503" in detail.upper() or "UNAVAILABLE" in detail.upper():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Agent pipeline failed: {detail}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent pipeline failed: {detail}",
        )

    return ChatResponse(
        seller_id=seller_id,
        message=body.message,
        response=response_text,
    )

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict] = Field(default_factory=list)


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    seller_id: str = Depends(validate_token),
) -> ChatResponse:
    try:
        response_text = await run_in_threadpool(
            run_chat,
            user_message=body.message,
            seller_id=seller_id,
            history=body.history,
        )
    except Exception as exc:
        detail = str(exc)
        if "503" in detail.upper() or "UNAVAILABLE" in detail.upper():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=f"Agent pipeline failed: {detail}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Agent pipeline failed: {detail}")

    return ChatResponse(seller_id=seller_id, message=body.message, response=response_text)


