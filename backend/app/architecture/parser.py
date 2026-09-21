import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from backend.app.discovery.parser import extract_json_object
from backend.app.schemas.architecture import SectionBlueprint

logger = logging.getLogger(__name__)


class ArchitectureParsed(BaseModel):
    summary_rationale: str = Field(..., min_length=10)
    sections: List[SectionBlueprint] = Field(..., min_length=3)


def parse_note_architecture(
    raw_text: str,
    topic: str,
    profile_summary: str,
    concepts: List[Dict[str, Any]],
    gaps: List[str],
    misconceptions: List[str],
) -> ArchitectureParsed:
    """
    Parses and validates LLM output for Note Architecture.
    Falls back to deterministic personalized generation if model output is malformed.
    """
    data = extract_json_object(raw_text)
    if data:
        try:
            summary_rationale = str(data.get("summary_rationale", "")).strip()
            raw_sections = data.get("sections", [])
            sections = []

            for idx, s in enumerate(raw_sections, start=1):
                depth = str(s.get("depth", "standard")).lower().strip()
                if depth not in ["brief", "standard", "deep"]:
                    depth = "standard"

                target_concepts = [str(tc).strip() for tc in s.get("target_concepts", []) if str(tc).strip()]
                if not target_concepts:
                    target_concepts = [topic]

                v_type = s.get("visual_type")
                if v_type:
                    v_type = str(v_type).strip()
                    if v_type.lower() in ["none", "null", ""]:
                        v_type = None

                sections.append(
                    SectionBlueprint(
                        order_index=idx,
                        title=str(s.get("title", f"Section {idx}")).strip(),
                        section_type=str(s.get("section_type", "deep_dive")).strip(),
                        depth=depth,  # type: ignore
                        target_concepts=target_concepts,
                        rationale=str(s.get("rationale", "Tailored to learner profile.")).strip(),
                        needs_code=bool(s.get("needs_code", False)),
                        needs_visual=bool(s.get("needs_visual", False)),
                        visual_type=v_type,
                    )
                )

            if len(sections) >= 3:
                if len(summary_rationale) < 10:
                    summary_rationale = f"Personalized learning architecture tailored for {topic} based on mapped gaps and strengths."
                return ArchitectureParsed(
                    summary_rationale=summary_rationale,
                    sections=sections,
                )
        except Exception as e:
            logger.warning("Pydantic validation failed for Note Architecture: %s", e)

    # Deterministic fallback architecture constructed directly from learner profile
    logger.info("Using deterministic fallback generation for note architecture on %s", topic)
    sections = []
    curr_idx = 1

    # 1. Orientation & Current Mental Model
    strong_concepts = [c["name"] for c in concepts if c.get("level") == "strong"]
    sections.append(
        SectionBlueprint(
            order_index=curr_idx,
            title=f"{topic} in One Sentence & Your Starting Mental Model",
            section_type="mental_model",
            depth="brief",
            target_concepts=strong_concepts or [topic],
            rationale="Respects existing strong foundations while framing the scope of the note.",
            needs_code=False,
            needs_visual=True,
            visual_type="flowchart",
        )
    )
    curr_idx += 1

    # 2. Misconceptions reset if any
    if misconceptions:
        sections.append(
            SectionBlueprint(
                order_index=curr_idx,
                title="Mental Model Realignment & Common Misconceptions",
                section_type="pitfall_warning",
                depth="standard",
                target_concepts=[topic],
                rationale="Directly clarifies identified misconceptions before deeper technical exploration.",
                needs_code=False,
                needs_visual=True,
                visual_type="comparison_table",
            )
        )
        curr_idx += 1

    # 3. Targeted Deep Dives for Gaps and Weak/Moderate concepts
    target_gaps = gaps or ["Internal Mechanics", "Edge Cases & Trade-offs"]
    for gap_title in target_gaps[:3]:
        sections.append(
            SectionBlueprint(
                order_index=curr_idx,
                title=f"Core Mechanics: {gap_title}",
                section_type="deep_dive",
                depth="deep",
                target_concepts=[gap_title],
                rationale=f"Addresses learner's primary knowledge gap in {gap_title} with granular depth.",
                needs_code=False,
                needs_visual=True,
                visual_type="architecture_diagram",
            )
        )
        curr_idx += 1

    # 4. End-to-End Practical Implementation
    sections.append(
        SectionBlueprint(
            order_index=curr_idx,
            title=f"Practical Implementation & Production Patterns for {topic}",
            section_type="code_walkthrough",
            depth="deep",
            target_concepts=[topic] + target_gaps[:2],
            rationale="Grounds the theoretical understanding into executable code and real-world patterns.",
            needs_code=True,
            needs_visual=False,
            visual_type=None,
        )
    )
    curr_idx += 1

    # 5. Advanced Next Steps
    sections.append(
        SectionBlueprint(
            order_index=curr_idx,
            title="Advanced Concepts to Master Next",
            section_type="bridge",
            depth="brief",
            target_concepts=[f"Next Frontier in {topic}"],
            rationale="Provides continuous learning trajectory once the immediate gaps are bridged.",
            needs_code=False,
            needs_visual=False,
            visual_type=None,
        )
    )

    return ArchitectureParsed(
        summary_rationale=(
            f"This personalized architecture specifically isolates your identified gaps in {', '.join(target_gaps[:2])} "
            f"while skipping redundant elementary explanations and prioritizing hands-on execution."
        ),
        sections=sections,
    )
