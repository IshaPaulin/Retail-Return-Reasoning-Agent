from fastapi import FastAPI
from backend.app.auth.routes import router

app=FastAPI()
app.include_router(router)