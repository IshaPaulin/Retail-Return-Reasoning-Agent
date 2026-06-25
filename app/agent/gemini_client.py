from __future__ import annotations

import json
import os
from typing import Any

import google.generativeai as genai


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    return key


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"


def _build_model(system_instruction: str = ""):
    genai.configure(api_key=_api_key())
    kwargs: dict[str, Any] = {"model_name": _model_name()}
    instruction = system_instruction.strip()
    if instruction:
        kwargs["system_instruction"] = instruction
    return genai.GenerativeModel(**kwargs)


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()
        cleaned = cleaned.replace("```", "").strip()
    return cleaned


def generate_text(prompt: str, system_instruction: str = "") -> str:
    try:
        response = _build_model(system_instruction).generate_content(prompt)
        return (getattr(response, "text", "") or "").strip()
    except Exception:
        return ""


def generate_json(
    prompt: str,
    system_instruction: str = "",
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = generate_text(prompt, system_instruction)
    if not text:
        return default or {}

    cleaned = _strip_code_fences(text)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return default or {}

    if isinstance(parsed, dict):
        return parsed

    return default or {}