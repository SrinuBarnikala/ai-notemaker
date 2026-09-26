import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.memory import (
    SearchResponse,
    ConceptProvenance,
    RelatedTopicsResponse,
    NoteMemoryReferencesResponse,
    LearningHistoryJourney,
    KnowledgeMemoryOverview,
)
from backend.app.memory.search_service import search_knowledge_base
from backend.app.memory.memory_service import (
    get_all_concept_memories,
    get_concept_memory,
    get_learning_history,
    get_memory_overview,
    get_related_topics,
    get_note_cross_references,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search", response_model=SearchResponse, tags=["Search & Memory"])
async def search_endpoint(
    q: str = Query(..., min_length=1, description="Search query string"),
    type: str = Query("all", description="Filter result type: all, journey, note, section, concept, code, flashcard"),
    journey_id: Optional[str] = Query(None, description="Optional journey ID filter"),
    limit: int = Query(30, ge=1, le=100, description="Max results to return"),
    db: Session = Depends(get_db),
):
    """
    Phase 15: Universal full-text search across learning journeys, living notes,
    individual sections, knowledge concepts, code snippets, and active recall flashcards.
    """
    return search_knowledge_base(
        db=db,
        query=q,
        result_type=type,
        journey_id=journey_id,
        limit=limit,
    )


@router.get("/memory/overview", response_model=KnowledgeMemoryOverview, tags=["Search & Memory"])
async def memory_overview_endpoint(
    db: Session = Depends(get_db),
):
    """
    Phase 15: Global knowledge memory metrics including total concepts tracked,
    mastered concepts, unresolved gaps, bridging concepts, and recent journey history.
    """
    return get_memory_overview(db=db)


@router.get("/memory/history", response_model=List[LearningHistoryJourney], tags=["Search & Memory"])
async def learning_history_endpoint(
    db: Session = Depends(get_db),
):
    """
    Phase 15: Chronological timeline of all learner journeys with note versioning,
    concept status breakdowns, and mastery assessment scores.
    """
    return get_learning_history(db=db)


@router.get("/memory/concepts", response_model=List[ConceptProvenance], tags=["Search & Memory"])
async def concept_memories_endpoint(
    db: Session = Depends(get_db),
):
    """
    Phase 15: Inventory of all concepts tracked across journeys, showing provenance,
    first encounter journey, appearances count, and current mastery status.
    """
    return get_all_concept_memories(db=db)


@router.get("/memory/concepts/{concept_name}", response_model=ConceptProvenance, tags=["Search & Memory"])
async def single_concept_memory_endpoint(
    concept_name: str = Path(..., description="Concept name to retrieve provenance for"),
    db: Session = Depends(get_db),
):
    """
    Phase 15: Deep provenance and evolution trajectory for a specific technical concept
    (e.g., 'You first encountered reranking while learning RAG Architecture').
    """
    return get_concept_memory(concept_name=concept_name, db=db)


@router.get("/memory/related/{journey_id}", response_model=RelatedTopicsResponse, tags=["Search & Memory"])
async def related_topics_endpoint(
    journey_id: str = Path(..., description="Journey ID to find related topics for"),
    db: Session = Depends(get_db),
):
    """
    Phase 15: Cross-journey related topics recommendations derived from bridging concepts,
    active knowledge gaps, and architectural continuations.
    """
    return get_related_topics(journey_id=journey_id, db=db)


@router.get("/memory/notes/{note_id}/cross-references", response_model=NoteMemoryReferencesResponse, tags=["Search & Memory"])
async def note_cross_references_endpoint(
    note_id: str = Path(..., description="Note ID to find cross-journey memory tags for"),
    db: Session = Depends(get_db),
):
    """
    Phase 15: In-note memory provenance tags connecting concepts within the current note
    to earlier learning journeys.
    """
    return get_note_cross_references(note_id=note_id, db=db)
