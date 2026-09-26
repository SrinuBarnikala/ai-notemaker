import pytest
import json
import httpx
from unittest.mock import patch

from backend.app.providers.openai_compatible import OpenAICompatibleProvider
from backend.app.providers.mock import MockLLMProvider
from backend.app.note.parser import parse_section_blocks
from backend.app.architecture.parser import parse_note_architecture, clean_gap_to_title
from backend.app.architecture.generator import generate_note_architecture
from backend.app.note.generator import generate_structured_note
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.db.session import SessionLocal
from backend.app.config import get_settings


# 1. PROVIDER RELIABILITY TESTS

@pytest.mark.asyncio
async def test_provider_retry_transient_429_success():
    """Transient HTTP 429 should be retried and succeed on second attempt."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        max_retries=2,
        initial_delay=0.01,
        backoff_factor=1.5,
    )

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp_429 = httpx.Response(429, headers={"Retry-After": "0.01"}, text='{"error":"Rate limit"}', request=req)
    resp_200 = httpx.Response(200, json={"choices": [{"message": {"content": '{"result": "success"}'}}]}, request=req)

    with patch("httpx.AsyncClient.post", side_effect=[resp_429, resp_200]) as mock_post:
        result = await provider.generate(prompt="test prompt")
        assert result == '{"result": "success"}'
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_provider_retry_transient_5xx_success():
    """Transient HTTP 503 should be retried and succeed on second attempt."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        max_retries=2,
        initial_delay=0.01,
        backoff_factor=1.5,
    )

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp_503 = httpx.Response(503, text='{"error":"Service unavailable"}', request=req)
    resp_200 = httpx.Response(200, json={"choices": [{"message": {"content": '{"status": "ok"}'}}]}, request=req)

    with patch("httpx.AsyncClient.post", side_effect=[resp_503, resp_200]) as mock_post:
        result = await provider.generate(prompt="test prompt")
        assert result == '{"status": "ok"}'
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_provider_retry_timeout_success():
    """Timeout exception should be retried and succeed on second attempt."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        max_retries=2,
        initial_delay=0.01,
        backoff_factor=1.5,
    )

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp_200 = httpx.Response(200, json={"choices": [{"message": {"content": "Recovered after timeout"}}]}, request=req)

    with patch("httpx.AsyncClient.post", side_effect=[httpx.ReadTimeout("Timeout"), resp_200]) as mock_post:
        result = await provider.generate(prompt="test prompt")
        assert result == "Recovered after timeout"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_provider_permanent_401_no_retry():
    """Permanent error like 401 Unauthorized must NOT be retried."""
    provider = OpenAICompatibleProvider(
        api_key="invalid-key",
        max_retries=3,
        initial_delay=0.01,
    )

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp_401 = httpx.Response(401, text='{"error":"Invalid API key"}', request=req)

    with patch("httpx.AsyncClient.post", return_value=resp_401) as mock_post:
        with pytest.raises(RuntimeError) as exc_info:
            await provider.generate(prompt="test prompt")
        assert "401" in str(exc_info.value)
        assert mock_post.call_count == 1


# 2. STRUCTURED OUTPUT TESTS

def test_structured_output_acceptance_valid():
    """Valid JSON array or blocks object should be parsed cleanly without fallback."""
    raw = json.dumps({
        "blocks": [
            {"type": "paragraph", "content": "Context window limits dictate agent prompt budgeting."},
            {"type": "definition", "term": "Context Window", "content": "Total contiguous token capacity."},
            {"type": "code", "language": "python", "code": "def budget(): pass", "title": "Budgeting"},
        ]
    })
    blocks = parse_section_blocks(
        raw_text=raw,
        section_title="Context Limits",
        section_type="deep_dive",
        depth="standard",
        target_concepts=["Context Window"],
        rationale="Clear boundaries",
        needs_code=True,
        needs_visual=False,
    )
    assert len(blocks) == 3
    assert blocks.used_fallback is False
    assert blocks.failure_reason is None


def test_structured_output_rejection_malformed():
    """Malformed output must be safely rejected and fallback metadata recorded."""
    corrupt = "This is not JSON at all, just plain conversational text."
    blocks = parse_section_blocks(
        raw_text=corrupt,
        section_title="Context Optimization",
        section_type="deep_dive",
        depth="deep",
        target_concepts=["Context Optimization"],
        rationale="Covers scaling",
        needs_code=True,
        needs_visual=True,
    )
    assert len(blocks) >= 3
    assert blocks.used_fallback is True
    assert blocks.failure_reason is not None


# 3. FALLBACK OBSERVABILITY TESTS

def test_fallback_observability_architecture():
    """Architecture fallback records used_fallback=True and failure_reason."""
    corrupt = "Not a json object."
    parsed = parse_note_architecture(
        raw_text=corrupt,
        topic="Context Management",
        profile_summary="Learner knows basics.",
        concepts=[{"name": "Context Window", "level": "strong"}],
        gaps=["Context Compression"],
        misconceptions=[],
    )
    assert parsed.used_fallback is True
    assert parsed.failure_reason is not None


# 4. CONTEXT PROPAGATION TESTS

@pytest.mark.asyncio
async def test_context_propagation_to_architecture_and_sections():
    """Verify that learner profile values reach the architecture and section generation prompts."""
    db = SessionLocal()
    try:
        # 1. Create Journey
        journey = LearningJourney(topic="Context Engineering in Agentic Applications")
        db.add(journey)
        db.commit()

        # 2. Add Discovery Interaction
        discovery = DiscoveryInteraction(
            journey_id=journey.id,
            question_index=1,
            question_text="What is your experience with context selection?",
            concept_target="Context Selection",
            learner_answer="I have used caching, but need production relevance scoring.",
            quick_assessment="Learner knows caching but lacks scoring algorithms.",
        )
        db.add(discovery)

        # 3. Add Knowledge Profile with specific identifiable test values
        profile = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence="intermediate",
            summary="Learner understands basic context windows but lacks relevance scoring mechanics.",
            gaps=json.dumps(["Relevance Scoring Mechanisms"]),
            misconceptions=json.dumps(["More context is always better"]),
        )
        db.add(profile)
        db.flush()

        concept_known = KnowledgeConcept(
            profile_id=profile.id,
            name="Context Window",
            level="strong",
            category="known",
            notes="High-level understanding confirmed.",
        )
        db.add(concept_known)
        db.commit()

        mock_provider = MockLLMProvider(
            response_text=json.dumps({
                "summary_rationale": "Personalized to bridge relevance scoring gap.",
                "sections": [
                    {
                        "order_index": 1,
                        "title": "Context Window Foundations",
                        "section_type": "mental_model",
                        "depth": "brief",
                        "target_concepts": ["Context Window"],
                        "rationale": "Respects known concept.",
                        "needs_code": False,
                        "needs_visual": True,
                        "visual_type": "flowchart",
                    },
                    {
                        "order_index": 2,
                        "title": "Relevance Scoring Mechanics",
                        "section_type": "deep_dive",
                        "depth": "deep",
                        "target_concepts": ["Relevance Scoring Mechanisms"],
                        "rationale": "Deep dive into scoring.",
                        "needs_code": True,
                        "needs_visual": True,
                        "visual_type": "architecture_diagram",
                    },
                    {
                        "order_index": 3,
                        "title": "Production Implementation",
                        "section_type": "code_walkthrough",
                        "depth": "deep",
                        "target_concepts": ["Implementation"],
                        "rationale": "Executable code.",
                        "needs_code": True,
                        "needs_visual": False,
                        "visual_type": None,
                    },
                ]
            })
        )

        settings = get_settings()

        with patch("backend.app.architecture.generator.get_llm_provider", return_value=mock_provider):
            arch_res = await generate_note_architecture(
                journey_id=journey.id,
                db=db,
                settings=settings,
                learning_goal="Design production context selection",
            )

        # Verify architecture prompt received all context
        arch_prompt = mock_provider.last_prompt
        assert "Context Window" in arch_prompt
        assert "Relevance Scoring Mechanisms" in arch_prompt
        assert "More context is always better" in arch_prompt
        assert "Design production context selection" in arch_prompt
        assert "caching, but need production relevance scoring" in arch_prompt

        # Mock section generator response
        mock_provider.set_response(json.dumps({
            "blocks": [
                {"type": "paragraph", "content": "Deep mechanics of context selection."},
                {"type": "definition", "term": "Scoring Engine", "content": "Calculates priority."},
            ]
        }))

        with patch("backend.app.note.generator.get_llm_provider", return_value=mock_provider):
            note_res = await generate_structured_note(
                journey_id=journey.id,
                db=db,
                settings=settings,
            )

        # Verify section prompt received complete learner context and document roadmap
        section_prompt = mock_provider.last_prompt
        assert "Context Window" in section_prompt
        assert "Relevance Scoring Mechanisms" in section_prompt
        assert "More context is always better" in section_prompt
        assert "Design production context selection" in section_prompt
        assert "Total Sections: 3" in section_prompt
        assert "Previous Section Context:" in section_prompt

    finally:
        db.close()


# 5. ANTI-HARDCODING TESTS

def test_anti_hardcoding_unrelated_topic():
    """Verify an unrelated topic (e.g. Python garbage collection) never receives RAG or vector-search boilerplate."""
    blocks = parse_section_blocks(
        raw_text="invalid json",
        section_title="Generational GC Mechanics",
        section_type="deep_dive",
        depth="deep",
        target_concepts=["Generational Garbage Collection"],
        rationale="Explains generation thresholds.",
        needs_code=True,
        needs_visual=True,
        visual_type="architecture_diagram",
        topic="Python Memory Management",
    )

    # Stringify all block content
    full_text = " ".join([
        f"{b.content or ''} {b.title or ''} {b.code or ''} {b.diagram_spec or ''}"
        for b in blocks
    ]).lower()

    prohibited_terms = [
        "vector search",
        "rerank",
        "top-100",
        "top-20",
        "hnsw",
        "cross-encoder",
        "gpu batch sizing",
        "vector database",
    ]
    for term in prohibited_terms:
        assert term not in full_text, f"Prohibited RAG term '{term}' found in non-RAG fallback!"


# 6. ARCHITECTURE PERSONALIZATION TESTS

def test_architecture_personalization_clean_titles():
    """Verify clean_gap_to_title eliminates awkward raw prefixes."""
    assert clean_gap_to_title("concrete understanding of context window definition and optimization") == "Context Window Definition and Optimization"
    assert clean_gap_to_title("factors influencing context window size and token limits") == "Context Window Size and Token Limits"
    assert clean_gap_to_title("practical application of context selection strategies such as compression and caching") == "Context Selection Strategies such as Compression and Caching"
    assert clean_gap_to_title("design and implementation of relevance scoring mechanisms for context selection") == "Relevance Scoring Mechanisms for Context Selection"


def test_architecture_fallback_avoids_raw_core_mechanics_prefix():
    """Verify fallback architecture titles do not have 'Core Mechanics: Concrete understanding of...'."""
    parsed = parse_note_architecture(
        raw_text="",
        topic="Context Engineering",
        profile_summary="Learner lacks sizing and scoring.",
        concepts=[{"name": "Context Window", "level": "strong"}],
        gaps=[
            "Concrete understanding of context window definition and optimization",
            "Factors influencing context window size and token limits"
        ],
        misconceptions=[],
    )
    for s in parsed.sections:
        assert not s.title.startswith("Core Mechanics: Concrete understanding")
        assert not s.title.startswith("Core Mechanics: Factors influencing")
