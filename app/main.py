from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.routes import router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.database.connection import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
	initialize_database()
	yield

app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.include_router(dashboard_router)
app.include_router(chat_router)