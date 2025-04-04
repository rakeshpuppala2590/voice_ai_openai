from fastapi import FastAPI
from src.api.routes import router as api_router

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Voice AI Agent API"}

app.include_router(api_router, prefix="/api/v1")