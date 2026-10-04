import logging
import re
from typing import List, Dict, Any, Optional
from backend.app.schemas.note import NoteBlock
from backend.app.visuals.sanitizer import sanitize_mermaid_spec, generate_fallback_mermaid
from backend.app.core.json_utils import strip_code_fence, find_bracket_span, try_parse_json

logger = logging.getLogger(__name__)


class ParsedBlocksList(list):
    """List of NoteBlock objects with generation observability metadata."""
    def __init__(self, iterable=(), used_fallback: bool = False, failure_reason: Optional[str] = None):
        super().__init__(iterable)
        self.used_fallback = used_fallback
        self.failure_reason = failure_reason


def extract_json_array_or_object(text: str) -> Any:
    clean = strip_code_fence(text)

    arr_span = find_bracket_span(clean, "[", "]")
    obj_span = find_bracket_span(clean, "{", "}")

    # If array starts before object, prioritize parsing outer array
    if arr_span and (obj_span is None or arr_span[0] < obj_span[0]):
        parsed = try_parse_json(clean[arr_span[0] : arr_span[1] + 1])
        if isinstance(parsed, list):
            return parsed

    # Check for object with "blocks" key or single block
    if obj_span:
        parsed = try_parse_json(clean[obj_span[0] : obj_span[1] + 1])
        if parsed is not None:
            if isinstance(parsed, dict):
                if "blocks" in parsed:
                    return parsed["blocks"]
                if "type" in parsed:
                    return [parsed]
            return parsed

    # Check for direct array
    if arr_span:
        parsed = try_parse_json(clean[arr_span[0] : arr_span[1] + 1])
        if parsed is not None:
            return parsed

    parsed = try_parse_json(clean)
    if isinstance(parsed, dict):
        if "blocks" in parsed:
            return parsed["blocks"]
        if "type" in parsed:
            return [parsed]
    return parsed


