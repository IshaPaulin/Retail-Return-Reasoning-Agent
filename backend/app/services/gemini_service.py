from google import genai
from app.core.config import GEMINI_API_KEYS

MODEL = "gemini-2.5-flash"


def generate_response(prompt: str) -> str:
    """
    Try Gemini API keys one by one.
    If one key fails, move to the next.
    """

    last_error = None

    for api_key in GEMINI_API_KEYS:

        try:
            client = genai.Client(api_key=api_key)

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt
            )

            return response.text

        except Exception as e:
            print(f"Key failed: {api_key[:10]}...")
            print(e)

            last_error = e
            continue

    raise Exception(
        f"All Gemini API keys failed. Last error: {last_error}"
    )