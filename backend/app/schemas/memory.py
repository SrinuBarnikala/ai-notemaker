from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    id: str = Field(..., description="Unique identifier for the result item")
    result_type: str = Field(..., description="Type of result: 'journey', 'note', 'section', 'concept', 'code', 'flashcard'")
    title: str = Field(..., description="Display title of the item")
    subtitle: Optional[str] = Field(None, description="Subtitle or category")
    snippet: str = Field(..., description="Matching text excerpt with context")
    journey_id: Optional[str] = Field(None, description="Associated journey ID if applicable")
    journey_topic: Optional[str] = Field(None, description="Associated journey topic if applicable")
    note_id: Optional[str] = Field(None, description="Associated note ID if applicable")
    section_id: Optional[str] = Field(None, description="Associated note section ID if applicable")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional item-specific metadata")


class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResultItem]
    filters_applied: Dict[str, Any] = Field(default_factory=dict)


class ConceptEvolutionStep(BaseModel):
    journey_id: str
    journey_topic: str
    timestamp: datetime
    category: str  # 'known', 'partially_known', 'gap', 'misconception'
    level: str  # 'strong', 'moderate', 'weak', 'unknown'
    context_note: Optional[str] = None
    event_type: str  # 'discovery', 'assessment_mastered', 'note_evolution'


class ConceptProvenance(BaseModel):
    concept_name: str
    first_encountered_journey_id: str
    first_encountered_journey_topic: str
    first_encountered_at: datetime
    first_encountered_category: str  # e.g., 'gap'
    current_status: str  # 'mastered', 'known', 'gap', 'misconception'
    total_appearances: int
    provenance_story: str  # e.g. "You first encountered 'reranking' while learning RAG Architecture..."
    history: List[ConceptEvolutionStep] = Field(default_factory=list)
    linked_note_ids: List[str] = Field(default_factory=list)
    related_concepts: List[str] = Field(default_factory=list)


class RelatedTopicItem(BaseModel):
    topic: str
    reason: str
    relationship_type: str  # 'builds_on_gap', 'shared_prerequisite', 'logical_next_step'
    bridging_concepts: List[str] = Field(default_factory=list)
    existing_journey_id: Optional[str] = None
    existing_note_id: Optional[str] = None


class RelatedTopicsResponse(BaseModel):
    journey_id: str
    journey_topic: str
    related_topics: List[RelatedTopicItem]
    bridging_concepts: List[str]


class CrossReferenceTag(BaseModel):
    concept_name: str
    provenance_story: str
    first_journey_id: str
    first_journey_topic: str
    first_encountered_at: datetime
    current_status: str
    section_id: Optional[str] = None
    section_title: Optional[str] = None


class NoteMemoryReferencesResponse(BaseModel):
    note_id: str
    journey_id: str
    cross_references: List[CrossReferenceTag]
    total_memory_bridges: int


class LearningHistoryJourney(BaseModel):
    id: str
    topic: str
    status: str
    created_at: datetime
    updated_at: datetime
    note_id: Optional[str] = None
    note_version: Optional[int] = None
    total_sections: int = 0
    total_concepts: int = 0
    concepts_mastered: int = 0
    concepts_gap: int = 0
    concept_names: List[str] = Field(default_factory=list)
    latest_quiz_score: Optional[str] = None


class KnowledgeMemoryOverview(BaseModel):
    total_journeys: int
    total_notes: int
    total_concepts_tracked: int
    total_concepts_mastered: int
    total_knowledge_gaps: int
    total_misconceptions: int
    top_bridging_concepts: List[Dict[str, Any]] = Field(default_factory=list)
    recent_history: List[LearningHistoryJourney] = Field(default_factory=list)
