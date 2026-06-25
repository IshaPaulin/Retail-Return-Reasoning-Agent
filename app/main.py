from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.auth.routes import router as auth_router


app = FastAPI()
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(chat_router)
