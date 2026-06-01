"""FastAPI entry-point for the Outlet Intelligence web app.

Run locally:
    cd webapp/backend
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

The app loads gold parquets / audit CSVs into memory once at startup and
exposes the data through JSON endpoints. CORS is open in local dev so the
Next.js frontend on :3000 can call it directly.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Always load the .env that lives next to this file, regardless of CWD.
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

from .routers import outlets as outlets_router       # noqa: E402
from .routers import dashboards as dash_router       # noqa: E402
from .routers import xai as xai_router               # noqa: E402
from .services.data_loader import get_cache          # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = get_cache()
    print(f"[startup] Repo root: {cache.repo_root}")
    print(f"[startup] outlets table: {cache.outlets_table.shape}")
    print(f"[startup] predictions:   {cache.predictions.shape}")
    print(f"[startup] dormancy:      {cache.dormancy.shape}")
    yield


app = FastAPI(
    title="Outlet Intelligence API",
    version="0.1.0",
    description="Beverage outlet potential, budget allocation, and XAI narratives.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(outlets_router.router)
app.include_router(dash_router.router)
app.include_router(xai_router.router)


@app.get("/")
def root():
    return {
        "service": "Outlet Intelligence API",
        "endpoints": [
            "GET  /api/summary",
            "GET  /api/outlets",
            "GET  /api/outlets/filters",
            "GET  /api/outlets/{outlet_id}",
            "POST /api/xai/explain/{outlet_id}",
            "GET  /api/budget/distributors",
            "GET  /api/budget/channels",
            "GET  /api/budget/outlets",
            "GET  /api/cooler-roi/top100",
            "GET  /api/cooler-roi/summary",
            "GET  /api/dormancy/top",
            "GET  /api/dormancy/bands",
            "GET  /api/scorecard",
            "GET  /api/territories",
            "GET  /api/forensics",
            "GET  /api/shap/global",
        ],
    }
