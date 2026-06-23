from google import genai
from google.genai import types
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.core.config import GEMINI_API_KEYS

if not GEMINI_API_KEYS:
    raise ValueError("No Gemini API keys found in .env")

MODEL = "gemini-2.5-flash"


def get_client():
    """
    Returns a working Gemini client.
    Tries API keys one by one until one succeeds.
    """
    last_error = None

    for api_key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=api_key)
            client.models.generate_content(model=MODEL, contents="ping")
            return client

        except Exception as e:
            print(f"Gemini key failed: {api_key[:10]}...")
            last_error = e

    raise Exception(f"All Gemini API keys failed. Last error: {last_error}")


def _convert_messages(contents: list) -> list[types.Content]:
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
            # Reconstruct function call parts if tool_calls present
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
            # Tool results go back as a user turn with a function_response part
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
            # Gemini doesn't support system role inside contents;
            # prepend as user turn so context isn't lost
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=str(msg.content))],
                )
            )

        else:
            # Fallback for any unknown message type
            gemini_contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=str(msg.content))],
                )
            )

    return gemini_contents


def generate_simple(prompt: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )
    return response.text


def generate_with_tools(contents: list, tools_schema: list):
    """
    contents    : list of LangChain message objects from LangGraph state
    tools_schema: list of Gemini FunctionDeclaration objects from tool_schemas.py
    """
    client = get_client()
    gemini_contents = _convert_messages(contents)
    tool_config = types.Tool(function_declarations=tools_schema)
    config = types.GenerateContentConfig(tools=[tool_config])

    return client.models.generate_content(
        model=MODEL,
        contents=gemini_contents,
        config=config,
    )


