import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.app.discovery.parser import extract_json_object
from backend.app.schemas.architecture import SectionBlueprint

logger = logging.getLogger(__name__)


class ArchitectureParsed(BaseModel):
    summary_rationale: str = Field(..., min_length=10)
    sections: List[SectionBlueprint] = Field(..., min_length=3)
    used_fallback: bool = False
    failure_reason: Optional[str] = None


def clean_gap_to_title(gap: str) -> str:
    """Transforms a raw knowledge gap phrase into a natural, authoritative technical title."""
    clean = gap.strip()
    prefixes_to_strip = [
        "concrete understanding of ",
        "factors influencing ",
        "practical application of ",
        "design and implementation of ",
        "design of ",
        "implementation of ",
        "understanding of ",
        "foundations of ",
        "foundational mechanics of ",
        "mechanics of ",
        "knowledge of ",
    ]
    lower = clean.lower()
    for prefix in prefixes_to_strip:
        if lower.startswith(prefix):
            clean = clean[len(prefix):].strip()
            break

    words = clean.split()
    minor_words = {"and", "or", "in", "of", "for", "to", "the", "a", "an", "on", "with", "as", "such"}
    capitalized = " ".join(
        w.capitalize() if w.lower() not in minor_words else w.lower()
        for w in words
    )

    if capitalized:
        capitalized = capitalized[0].upper() + capitalized[1:]
    return capitalized or gap.strip()


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

                title = str(s.get("title", f"Section {idx}")).strip()
                # Clean any unintentional raw prefixes
                if title.lower().startswith("core mechanics: concrete understanding"):
                    title = clean_gap_to_title(title.replace("Core Mechanics:", ""))

                sections.append(
                    SectionBlueprint(
                        order_index=idx,
                        title=title,
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
                    used_fallback=False,
                    failure_reason=None,
                )
        except Exception as e:
            logger.warning("Pydantic validation failed for Note Architecture: %s", e)
            failure_reason = f"Schema validation failed: {e}"
    else:
        failure_reason = "Model output was empty or invalid JSON"

    # Deterministic fallback architecture constructed directly from learner profile
    logger.info("Using deterministic fallback generation for note architecture on %s (reason: %s)", topic, failure_reason)
    sections = []
    curr_idx = 1

    # 1. Orientation & Current Mental Model
    strong_concepts = [c["name"] for c in concepts if c.get("level") == "strong"]
    sections.append(
        SectionBlueprint(
            order_index=curr_idx,
            title=f"{topic}: Foundations & Starting Mental Model",
            section_type="mental_model",
            depth="brief",
            target_concepts=strong_concepts or [topic],
            rationale="Anchors on existing baseline foundations while establishing the precise architectural scope.",
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
                title=f"Mental Model Realignment: Avoiding Pitfalls in {topic}",
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

    # 3. Targeted Deep Dives for Gaps (synthesizing natural technical titles)
    target_gaps = gaps or ["Internal Mechanics", "Operational Trade-offs"]
    for i, raw_gap in enumerate(target_gaps[:3]):
        cleaned_gap = clean_gap_to_title(raw_gap)
        if i == 0:
            sec_title = f"{cleaned_gap}: Internal Mechanics & Architecture"
        elif i == 1:
            sec_title = f"{cleaned_gap}: Strategies & Constraint Dynamics"
        else:
            sec_title = f"{cleaned_gap}: Optimization & Algorithms"

        sections.append(
            SectionBlueprint(
                order_index=curr_idx,
                title=sec_title,
                section_type="deep_dive",
                depth="deep",
                target_concepts=[raw_gap],
                rationale=f"Addresses learner's primary knowledge gap in {cleaned_gap} with rigorous technical depth.",
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
            title=f"Production Implementation & Practical Patterns for {topic}",
            section_type="code_walkthrough",
            depth="deep",
            target_concepts=[topic] + target_gaps[:2],
            rationale="Grounds theoretical mechanics into executable code, real-world patterns, and edge-case handling.",
            needs_code=True,
            needs_visual=False,
            visual_type=None,
        )
    )
    curr_idx += 1

    # 5. Advanced Next Steps / Production Trade-offs
    sections.append(
        SectionBlueprint(
            order_index=curr_idx,
            title=f"Operational Trade-offs, Edge Cases & Next Frontiers in {topic}",
            section_type="bridge",
            depth="brief",
            target_concepts=[f"Next Frontier in {topic}"],
            rationale="Provides continuous learning trajectory, scaling trade-offs, and production considerations.",
            needs_code=False,
            needs_visual=False,
            visual_type=None,
        )
    )

    clean_gaps_summary = ", ".join([clean_gap_to_title(g) for g in target_gaps[:2]])
    return ArchitectureParsed(
        summary_rationale=(
            f"This personalized architecture systematically resolves your identified knowledge gaps in "
            f"{clean_gaps_summary} while bypassing redundant elementary reviews and emphasizing production patterns."
        ),
        sections=sections,
        used_fallback=True,
        failure_reason=failure_reason,
    )
