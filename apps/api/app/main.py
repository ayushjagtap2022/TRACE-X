import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, schema, fraud
from app.core.config import settings

ROOT_DIR = Path(__file__).resolve().parents[3]
AI_ML_DIR = ROOT_DIR / "apps" / "ai-ml"
if str(AI_ML_DIR) not in sys.path:
    sys.path.append(str(AI_ML_DIR))

from fraud_detector import (
    score_account,
    detect_layering,
    get_account_ids,
    explain_dormant,
    explain_smurfing,
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(schema.router, prefix=settings.API_V1_STR)
app.include_router(fraud.router, prefix=settings.API_V1_STR)


@app.get("/")
def read_root():
    return {"message": "Welcome to the TRACE-X Platform API"}
