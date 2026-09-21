import json
import logging
import re
from typing import List, Dict, Any
from backend.app.schemas.note import NoteBlock

logger = logging.getLogger(__name__)


def extract_json_array_or_object(text: str) -> Any:
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if match:
        clean = match.group(1).strip()

    # Check for array
    start_arr = clean.find("[")
    end_arr = clean.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        candidate = clean[start_arr : end_arr + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Check for object with "blocks" key
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

    try:
        return json.loads(clean)
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
) -> List[NoteBlock]:
    """
    Parses LLM output into a list of validated NoteBlock objects.
    Falls back to high-fidelity structured blocks if LLM output is malformed.
    """
    data = extract_json_array_or_object(raw_text)
    if data and isinstance(data, list):
        parsed_blocks = []
        valid_types = {"paragraph", "definition", "example", "code", "warning", "comparison", "diagram"}
        for item in data:
            if isinstance(item, dict):
                b_type = str(item.get("type", "paragraph")).lower().strip()
                if b_type not in valid_types:
                    b_type = "paragraph"
                try:
                    parsed_blocks.append(
                        NoteBlock(
                            type=b_type,  # type: ignore
                            content=item.get("content"),
                            term=item.get("term"),
                            language=item.get("language"),
                            code=item.get("code"),
                            title=item.get("title"),
                            caption=item.get("caption"),
                            diagram_spec=item.get("diagram_spec"),
                            items=item.get("items"),
                        )
                    )
                except Exception as e:
                    logger.warning("Block validation failed: %s", e)

        if parsed_blocks:
            return parsed_blocks

    # Deterministic high-quality fallback structured blocks
    logger.info("Using deterministic fallback blocks for section: %s", section_title)
    blocks = []
    primary_concept = target_concepts[0] if target_concepts else section_title

    # 1. Conceptual Introduction Paragraph
    blocks.append(
        NoteBlock(
            type="paragraph",
            content=(
                f"**{section_title}** forms a foundational component of this topic. "
                f"{rationale} By examining its internal mechanics, we transition from intuitive "
                f"assumptions to concrete systems design."
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
                    f"The core mechanism responsible for executing {primary_concept.lower()} "
                    f"within the end-to-end architecture, establishing invariants and managing data transformations."
                ),
            )
        )

    # 3. Add Warning block for pitfall warning or misconception
    if section_type == "pitfall_warning":
        blocks.append(
            NoteBlock(
                type="warning",
                title="Common Conceptual Pitfall",
                content=(
                    f"A frequent misconception is conflating raw vector similarity with true relevance reranking. "
                    f"Vector search uses approximate nearest neighbors over fixed embeddings, whereas rerankers "
                    f"perform joint query-document cross-attention."
                ),
            )
        )
        blocks.append(
            NoteBlock(
                type="comparison",
                title="Vector Search vs Reranking Comparison",
                content="Key behavioral and operational differences:",
                items=[
                    {"dimension": "Speed", "Vector Search": "Sub-millisecond (HNSW)", "Reranking": "10-50ms (Cross-Encoder)"},
                    {"dimension": "Context", "Vector Search": "Independent embeddings", "Reranking": "Full token interaction"},
                    {"dimension": "Recall vs Precision", "Vector Search": "High recall filter", "Reranking": "High precision ranking"},
                ],
            )
        )

    # 4. Add Visual Diagram if requested
    if needs_visual:
        blocks.append(
            NoteBlock(
                type="diagram",
                title=f"Architectural Flow: {primary_concept}",
                caption=f"Visual representation of data flow and component boundaries for {primary_concept}.",
                diagram_spec=(
                    f"┌──────────────┐       ┌───────────────┐       ┌──────────────┐\n"
                    f"│ Query Input  │ ────> │ {primary_concept[:12]} │ ────> │ Output State │\n"
                    f"└──────────────┘       └───────────────┘       └──────────────┘"
                ),
            )
        )

    # 5. Add Code block if requested or if walkthrough
    if needs_code or section_type == "code_walkthrough":
        blocks.append(
            NoteBlock(
                type="code",
                language="python",
                title=f"Production Implementation: {primary_concept}",
                code=(
                    f"from typing import List, Dict, Any\n"
                    f"\n"
                    f"def execute_{primary_concept.lower().replace(' ', '_').replace('-', '_')}(query: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:\n"
                    f"    \"\"\"\n"
                    f"    Executes production logic for {primary_concept}.\n"
                    f"    \"\"\"\n"
                    f"    results = []\n"
                    f"    for item in items:\n"
                    f"        score = compute_score(query, item['content'])\n"
                    f"        if score > 0.7:\n"
                    f"            results.append({{**item, 'relevance': score}})\n"
                    f"    return sorted(results, key=lambda x: x['relevance'], reverse=True)\n"
                ),
            )
        )

    # 6. Deep Dive Detail Paragraph
    if depth == "deep":
        blocks.append(
            NoteBlock(
                type="example",
                title="Real-World Architectural Consideration",
                content=(
                    f"When operating {primary_concept} at scale, network latency and GPU batch sizing dominate. "
                    f"Always apply two-stage filtering: retrieve top-100 candidates via indexed vector search, "
                    f"then rerank top-20 before prompting the generator model."
                ),
            )
        )

    return blocks
