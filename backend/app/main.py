import os
import sys
from fastapi import FastAPI

# Ensure the backend directory is on sys.path so `from app.*` imports work
# when running from the repo root as `uvicorn backend.app.main:app`.
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.auth.routes import router as auth_router


app = FastAPI()
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(chat_router)
