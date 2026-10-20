import logging
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field

from backend.app.discovery.parser import extract_json_object
from backend.app.discovery.state import DiscoveryLearnerState
from backend.app.schemas.profile import ConceptItem

logger = logging.getLogger(__name__)


class ProfileParsed(BaseModel):
    overall_confidence: Literal["beginner", "intermediate", "advanced", "mixed", "unknown"] = "unknown"
    summary: str = Field(..., min_length=10)
    concepts: List[ConceptItem] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    used_fallback: bool = False


def parse_knowledge_profile(
    raw_text: str,
    topic: str,
    interactions: List[Dict[str, Any]],
    learner_state: Optional[DiscoveryLearnerState] = None,
) -> ProfileParsed:
    """
    Parses and validates LLM output for Knowledge Profile.
    If the model output is unusable, falls back to a profile that assigns no knowledge levels
    (nothing is guessed from keywords) and carries over only what discovery recorded.
    """
    data = extract_json_object(raw_text)
    if data:
        try:
            # Normalize confidence
            conf = str(data.get("overall_confidence", "unknown")).lower().strip()
            if conf not in ["beginner", "intermediate", "advanced", "mixed", "unknown"]:
                conf = "unknown"  # an unusable value means "not assessed", never a guessed level

            # Parse concepts
            concepts = []
            for c in data.get("concepts", []):
                lvl = str(c.get("level", "unknown")).lower().strip()
                if lvl not in ["strong", "moderate", "weak", "unknown"]:
                    lvl = "unknown"
                cat = str(c.get("category", "unknown")).lower().strip()
                if cat not in ["known", "partially_known", "unknown"]:
                    cat = "unknown"
                concepts.append(
                    ConceptItem(
                        name=str(c.get("name", "Technical Concept")).strip(),
                        level=lvl,
                        category=cat,
                        notes=str(c.get("notes", "")).strip() or None,
                    )
                )

            misconceptions = [str(m).strip() for m in data.get("misconceptions", []) if str(m).strip()]
            gaps = [str(g).strip() for g in data.get("gaps", []) if str(g).strip()]
            summary = str(data.get("summary", "")).strip()
            if len(summary) < 10:
                summary = f"Synthesized knowledge profile for {topic} based on {len(interactions)} discovery turns."

            return ProfileParsed(
                overall_confidence=conf,
                summary=summary,
                concepts=concepts,
                misconceptions=misconceptions,
                gaps=gaps,
            )
        except Exception as e:
            logger.warning("Pydantic validation failed for Knowledge Profile: %s", e)

    logger.info("Using non-inferential fallback profile for %s", topic)
    return _fallback_profile(topic, learner_state)


def _fallback_profile(topic: str, state: Optional[DiscoveryLearnerState]) -> ProfileParsed:
    summary_parts = ["Automated profile synthesis was unavailable, so no knowledge levels were assigned."]
    gaps: List[str] = []
    misconceptions: List[str] = []
    if state is not None:
        if state.understanding:
            summary_parts.append(f"Learner's understanding as recorded in discovery: {state.understanding.value}")
        if state.intent:
            summary_parts.append(f"Stated goal: {state.intent.value}")
        gaps = [f.value for f in state.gaps]
        misconceptions = [f.value for f in state.misconceptions]

    return ProfileParsed(
        overall_confidence="unknown",
        summary=" ".join(summary_parts),
        concepts=[
            ConceptItem(
                name=topic,
                level="unknown",
                category="unknown",
                notes="Not assessed: profile synthesis was unavailable.",
            )
        ],
        misconceptions=misconceptions,
        gaps=gaps,
        used_fallback=True,
    )
