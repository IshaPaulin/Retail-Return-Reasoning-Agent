# app/agent/gemini_client.py

import json
from google import genai
from google.genai import types
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.core.config import GEMINI_API_KEYS

if not GEMINI_API_KEYS:
    raise ValueError("No Gemini API keys found in .env")

MODEL = "gemini-2.5-flash"

_current_key_index = 0


def get_client() -> genai.Client:
    """Returns a Gemini client using the current active API key."""
    return genai.Client(api_key=GEMINI_API_KEYS[_current_key_index])


def convert_messages(contents: list) -> list[types.Content]:
    """
    Converts LangChain message objects (used by LangGraph state) into
    Gemini SDK types.Content objects.

    LangChain → Gemini role mapping:
        HumanMessage  → "user"
        AIMessage     → "model"
        ToolMessage   → "user"  (tool results sent back as user turn)
        SystemMessage → "user"  (Gemini has no system role in contents)
    """
    gemini_contents = []

    for msg in contents:
        if isinstance(msg, HumanMessage):
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=str(msg.content))],
                )
            )

        elif isinstance(msg, AIMessage):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                parts = []
                for tc in msg.tool_calls:
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                name=tc["name"],
                                args=tc["args"],
                            )
                        )
                    )
                gemini_contents.append(
                    types.Content(role="model", parts=parts)
                )
            else:
                gemini_contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part(text=str(msg.content))],
                    )
                )

        elif isinstance(msg, ToolMessage):
            tool_name = msg.name if hasattr(msg, "name") and msg.name else "tool"
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name,
                                response={"result": str(msg.content)},
                            )
                        )
                    ],
                )
            )

        elif isinstance(msg, SystemMessage):
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=str(msg.content))],
                )
            )

        else:
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=str(msg.content))],
                )
            )

    return gemini_contents


def generate_simple(prompt: str) -> str:
    """
    One-shot generation with no tools.
    Used by scope_check.py and dashboard_scoring.py fallback.
    """
    client = get_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )
    return response.text


def generate_json(prompt: str, system_instruction: str = "") -> dict:
    """
    One-shot generation expecting a structured JSON response.
    Used by dashboard_scoring.py for Gemini insight generation.
    Strips markdown fences and parses JSON before returning.
    Returns empty dict on parse failure — caller handles gracefully.
    """
    client = get_client()

    full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt

    response = client.models.generate_content(
        model=MODEL,
        contents=full_prompt,
    )

    raw = response.text.strip()
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {}


def generate_with_tools(contents: list, tools_schema: list):
    """
    Generation with Gemini native function calling enabled.
    contents: list of Gemini types.Content objects (already converted
    via convert_messages before calling this function).
    Used by chatbot_pipeline.py agent_node.
    Returns raw response object.
    """
    client = get_client()
    tool_config = types.Tool(function_declarations=tools_schema)
    config = types.GenerateContentConfig(tools=[tool_config])

    return client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=config,
    )