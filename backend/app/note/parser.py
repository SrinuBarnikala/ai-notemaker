import json
import logging
import re
from typing import List, Dict, Any, Optional
from backend.app.schemas.note import NoteBlock
from backend.app.visuals.sanitizer import sanitize_mermaid_spec, generate_fallback_mermaid

logger = logging.getLogger(__name__)


class ParsedBlocksList(list):
    """List of NoteBlock objects with generation observability metadata."""
    def __init__(self, iterable=(), used_fallback: bool = False, failure_reason: Optional[str] = None):
        super().__init__(iterable)
        self.used_fallback = used_fallback
        self.failure_reason = failure_reason


def extract_json_array_or_object(text: str) -> Any:
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if match:
        clean = match.group(1).strip()

    # Check for object with "blocks" key first
    start_obj = clean.find("{")
    end_obj = clean.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        candidate = clean[start_obj : end_obj + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "blocks" in parsed:
                return parsed["blocks"]
            return parsed
        except json.JSONDecodeError:
            pass

    # Check for direct array
    start_arr = clean.find("[")
    end_arr = clean.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        candidate = clean[start_arr : end_arr + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict) and "blocks" in parsed:
            return parsed["blocks"]
        return parsed
    except json.JSONDecodeError:
        return None


def parse_section_blocks(
    raw_text: str,
    section_title: str,
    section_type: str,
    depth: str,
    target_concepts: List[str],
    rationale: str,
    needs_code: bool,
    needs_visual: bool,
    visual_type: str = None,
    topic: str = "Systems Engineering",
) -> ParsedBlocksList:
    """
    Parses and validates LLM output into structured NoteBlock objects.
    Falls back to topic-neutral structured blocks if LLM output fails validation.
    """
    data = extract_json_array_or_object(raw_text)
    failure_reason = None

    if data:
        raw_items = data if isinstance(data, list) else (data.get("blocks") if isinstance(data, dict) else None)
        if isinstance(raw_items, list) and len(raw_items) > 0:
            parsed_blocks = []
            valid_types = {"paragraph", "definition", "example", "code", "warning", "comparison", "diagram"}

            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                b_type = str(item.get("type", "paragraph")).lower().strip()
                if b_type not in valid_types:
                    b_type = "paragraph"

                content = item.get("content")
                term = item.get("term")
                code_snippet = item.get("code")
                diag_spec = item.get("diagram_spec")

                # Sanitize Mermaid if diagram block
                if b_type == "diagram" and diag_spec:
                    diag_spec = sanitize_mermaid_spec(diag_spec, fallback_title=section_title)

                # Ensure minimum valid content
                if b_type == "paragraph" and not content:
                    continue
                if b_type == "definition" and not (content or term):
                    continue
                if b_type == "code" and not code_snippet:
                    continue

                try:
                    parsed_blocks.append(
                        NoteBlock(
                            type=b_type,  # type: ignore
                            content=content,
                            term=term,
                            language=item.get("language") or ("python" if b_type == "code" else None),
                            code=code_snippet,
                            title=item.get("title"),
                            caption=item.get("caption"),
                            diagram_spec=diag_spec,
                            diagram_type=item.get("diagram_type") or (visual_type if b_type == "diagram" else None),
                            items=item.get("items"),
                        )
                    )
                except Exception as e:
                    logger.warning("Block validation failed: %s", e)

            if parsed_blocks:
                return ParsedBlocksList(parsed_blocks, used_fallback=False, failure_reason=None)
            else:
                failure_reason = "No valid blocks satisfied schema constraints"
        else:
            failure_reason = "Extracted JSON did not contain a non-empty array of blocks"
    else:
        failure_reason = "Output was empty or not parseable as JSON"

    # Deterministic topic-neutral fallback blocks
    logger.info("Using deterministic fallback blocks for section '%s' (reason: %s)", section_title, failure_reason)
    blocks = []
    primary_concept = target_concepts[0] if target_concepts else section_title

    # 1. Conceptual Introduction Paragraph
    blocks.append(
        NoteBlock(
            type="paragraph",
            content=(
                f"**{section_title}** establishes key architectural mechanisms within {topic}. "
                f"{rationale} Understanding its operational boundaries and state transitions is essential "
                f"for resilient systems design."
            ),
        )
    )

    # 2. Add Definition block for deep dive or mental model
    if section_type in ["mental_model", "deep_dive"]:
        blocks.append(
            NoteBlock(
                type="definition",
                term=primary_concept,
                content=(
                    f"The core technical principles, operational parameters, and behavioral guarantees defining "
                    f"{primary_concept} within the end-to-end architecture."
                ),
            )
        )

    # 3. Add Warning & Comparison block for pitfall warning
    if section_type == "pitfall_warning":
        blocks.append(
            NoteBlock(
                type="warning",
                title=f"Critical Constraint Management in {primary_concept}",
                content=(
                    f"A frequent pitfall is assuming default resource allocations scale linearly without establishing "
                    f"explicit boundaries, backpressure limits, and fallback invariants."
                ),
            )
        )
        blocks.append(
            NoteBlock(
                type="comparison",
                title=f"{primary_concept}: Baseline vs Production Patterns",
                content="Key operational trade-offs and behavioral differences:",
                items=[
                    {"dimension": "Constraint Management", "Naive Baseline": "Unbounded / unvalidated", "Engineered Pattern": "Explicit thresholds and backpressure"},
                    {"dimension": "State Lifecycle", "Naive Baseline": "Volatile, implicit state", "Engineered Pattern": "Deterministic synchronization and checkpoints"},
                    {"dimension": "Failure Handling", "Naive Baseline": "Unhandled degradation", "Engineered Pattern": "Circuit-breaking and telemetry"},
                ],
            )
        )

    # 4. Add Visual Diagram if requested
    if needs_visual:
        v_type = visual_type or "architecture_diagram"
        diag_title = f"{primary_concept} Architecture & Data Flow"
        blocks.append(
            NoteBlock(
                type="diagram",
                title=diag_title,
                caption=f"Visual representation of component boundaries and data transitions for {primary_concept}.",
                diagram_spec=generate_fallback_mermaid(v_type, primary_concept),
                diagram_type=v_type,
                visual_description=f"System diagram illustrating data transformations for {primary_concept}.",
            )
        )

    # 5. Add Code block if requested or if walkthrough
    if needs_code or section_type == "code_walkthrough":
        clean_name = "".join(w.capitalize() for w in re.sub(r"[^a-zA-Z0-9 ]", "", primary_concept).split()) or "Core"
        blocks.append(
            NoteBlock(
                type="code",
                language="python",
                title=f"Production Pattern: {primary_concept}",
                code=(
                    f"from typing import Dict, Any\n\n"
                    f"class {clean_name}Controller:\n"
                    f"    \"\"\"\n"
                    f"    Manages operational lifecycle and state invariants for {primary_concept}.\n"
                    f"    \"\"\"\n"
                    f"    def __init__(self, capacity_limit: int = 1000):\n"
                    f"        self.capacity_limit = capacity_limit\n"
                    f"        self._active_state: Dict[str, Any] = {{}}\n\n"
                    f"    def process_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:\n"
                    f"        if not payload:\n"
                    f"            raise ValueError('Context payload cannot be empty')\n"
                    f"        # Verify operational bounds and execute state transformation\n"
                    f"        processed = {{'status': 'applied', 'concept': '{primary_concept}', 'data': payload}}\n"
                    f"        return processed\n"
                ),
            )
        )

    # 6. Deep Dive Detail Paragraph
    if depth == "deep":
        blocks.append(
            NoteBlock(
                type="example",
                title="Production Engineering Consideration",
                content=(
                    f"When operating {primary_concept} at scale, monitor resource utilization and latency profiles. "
                    f"Establish proactive circuit breakers and bounded limits to prevent cascading failures under heavy load."
                ),
            )
        )

    return ParsedBlocksList(blocks, used_fallback=True, failure_reason=failure_reason)
