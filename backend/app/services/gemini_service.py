import google.generativeai as genai
from app.core.config import GEMINI_API_KEYS

def generate_response(prompt):

    last_error = None

    for api_key in GEMINI_API_KEYS:

        try:
            genai.configure(api_key=api_key)

            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash"
            )

            response = model.generate_content(prompt)

            return response.text

        except Exception as e:
            print(f"Key failed: {api_key[:10]}...")
            print(e)

            last_error = e
            continue

    raise Exception(
        f"All Gemini API keys failed. Last error: {last_error}"
    )