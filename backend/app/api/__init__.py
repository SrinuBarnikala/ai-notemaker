from fastapi import APIRouter
from backend.app.api.journeys import router as journeys_router
from backend.app.api.discovery import router as discovery_router
from backend.app.api.profile import router as profile_router
from backend.app.api.architecture import router as architecture_router
from backend.app.api.note import router as note_router
from backend.app.api.assessment import router as assessment_router
from backend.app.api.visuals import router as visuals_router
from backend.app.api.code import router as code_router
from backend.app.api.copilot import router as copilot_router

api_router = APIRouter()
api_router.include_router(journeys_router, prefix="/journeys", tags=["Journeys"])
api_router.include_router(discovery_router, prefix="/journeys", tags=["Discovery"])
api_router.include_router(profile_router, prefix="/journeys", tags=["Knowledge Profile"])
api_router.include_router(architecture_router, prefix="/journeys", tags=["Note Architecture"])
api_router.include_router(note_router)
api_router.include_router(assessment_router)
api_router.include_router(visuals_router)
api_router.include_router(code_router)
api_router.include_router(copilot_router)

