"""FastAPI entry point for the local timetable-data prototype."""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401 - imports register models with Base.metadata
from app.database import engine, initialize_schema
from app.routes import api_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Validate the existing schema; creation and migration are explicit commands."""
    initialize_schema(engine)
    yield


app = FastAPI(
    title="AI College Timetable Generator API",
    version="0.2.0",
    description=(
        "Local academic-data API foundation. This prototype has no authentication; "
        "do not expose it publicly."
    ),
    lifespan=lifespan,
)

# Local development only. Authentication is intentionally out of scope for this prototype.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "TIMETABLE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(","),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(api_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok"}
