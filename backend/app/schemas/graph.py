from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field, ConfigDict


class GraphNode(BaseModel):
    id: str
    name: str
    status: Literal["known", "partial", "gap", "misconception"] = "known"
    journey_id: Optional[str] = None
    journey_topic: Optional[str] = None
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    depth: Optional[str] = "standard"
    size: int = 22
    group: Optional[str] = "concept"
    summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: Literal["prerequisite", "subconcept", "compares_to", "implements", "relates_to"] = "prerequisite"
    label: Optional[str] = None
    weight: float = 1.0

    model_config = ConfigDict(from_attributes=True)


class ConceptGraphResponse(BaseModel):
    journey_id: Optional[str] = None
    title: str
    is_global: bool = False
    total_nodes: int = 0
    total_edges: int = 0
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    summary: str = ""
    mastery_breakdown: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
