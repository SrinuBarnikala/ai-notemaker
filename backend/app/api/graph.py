import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.config import Settings, get_settings
from backend.app.schemas.graph import ConceptGraphResponse
from backend.app.providers.factory import get_llm_provider
from backend.app.graph.builder import (
    build_journey_concept_graph,
    build_global_concept_graph,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/journeys/{journey_id}/graph",
    response_model=ConceptGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Get interactive concept dependency graph for a journey",
)
async def get_journey_graph_endpoint(
    journey_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    provider = get_llm_provider(settings)
    return await build_journey_concept_graph(journey_id, db, provider)


@router.get(
    "/graph/global",
    response_model=ConceptGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cross-journey global technical knowledge graph",
)
def get_global_graph_endpoint(
    db: Session = Depends(get_db),
):
    return build_global_concept_graph(db)
