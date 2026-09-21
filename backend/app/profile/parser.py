import logging
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field

from backend.app.discovery.parser import extract_json_object
from backend.app.schemas.profile import ConceptItem

logger = logging.getLogger(__name__)


class ProfileParsed(BaseModel):
    overall_confidence: Literal["beginner", "intermediate", "advanced", "mixed"] = "intermediate"
    summary: str = Field(..., min_length=10)
    concepts: List[ConceptItem] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


def parse_knowledge_profile(
    raw_text: str,
    topic: str,
    interactions: List[Dict[str, Any]],
) -> ProfileParsed:
    """
    Parses and validates LLM output for Knowledge Profile.
    Falls back to deterministic synthesis from interactions if model output fails.
    """
    data = extract_json_object(raw_text)
    if data:
        try:
            # Normalize confidence
            conf = str(data.get("overall_confidence", "intermediate")).lower().strip()
            if conf not in ["beginner", "intermediate", "advanced", "mixed"]:
                conf = "intermediate"

            # Parse concepts
            concepts = []
            for c in data.get("concepts", []):
                lvl = str(c.get("level", "moderate")).lower().strip()
                if lvl not in ["strong", "moderate", "weak", "unknown"]:
                    lvl = "moderate"
                cat = str(c.get("category", "partially_known")).lower().strip()
                if cat not in ["known", "partially_known", "unknown"]:
                    cat = "partially_known"
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

    # Deterministic fallback synthesis directly from interactions
    logger.info("Using deterministic fallback synthesis for knowledge profile on %s", topic)
    concepts = []
    gaps = []
    misconceptions = []

    for item in interactions:
        target = item.get("concept_target") or "Core Architecture"
        ans = (item.get("learner_answer") or "").lower()
        if "production" in ans or "built" in ans or "strong" in ans or "deployed" in ans:
            concepts.append(
                ConceptItem(
                    name=target,
                    level="strong",
                    category="known",
                    notes="Demonstrated hands-on experience and solid baseline understanding.",
                )
            )
        elif "not used" in ans or "never" in ans or "new" in ans or "uncertain" in ans:
            concepts.append(
                ConceptItem(
                    name=target,
                    level="weak",
                    category="unknown",
                    notes="Self-reported unfamiliarity or emerging comprehension.",
                )
            )
            gaps.append(f"Foundational mechanics of {target}")
        else:
            concepts.append(
                ConceptItem(
                    name=target,
                    level="moderate",
                    category="partially_known",
                    notes="Understands high-level concept but would benefit from architectural depth.",
                )
            )
            gaps.append(f"Production trade-offs and edge cases of {target}")

    if not concepts:
        concepts.append(
            ConceptItem(
                name=f"{topic} Fundamentals",
                level="moderate",
                category="partially_known",
                notes="Initial conceptual baseline established.",
            )
        )
        gaps.append(f"Advanced implementation patterns for {topic}")

    return ProfileParsed(
        overall_confidence="intermediate" if len(gaps) <= 2 else "beginner",
        summary=(
            f"The learner displays familiarity with core conceptual aspects of {topic} "
            f"while identifying key gaps in advanced execution, trade-offs, and edge cases."
        ),
        concepts=concepts,
        misconceptions=misconceptions,
        gaps=gaps,
    )
