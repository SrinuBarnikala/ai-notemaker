import re
import json
import logging
from typing import Optional, Dict, Any

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
    clean = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if match:
        clean = match.group(1).strip()

    # Try array
    s_arr = clean.find("[")
    e_arr = clean.rfind("]")
    if s_arr != -1 and e_arr != -1 and e_arr > s_arr:
        candidate = clean[s_arr : e_arr + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Try object
    s_obj = clean.find("{")
    e_obj = clean.rfind("}")
    if s_obj != -1 and e_obj != -1 and e_obj > s_obj:
        candidate = clean[s_obj : e_obj + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


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

    if visual_type == "architecture":
        return f"""flowchart TD
    subgraph Ingestion["1. Ingress Layer"]
        ClientApp["Client Application"] --> LoadBalancer["Load Balancer / Proxy"]
    end

    subgraph Processing["2. {clean_title} Core"]
        LoadBalancer --> Service["Processing Service"]
        Service --> Cache[("In-Memory Cache")]
    end

    subgraph Persistence["3. Persistence & Vector Layer"]
        Service --> PrimaryDB[("Primary Database")]
        Service --> EventQueue["Event Queue / Log"]
    end

    classDef primary fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#f8fafc;
    classDef secondary fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    class ClientApp,Service primary;
    class PrimaryDB,EventQueue secondary;"""

    # Default: flowchart
    return f"""flowchart LR
    Input["Input Query / State"] --> Transform["{clean_title}"]
    Transform --> Validator{{"Invariants Valid?"}}
    Validator -- Yes --> Output["Optimized Output State"]
    Validator -- No --> Fallback["Fallback / Recovery Path"]

    classDef accent fill:#312e81,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef success fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc;
    class Transform accent;
    class Output success;"""
