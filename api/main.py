import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(
    title="TokenScope API",
    description="Profile LLM API payloads. Find the waste. Cut the cost.",
    version="1.0.0",
)

cors_origins_raw = os.environ.get("CORS_ORIGINS", "*")
cors_origins = [o.strip() for o in cors_origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
def root():
    return {"name": "TokenScope API", "version": "1.0.0", "docs": "/docs"}