import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.config import Settings, get_settings
from backend.app.schemas.copilot import (
    CopilotQueryRequest,
    CopilotQueryResponse,
    PinAnswerRequest,
    PinAnswerResponse,
)
from backend.app.providers.factory import get_llm_provider
from backend.app.copilot.agent import (
    ask_copilot,
    pin_copilot_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/copilot/ask",
    response_model=CopilotQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask Agent 9 Socratic In-Note Copilot for contextual explanation",
)
async def ask_copilot_endpoint(
    journey_id: str,
    request: CopilotQueryRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    provider = get_llm_provider(settings)
    return await ask_copilot(journey_id, request, db, provider)


@router.post(
    "/journeys/{journey_id}/copilot/pin",
    response_model=PinAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Pin a Copilot answer directly into the living note as a structured block",
)
def pin_copilot_endpoint(
    journey_id: str,
    request: PinAnswerRequest,
    db: Session = Depends(get_db),
):
    return pin_copilot_answer(journey_id, request, db)
