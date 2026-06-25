from __future__ import annotations

from typing import Any

from app.agent.dashboard_scoring import analyze_product_dashboard
from app.agent.chat_pipeline import run_chat as run_chat_pipeline


def run_dashboard_analysis(
    product_id: str,
    seller_id: str,
    product: dict[str, Any] | None = None,
    include_gemini: bool = False,
    fast_mode: bool = False,
) -> dict[str, Any]:
    return analyze_product_dashboard(
        product_id,
        seller_id,
        product,
        include_gemini=include_gemini,
        fast_mode=fast_mode,
    )


def run_chat(query: str, seller_id: str) -> dict[str, Any]:
    return run_chat_pipeline(query, seller_id)
