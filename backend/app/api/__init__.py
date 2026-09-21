from fastapi import APIRouter
from backend.app.api.journeys import router as journeys_router

api_router = APIRouter()
api_router.include_router(journeys_router, prefix="/journeys", tags=["Journeys"])
