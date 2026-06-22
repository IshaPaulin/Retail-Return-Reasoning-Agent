from google import genai
from google.genai import types
from app.core.config import GEMINI_API_KEYS

if not GEMINI_API_KEYS:
    raise ValueError("No Gemini API keys found in .env")

MODEL="gemini-2.5-flash"

_current_key_index = 0

def get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEYS[_current_key_index])

def generate_simple(prompt: str) -> str:
    client=get_client()
    response= client.models.generate_content(
        model=MODEL,
        contents=prompt
    )
    return response.text

def generate_with_tools(contents: list, tools_schema: list):
    client=get_client()
    tool_config=types.Tool(functional_declarations=tools_schema)
    config=types.GenerateContentConfig(tools=[tool_config])
    return client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=config
    )


