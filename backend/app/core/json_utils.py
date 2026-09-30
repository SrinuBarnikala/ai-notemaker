import json
import re
from typing import Any, Optional, Tuple

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def strip_code_fence(text: str) -> str:
    """Strips a leading/trailing markdown code fence (```...```) from raw LLM text."""
    clean = text.strip()
    match = _FENCE_RE.search(clean)
    if match:
        clean = match.group(1).strip()
    return clean


def find_bracket_span(text: str, open_ch: str, close_ch: str) -> Optional[Tuple[int, int]]:
    """Finds the outermost open/close bracket span in text, or None if not present/invalid."""
    start = text.find(open_ch)
    end = text.rfind(close_ch)
    if start != -1 and end != -1 and end > start:
        return start, end
    return None


def try_parse_json(candidate: str) -> Optional[Any]:
    """Attempts json.loads, returning None instead of raising on failure."""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
