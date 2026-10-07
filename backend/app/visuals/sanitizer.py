import re
import logging
from typing import Optional, Dict, Any
from backend.app.core.json_utils import strip_code_fence, find_bracket_span, try_parse_json

logger = logging.getLogger(__name__)

MERMAID_KEYWORDS = (
    "graph ",
    "graph\n",
    "flowchart ",
    "flowchart\n",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "mindmap",
    "gitGraph",
    "journey",
    "C4Context",
)


def extract_json(raw_text: str) -> Optional[Any]:
    """
    Safely extracts JSON object or array from LLM response text.
    """
    clean = strip_code_fence(raw_text)

    # Try array
    span = find_bracket_span(clean, "[", "]")
    if span:
        parsed = try_parse_json(clean[span[0] : span[1] + 1])
        if parsed is not None:
            return parsed

    # Try object
    span = find_bracket_span(clean, "{", "}")
    if span:
        parsed = try_parse_json(clean[span[0] : span[1] + 1])
        if parsed is not None:
            return parsed

    return try_parse_json(clean)


def sanitize_mermaid_spec(raw_spec: str, fallback_title: str = "Architecture Flow") -> str:
    """
    Cleans and repairs Mermaid.js diagram specifications.
    Ensures valid syntax, removes markdown wrappers, and auto-quotes troublesome labels.
    """
    if not raw_spec or not raw_spec.strip():
        return generate_fallback_mermaid("flowchart", fallback_title)

    spec = raw_spec.strip()

    # Strip code block wrappers
    spec = re.sub(r"^```(?:mermaid)?\s*", "", spec, flags=re.IGNORECASE)
    spec = re.sub(r"\s*```$", "", spec)
    spec = spec.strip()

    # Check if starts with a recognized mermaid keyword
    starts_valid = any(spec.startswith(kw) for kw in MERMAID_KEYWORDS)
    if not starts_valid:
        # If it looks like flow lines (e.g. A --> B), prefix with flowchart TD
        if "-->" in spec or "---" in spec or "->>" in spec:
            if "->>" in spec:
                spec = f"sequenceDiagram\n    {spec}"
            else:
                spec = f"flowchart TD\n    {spec}"
        else:
            return generate_fallback_mermaid("flowchart", fallback_title)

    # Auto-quote labels containing parentheses or spaces if unquoted: e.g. A[Client (HTTP)] -> A["Client (HTTP)"]
    def quote_square_label(m):
        node_id = m.group(1)
        inner = m.group(2).strip()
        if (inner.startswith('"') and inner.endswith('"')) or (inner.startswith("'") and inner.endswith("'")):
            return f"{node_id}[{inner}]"
        # If it has spaces, parens, colons, or slashes, wrap in quotes
        if any(c in inner for c in " ()/:->#"):
            cleaned = inner.replace('"', "'")
            return f'{node_id}["{cleaned}"]'
        return f"{node_id}[{inner}]"

    spec = re.sub(r'(\b[A-Za-z0-9_]+)\[([^"\]\r\n]+)\]', quote_square_label, spec)

    return spec


def generate_fallback_mermaid(visual_type: str = "flowchart", title: str = "Technical Architecture") -> str:
    """
    Generates deterministic, visually rich, syntactically guaranteed Mermaid diagrams.
    """
    clean_title = title.replace('"', "'")

    if visual_type == "sequence":
        return f"""sequenceDiagram
    autonumber
    actor Learner as "Client / Learner"
    participant Gateway as "API Gateway"
    participant Engine as "Core Engine ({clean_title})"
    participant Storage as "State & Storage"

    Learner->>Gateway: Submit Request (Payload)
    activate Gateway
    Gateway->>Engine: Forward & Authenticate
    activate Engine
    Engine->>Storage: Fetch Dependencies & Context
    Storage-->>Engine: Return State
    Engine-->>Gateway: Execution Result & Metrics
    deactivate Engine
    Gateway-->>Learner: 200 OK (Processed Response)
    deactivate Gateway"""

    if visual_type == "state_machine":
        return f"""stateDiagram-v2
    [*] --> Idle: Initialize {clean_title}
    Idle --> Processing: Event Dispatched
    Processing --> Validating: Run Invariants
    Validating --> Committed: Invariants Passed
    Validating --> Failed: Constraint Violation
    Failed --> Idle: Rollback & Alert
    Committed --> [*]: Finalize State"""

    if visual_type == "concept_map":
        return f"""flowchart TD
    subgraph CoreDomain["Core Concept: {clean_title}"]
        RootNode["{clean_title}"]
    end

    subgraph Foundations["Foundational Mechanics"]
        F1["State Invariants"]
        F2["Data Flow & Serialization"]
    end

    subgraph Advanced["Operational Trade-offs"]
        A1["Latency vs Throughput"]
        A2["Fault Tolerance & Recovery"]
    end

    RootNode --> F1
    RootNode --> F2
    F1 --> A1
    F2 --> A2"""

    if visual_type in ("architecture", "architecture_diagram"):
        return f"""flowchart TD
    subgraph Ingress["1. Ingress & Interface"]
        ClientApp["Client / Agent Context"] --> Dispatcher["Dispatcher & Gateway"]
    end

    subgraph ProcessingCore["2. {clean_title} Core"]
        Dispatcher --> Controller["Controller Logic"]
        Controller --> Execution["{clean_title} Engine"]
    end

    subgraph Persistence["3. Storage & State Persistence"]
        Execution <--> StateStore[("State Store / Cache")]
    end

    classDef primary fill:#3a2f1a,stroke:#d9a441,stroke-width:2px,color:#ece8df;
    classDef secondary fill:#2f4a2a,stroke:#7fa37a,stroke-width:2px,color:#ece8df;
    class ClientApp,Dispatcher,Controller,Execution primary;
    class StateStore secondary;"""

    # Default: flowchart
    return f"""flowchart TD
    InputNode["Initial State / Context Input"] --> PrepNode["Prepare & Validate {clean_title}"]
    PrepNode --> ExecNode["Execute {clean_title}"]
    ExecNode --> EvalNode{{"Constraints Satisfied?"}}
    EvalNode -- Yes --> ResultNode["Optimized Output State"]
    EvalNode -- No --> FallbackNode["Compensate & Handle Edge Case"]

    classDef accent fill:#4a3a1c,stroke:#d9a441,stroke-width:2px,color:#ece8df;
    classDef success fill:#2f4a2a,stroke:#7fa37a,stroke-width:2px,color:#ece8df;
    classDef warn fill:#6b2f20,stroke:#c4684f,stroke-width:2px,color:#ece8df;
    class PrepNode,ExecNode accent;
    class ResultNode success;
    class FallbackNode warn;"""

