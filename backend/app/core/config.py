from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
SECRET_KEY = os.getenv("SECRET_KEY")

GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
    os.getenv("GEMINI_API_KEY_5"),
    os.getenv("GEMINI_API_KEY_6"),
    os.getenv("GEMINI_API_KEY_7"),
]

GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

FLOOR_THRESHOLD = 0.4       # below this after all retries → serve with disclaimer
CEILING_THRESHOLD = 0.7     # above this → serve immediately, no retry needed
MAX_ATTEMPTS = 3
