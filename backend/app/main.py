from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.config import Settings, get_settings
from backend.app.db.session import engine, Base, check_db_health, ensure_schema_migrations
from backend.app.providers.factory import get_llm_provider
from backend.app.api import api_router
# Ensure models are imported so Base.metadata knows about them
import backend.app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data directory exists
    Path("./data").mkdir(parents=True, exist_ok=True)
    # Create tables if not exist
    Base.metadata.create_all(bind=engine)
    ensure_schema_migrations()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)


@app.get("/health", tags=["System"])
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Health check endpoint returning system status, database connectivity,
    and LLM provider information.
    """
    db_ok = check_db_health()
    provider = get_llm_provider(settings)
    llm_ok = await provider.health_check()

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": "connected" if db_ok else "unreachable",
        "llm_provider": provider.provider_name,
        "llm_model": provider.model_name,
        "llm_healthy": llm_ok,
    }


# Frontend static files
frontend_dir = Path("./frontend")
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", tags=["Frontend"])
    async def serve_index():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Personalized Technical Note Maker API running."}
