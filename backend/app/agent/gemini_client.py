from google import genai
from google.genai import types
from app.core.config import GEMINI_API_KEYS

if not GEMINI_API_KEYS:
    raise ValueError("No Gemini API keys found in .env")

MODEL="gemini-2.5-flash"

def get_client():
    """
    Returns a working Gemini client.
    Tries API keys one by one until one succeeds.
    """
    last_error = None

    for api_key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=api_key)

            # Lightweight validation call
            client.models.generate_content(
                model=MODEL,
                contents="ping"
            )

            return client

        except Exception as e:
            print(f"Gemini key failed: {api_key[:10]}...")
            last_error = e

    raise Exception(
        f"All Gemini API keys failed. Last error: {last_error}"
    )

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


