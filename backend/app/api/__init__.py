from fastapi import APIRouter
from backend.app.api.journeys import router as journeys_router
from backend.app.api.discovery import router as discovery_router

api_router = APIRouter()
api_router.include_router(journeys_router, prefix="/journeys", tags=["Journeys"])
api_router.include_router(discovery_router, prefix="/journeys", tags=["Discovery"])
