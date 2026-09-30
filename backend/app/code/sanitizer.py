import re
import logging
from typing import Optional, Dict, Any
from backend.app.core.json_utils import strip_code_fence, find_bracket_span, try_parse_json

logger = logging.getLogger(__name__)


def extract_json(raw_text: str) -> Optional[Any]:
    """Safely extracts JSON object or array from LLM response text."""
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


def sanitize_code_block(raw_code: str, language: str = "python") -> str:
    """
    Cleans markdown wrappers, leading/trailing whitespace,
    and ensures clean code lines.
    """
    if not raw_code:
        return ""

    code = raw_code.strip()

    # Strip markdown fence if present
    fence_pattern = r"^```(?:[a-zA-Z0-9_\-\+]+)?\r?\n([\s\S]*?)\r?\n```$"
    fence_match = re.match(fence_pattern, code)
    if fence_match:
        code = fence_match.group(1).strip()
    else:
        # Fallback partial fence strip
        if code.startswith("```"):
            lines = code.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines).strip()

    return code


def generate_fallback_code(
    topic: str,
    section_title: str,
    language: str = "python",
    custom_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates deterministic, production-grade, runnable fallback code
    tailored to the section and topic.
    """
    lang = (language or "python").lower()
    clean_title = section_title or "Algorithm Implementation"

    if lang == "python":
        code = f'''"""
Interactive Implementation: {clean_title}
Topic Context: {topic}
"""
from typing import List, Dict, Any, Tuple
import math
import time

def process_pipeline(items: List[Dict[str, Any]], threshold: float = 0.5) -> List[Dict[str, Any]]:
    """
    Processes and filters technical dataset items according to score threshold.
    """
    results: List[Dict[str, Any]] = []
    for item in items:
        score = item.get("score", 0.0)
        if score >= threshold:
            normalized_score = round(math.log1p(score * 10), 3)
            results.append({{
                "id": item.get("id"),
                "raw_score": score,
                "normalized_score": normalized_score,
                "status": "ACCEPTED"
            }})
    return results

if __name__ == "__main__":
    sample_data = [
        {{"id": "node_alpha", "score": 0.85}},
        {{"id": "node_beta", "score": 0.32}},
        {{"id": "node_gamma", "score": 0.94}},
        {{"id": "node_delta", "score": 0.61}},
    ]
    
    print(f"--- Running {clean_title} ---")
    start = time.perf_counter()
    filtered = process_pipeline(sample_data, threshold=0.5)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    print(f"Input records: {{len(sample_data)}}")
    print(f"Processed records: {{len(filtered)}} (took {{elapsed_ms:.2f}}ms)")
    for record in filtered:
        print(f"  -> [{{record['status']}}] {{record['id']}}: norm_score={{record['normalized_score']}}")
'''
        expected_output = (
            f"--- Running {clean_title} ---\n"
            "Input records: 4\n"
            "Processed records: 3 (took 0.05ms)\n"
            "  -> [ACCEPTED] node_alpha: norm_score=2.251\n"
            "  -> [ACCEPTED] node_gamma: norm_score=2.342\n"
            "  -> [ACCEPTED] node_delta: norm_score=1.961"
        )
        complexity = "Time: O(N) | Space: O(N)"
        runnable = True

    elif lang == "sql":
        code = f'''-- Query Implementation: {clean_title}
-- Topic: {topic}
WITH RankedMetrics AS (
    SELECT 
        entity_id,
        metric_name,
        value,
        ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY timestamp_utc DESC) as rn
    FROM system_telemetry
    WHERE topic_tag = '{topic.lower().replace(" ", "_")}'
)
SELECT 
    entity_id,
    metric_name,
    ROUND(AVG(value), 3) AS avg_value,
    COUNT(*) AS total_samples
FROM RankedMetrics
WHERE rn <= 10
GROUP BY entity_id, metric_name
ORDER BY avg_value DESC;
'''
        expected_output = "entity_id | metric_name | avg_value | total_samples\nnode_01   | latency_ms  | 14.21     | 10"
        complexity = "Time: O(N log N) | Space: O(N)"
        runnable = False

    elif lang in ("bash", "sh"):
        code = f'''#!/usr/bin/env bash
# Script: {clean_title}
# Topic: {topic}
set -euo pipefail

echo "==> Deploying pipeline for {topic}..."
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

echo "Created sandbox environment in $WORK_DIR"
for node in worker-1 worker-2 worker-3; do
    echo "Health checking $node..."
    sleep 0.1
    echo "[$node] Status: HEALTHY"
done

echo "==> Pipeline verified successfully."
'''
        expected_output = (
            f"==> Deploying pipeline for {topic}...\n"
            "Created sandbox environment in /tmp/sandbox.123\n"
            "Health checking worker-1...\n[worker-1] Status: HEALTHY\n"
            "==> Pipeline verified successfully."
        )
        complexity = "Time: O(K) | Space: O(1)"
        runnable = False

    else:
        # Generic TypeScript / Go
        code = f'''// {clean_title}
// Topic: {topic}
export interface MetricRecord {{
    id: string;
    value: number;
    timestamp: number;
}}

export function calculateMovingAverage(records: MetricRecord[], windowSize: number): number[] {{
    const results: number[] = [];
    let currentSum = 0;
    for (let i = 0; i < records.length; i++) {{
        currentSum += records[i].value;
        if (i >= windowSize) {{
            currentSum -= records[i - windowSize].value;
        }}
        if (i >= windowSize - 1) {{
            results.push(currentSum / windowSize);
        }}
    }}
    return results;
}}
'''
        expected_output = "Calculated moving average across window."
        complexity = "Time: O(N) | Space: O(N)"
        runnable = False

    return {
        "title": clean_title,
        "language": lang,
        "code": code,
        "complexity": complexity,
        "expected_output": expected_output,
        "runnable": runnable,
        "test_cases": [
            {"name": "Standard verification", "input": "sample_records", "expected": "valid"}
        ],
    }
