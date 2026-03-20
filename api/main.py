import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(
    title="TokenScope API",
    description="Profile LLM API payloads. Find the waste. Cut the cost.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url=None,
)

cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"name": "TokenScope API", "version": "0.2.0", "docs": "/docs"}