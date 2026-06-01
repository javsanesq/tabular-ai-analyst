from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tabular_analyst.api import analyses, datasets, evals, health
from tabular_analyst.core.config import get_settings
from tabular_analyst.core.migrations import run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_runtime()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    yield


app = FastAPI(title="Tabular AI Analyst", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(datasets.router)
app.include_router(analyses.router)
app.include_router(evals.router)
if settings.ui_dist_dir.exists():
    app.mount("/", StaticFiles(directory=settings.ui_dist_dir, html=True), name="ui")