def parse_markdown_table_to_items(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parses a Markdown pipe table into a list of dictionaries.
    e.g.
    | Metric | Approach A | Approach B |
    | --- | --- | --- |
    | Latency | 5ms | 200ms |
    """
    if not text or "|" not in text:
        return None

    clean_text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    lines = [line.strip() for line in clean_text.strip().splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") or line.endswith("|") or "|" in line]
    if len(table_lines) < 2:
        return None

    # Find the separator row (e.g. |---|---| or |:---:|---:|)
    sep_idx = -1
    for idx, line in enumerate(table_lines):
        clean = line.replace("|", "").replace(":", "").replace("-", "").replace(" ", "").strip()
        if clean == "" and "-" in line:
            sep_idx = idx
            break

    if sep_idx < 1 or sep_idx >= len(table_lines):
        return None

    def split_row(row_str: str) -> List[str]:
        clean = row_str.strip()
        if clean.startswith("|"):
            clean = clean[1:]
        if clean.endswith("|"):
            clean = clean[:-1]
        return [c.strip() for c in clean.split("|")]

    headers = split_row(table_lines[sep_idx - 1])
    if not headers or all(not h for h in headers):
        return None

    items = []
    for line in table_lines[sep_idx + 1:]:
        cells = split_row(line)
        if not any(cells):
            continue
        row_dict = {}
        for i, header in enumerate(headers):
            val = cells[i] if i < len(cells) else ""
            row_dict[header] = val
        if row_dict:
            items.append(row_dict)

    return items if items else None


def sanitize_latex_text(text: Optional[str]) -> Optional[str]:
    """Sanitizes unescaped ASCII control characters (such as form feed \x0c) and restores missing LaTeX backslashes."""
    if not text:
        return text
    # 1. Recover form feed control characters (0x0C / \f) resulting from unescaped \frac in JSON strings
    text = text.replace('\x0c', '\\f').replace('\f', '\\f')

    # 2. Inside math delimiters ($...$ or $$...$$), restore missing backslashes for common LaTeX commands
    math_commands = [
        'frac', 'partial', 'leftarrow', 'rightarrow', 'Leftarrow', 'Rightarrow',
        'sum', 'prod', 'int', 'infty', 'nabla', 'cdot', 'times',
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta',
        'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma',
        'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega',
        'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Phi', 'Psi', 'Omega',
        'dots', 'ldots', 'cdots', 'approx', 'neq', 'leq', 'geq', 'in', 'subset',
        'forall', 'exists', 'to', 'mapsto'
    ]
    cmd_pattern = r'(?<!\\)(?<![a-zA-Z])(' + '|'.join(math_commands) + r')(?![a-zA-Z])'

    def fix_math_block(match):
        inner_content = match.group(1)
        fixed_inner = re.sub(cmd_pattern, r'\\\1', inner_content)
        delim = match.group(0)[0:2] if match.group(0).startswith('$$') else '$'
        return f"{delim}{fixed_inner}{delim}"

    text = re.sub(r'\$\$([\s\S]*?)\$\$', fix_math_block, text)
    text = re.sub(r'(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)', fix_math_block, text)
    return text


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
    preferred_language: str = "python",
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

                # Sanitize LaTeX formatting in non-code content and terms
                if b_type != "code" and content:
                    content = sanitize_latex_text(content)
                if term:
                    term = sanitize_latex_text(term)

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

                items = item.get("items")
                if b_type == "comparison":
                    if (not items or len(items) == 0) and content:
                        parsed_items = parse_markdown_table_to_items(content)
                        if parsed_items:
                            items = parsed_items

                try:
                    parsed_blocks.append(
                        NoteBlock(
                            type=b_type,  # type: ignore
                            content=content,
                            term=term,
                            language=item.get("language") or (preferred_language if b_type == "code" else None),
                            code=code_snippet,
                            title=item.get("title"),
                            caption=item.get("caption"),
                            diagram_spec=diag_spec,
                            diagram_type=item.get("diagram_type") or (visual_type if b_type == "diagram" else None),
                            items=items,
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
        lang_lower = (preferred_language or "python").lower()

        if lang_lower in ["cpp", "c++"]:
            code_text = (
                f"#include <iostream>\n"
                f"#include <string>\n"
                f"#include <stdexcept>\n\n"
                f"class {clean_name}Controller {{\n"
                f"private:\n"
                f"    int capacity_limit;\n\n"
                f"public:\n"
                f"    explicit {clean_name}Controller(int limit = 1000) : capacity_limit(limit) {{}}\n\n"
                f"    void processPayload(const std::string& payload) {{\n"
                f"        if (payload.empty()) {{\n"
                f"            throw std::invalid_argument(\"Context payload cannot be empty\");\n"
                f"        }}\n"
                f"        std::cout << \"Executing {primary_concept} with capacity: \" << capacity_limit << std::endl;\n"
                f"    }}\n"
                f"}};\n"
            )
            fallback_lang = "cpp"
        elif lang_lower in ["rust", "rs"]:
            code_text = (
                f"pub struct {clean_name}Controller {{\n"
                f"    pub capacity_limit: usize,\n"
                f"}}\n\n"
                f"impl {clean_name}Controller {{\n"
                f"    pub fn new(capacity_limit: usize) -> Self {{\n"
                f"        Self {{ capacity_limit }}\n"
                f"    }}\n\n"
                f"    pub fn process(&self, payload: &str) -> Result<(), &'static str> {{\n"
                f"        if payload.is_empty() {{\n"
                f"            return Err(\"Payload cannot be empty\");\n"
                f"        }}\n"
                f"        println!(\"Processing {primary_concept}...\");\n"
                f"        Ok(())\n"
                f"    }}\n"
                f"}}\n"
            )
            fallback_lang = "rust"
        elif lang_lower in ["go", "golang"]:
            code_text = (
                f"package main\n\n"
                f"import (\n"
                f"    \"errors\"\n"
                f"    \"fmt\"\n"
                f")\n\n"
                f"type {clean_name}Controller struct {{\n"
                f"    CapacityLimit int\n"
                f"}}\n\n"
                f"func New{clean_name}Controller(limit int) *{clean_name}Controller {{\n"
                f"    return &{clean_name}Controller{{CapacityLimit: limit}}\n"
                f"}}\n\n"
                f"func (c *{clean_name}Controller) Process(payload string) error {{\n"
                f"    if payload == \"\" {{\n"
                f"        return errors.New(\"payload cannot be empty\")\n"
                f"    }}\n"
                f"    fmt.Printf(\"Processing {primary_concept}...\\n\")\n"
                f"    return nil\n"
                f"}}\n"
            )
            fallback_lang = "go"
        else:
            code_text = (
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
            )
            fallback_lang = "python"

        blocks.append(
            NoteBlock(
                type="code",
                language=fallback_lang,
                title=f"Production Pattern: {primary_concept}",
                code=code_text,
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
