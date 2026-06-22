from fastapi import FastAPI
from app.auth.routes import router

app=FastAPI()
app.include_router(router)