"""Regression tests for the review findings: evidence, stopping rules, retractions, confidence,
plain-text recovery, Unicode de-duplication, profile retry, deadlines and status protection."""
import json

import pytest

from backend.app.db.session import SessionLocal
from backend.app.discovery.groups import question_problem
from backend.app.discovery.parser import parse_turn
from backend.app.discovery.state import (
    DiscoveryLearnerState,
    Finding,
    Retraction,
    evidence_is_valid,
    ground_findings,
    merge_states,
    parse_retractions,
    parse_state,
    same_finding,
    state_to_prompt_text,
)
from backend.app.discovery.text import tokenize
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile
from backend.app.personalization.builder import PersonalizationContextBuilder
from backend.app.profile.parser import parse_knowledge_profile
from discovery_helpers import Sleep, finding, opening, profile_json, turn

TOPIC = "How does backpropagation work?"
Q1 = "Why do you think we needed a way to adjust weights automatically?"


def new_journey(client, topic=TOPIC):
    return client.post("/journeys", json={"topic": topic}).json()["id"]


def stored_analysis(journey_id, index):
    db = SessionLocal()
    try:
        row = db.query(DiscoveryInteraction).filter_by(journey_id=journey_id, question_index=index).one()
        return json.loads(row.analysis)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# D4: evidence validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("quote", ["a", "I", "the", "I am", "yes", "...", "", None])
def test_trivially_short_quotes_are_not_evidence(quote):
    assert evidence_is_valid(quote, ["I am a learner and I said yes to the idea."]) is False


def test_valid_quote_keeps_its_basis_and_evidence():
    state = parse_state({"intent": finding("Wants to implement it", "stated", "implement it in Rust")}, "t")
    ground_findings(state, ["I'd love to implement it in Rust someday."])
    assert state.intent.basis == "stated" and state.intent.evidence == "implement it in Rust"


def test_fabricated_quote_is_downgraded_and_the_fake_evidence_is_discarded():
    state = parse_state({"understanding": finding("Knows loops", "demonstrated", "I never said this sentence")}, "t")
    ground_findings(state, ["I like cats."])
    assert state.understanding.basis == "inferred"
    assert state.understanding.evidence is None  # a fabricated quote is never exposed


def test_inferred_findings_never_carry_unverified_evidence():
    state = parse_state({"gaps": [finding("Activation functions", "inferred", "made up words here")]}, "t")
    ground_findings(state, ["I like cats."])
    assert state.gaps[0].basis == "inferred" and state.gaps[0].evidence is None


def test_quote_must_match_whole_words_not_fragments():
    assert evidence_is_valid("cat theory", ["I like category theory"]) is False
    assert evidence_is_valid("category theory", ["I like category theory"]) is True


def test_quote_cannot_be_stitched_across_two_answers():
    answers = ["I know forward propagation well", "and I am unsure about activation functions"]
    assert evidence_is_valid("well and I am unsure", answers) is False
    assert evidence_is_valid("unsure about activation functions", answers) is True


def test_ellipsis_fragments_must_come_from_the_same_answer():
    answers = ["I know forward propagation but I am unsure about activations", "I prefer visuals and diagrams"]
    assert evidence_is_valid("I know forward propagation ... unsure about activations", answers) is True
    assert evidence_is_valid("I know forward propagation ... visuals and diagrams", answers) is False


def test_evidence_check_proves_presence_not_support():
    """Documented limit: a real quote attached to an unrelated claim passes; only the model can judge support."""
    state = parse_state({"intent": finding("Wants a PhD in physics", "stated", "I like cats")}, "t")
    ground_findings(state, ["I like cats."])
    assert state.intent.basis == "stated"


def test_evidence_in_telugu_is_checked_correctly():
    answer = "నాకు ఫార్వర్డ్ ప్రొపగేషన్ తెలుసు కానీ యాక్టివేషన్ ఫంక్షన్లు అర్థం కావు"
    assert evidence_is_valid("యాక్టివేషన్ ఫంక్షన్లు అర్థం కావు", [answer]) is True
    assert evidence_is_valid("బ్యాక్‌ప్రొపగేషన్ నాకు తెలుసు", [answer]) is False


# ---------------------------------------------------------------------------
# D3: evidence-based stopping rule and learning goal
# ---------------------------------------------------------------------------


def _journey_with_profile(client, scripted, intent_basis):
    state = {
        "understanding": finding("Knows the forward pass", "demonstrated", "I know the forward pass"),
        "intent": finding("Understand it deeply", intent_basis, "I want to understand it deeply" if intent_basis != "inferred" else None),
        "desired_depth": finding("Deep understanding", "stated", "understand it deeply"),
    }
    scripted.push(opening(Q1), turn(ready=True, state=state), profile_json())
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer",
                json={"answer": "I know the forward pass and I want to understand it deeply."})
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    return journey_id


# ---------------------------------------------------------------------------
# D5: explicit retractions
# ---------------------------------------------------------------------------

def test_parse_retractions_is_lenient_and_ignores_unknown_fields():
    raw = [
        {"field": "misconceptions", "value": "Believes ReLU is linear", "reason": "corrected"},
        "gaps: Activation functions",
        {"field": "nonsense", "value": "x"},
        {"field": "intention", "value": ""},
        42,
    ]
    parsed = parse_retractions(raw)
    assert [(r.field, r.value) for r in parsed] == [
        ("misconceptions", "Believes ReLU is linear"), ("gaps", "Activation functions"), ("intent", ""),
    ]
    assert parse_retractions("not a list") == []


def test_parse_turn_reads_retractions():
    reply = json.dumps({
        "state": {}, "ready_to_finish": False,
        "group": {"motive": "I'd like to see what happens next.", "questions": ["What would you like to do next here?"]},
        "retractions": [{"field": "misconceptions", "value": "Believes ReLU is linear"}],
    })
    assert parse_turn(reply, "t").retractions == [Retraction(field="misconceptions", value="Believes ReLU is linear")]


def test_a_retracted_finding_disappears_even_when_the_model_merely_omits_the_rest():
    previous = DiscoveryLearnerState(
        misconceptions=[Finding(value="Believes ReLU is linear", basis="demonstrated", evidence="ReLU is linear")],
        gaps=[Finding(value="Activation functions"), Finding(value="Weight initialisation")],
        intent=Finding(value="Pass an exam", basis="stated", evidence="an exam"),
    )
    new = DiscoveryLearnerState(related_familiarity=[Finding(value="Knows gradient descent")])
    merged = merge_states(previous, new, [
        Retraction(field="misconceptions", value="Believes ReLU is linear", reason="learner corrected it"),
        Retraction(field="gaps", value="Activation functions"),
    ])
    assert merged.misconceptions == []
    assert [g.value for g in merged.gaps] == ["Weight initialisation"]  # not retracted: preserved when omitted
    assert merged.intent.value == "Pass an exam"                       # not retracted: preserved when omitted
    assert {(r.field, r.value) for r in merged.resolved} == {
        ("misconceptions", "Believes ReLU is linear"), ("gaps", "Activation functions"),
    }


def test_retraction_matches_a_paraphrase_and_beats_the_models_own_relisting():
    previous = DiscoveryLearnerState(misconceptions=[Finding(value="Believes the ReLU activation is linear")])
    relisted = DiscoveryLearnerState(misconceptions=[Finding(value="Thinks ReLU activation is linear")])
    merged = merge_states(previous, relisted, [Retraction(field="misconceptions", value="believes ReLU activation is linear")])
    assert merged.misconceptions == []


def test_single_valued_findings_can_be_retracted_and_replaced():
    previous = DiscoveryLearnerState(intent=Finding(value="Pass an interview", basis="stated", evidence="interview"))
    merged = merge_states(previous, DiscoveryLearnerState(), [Retraction(field="intent", value="Pass an interview")])
    assert merged.intent is None
    replaced = merge_states(previous, DiscoveryLearnerState(intent=Finding(value="Build a product")),
                            [Retraction(field="intent", value="Pass an interview")])
    assert replaced.intent.value == "Build a product"


def test_resolved_findings_reach_the_model_but_not_the_current_state_text():
    state = DiscoveryLearnerState()
    previous = DiscoveryLearnerState(misconceptions=[Finding(value="Believes ReLU is linear")])
    merged = merge_states(previous, state, [Retraction(field="misconceptions", value="Believes ReLU is linear")])
    text = state_to_prompt_text(merged)
    assert "Possible misconceptions: unknown" in text
    assert "Corrected or resolved earlier (no longer current): Believes ReLU is linear (misconceptions)" in text


# ---------------------------------------------------------------------------
# D6: unknown confidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {},                                              # missing
    {"overall_confidence": "not-assessed"},          # invalid
    {"overall_confidence": ""},
    {"overall_confidence": None},
])
def test_invalid_or_missing_confidence_is_unknown_never_intermediate(payload):
    parsed = parse_knowledge_profile(json.dumps({"summary": "A sufficiently long summary.", **payload}), "T", [])
    assert parsed.overall_confidence == "unknown" and parsed.used_fallback is False


def test_valid_confidence_values_are_kept():
    for level in ("beginner", "intermediate", "advanced", "mixed", "unknown"):
        parsed = parse_knowledge_profile(json.dumps({"summary": "A sufficiently long summary.", "overall_confidence": level}), "T", [])
        assert parsed.overall_confidence == level


def test_unknown_confidence_flows_downstream_without_claiming_a_level(client, scripted):
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Something."})
    body = client.post(f"/journeys/{journey_id}/knowledge-profile").json()  # unusable model output
    assert body["overall_confidence"] == "unknown" and body["synthesis_fallback"] is True
    assert client.get(f"/journeys/{journey_id}/knowledge-profile").json()["overall_confidence"] == "unknown"

    db = SessionLocal()
    try:
        ctx = PersonalizationContextBuilder.build(journey_id, db)
        assert ctx.overall_confidence == "unknown"
        assert "Topic Confidence" not in ctx.format_for_prompt()
    finally:
        db.close()
    assert client.post(f"/journeys/{journey_id}/architecture", json={}).status_code == 200
    assert client.post(f"/journeys/{journey_id}/generate-note").status_code == 200


def test_developing_confidence_written_by_the_quiz_stage_no_longer_breaks_the_profile_endpoint(client, scripted):
    scripted.push(opening(Q1), turn(question="What do you want to build?"), profile_json())
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass."})
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    db = SessionLocal()
    try:
        db.query(KnowledgeProfile).filter_by(journey_id=journey_id).one().overall_confidence = "developing"
        db.commit()
    finally:
        db.close()
    res = client.get(f"/journeys/{journey_id}/knowledge-profile")
    assert res.status_code == 200 and res.json()["overall_confidence"] == "developing"


def test_ui_shows_an_honest_not_assessed_state(client):
    html = client.get("/").text
    assert 'id="prof-confidence"' in html and "confidence-unknown" in html and "NOT ASSESSED" in html
    assert 'id="prof-fallback-notice"' in html and 'id="prof-error"' in html
    assert ".confidence-unknown" in client.get("/static/css/main.css").text
    js = client.get("/static/js/journey.js").text
    assert "NOT ASSESSED" in js and "synthesis_fallback" in js and "retryProfileGeneration" in js


# ---------------------------------------------------------------------------
# D7: plain-text recovery before the canned list
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# D8: Unicode de-duplication
# ---------------------------------------------------------------------------

TELUGU_Q = "బ్యాక్‌ప్రొపగేషన్ ఎలా పనిచేస్తుందని మీరు అనుకుంటున్నారు?"
HINDI_Q = "आपको क्या लगता है कि बैकप्रोपेगेशन कैसे काम करता है?"
ARABIC_Q = "ما رأيك في كيفية عمل الانتشار الخلفي في الشبكات العصبية؟"
JAPANESE_Q = "誤差逆伝播法はどのように機能すると思いますか？"


def test_tokenizer_keeps_indic_words_whole_and_splits_spaceless_scripts_into_bigrams():
    assert tokenize("ఇది ఏమిటి") == ["ఇది", "ఏమిటి"]  # vowel signs are not word separators
    assert tokenize("इसका मतलब क्या है") == ["इसका", "मतलब", "क्या", "है"]
    assert tokenize("誤差逆伝播") == ["誤差", "差逆", "逆伝", "伝播"]
    assert tokenize("Hello, WORLD!") == ["hello", "world"]


@pytest.mark.parametrize("question", [TELUGU_Q, HINDI_Q, ARABIC_Q, JAPANESE_Q])
def test_identical_questions_are_detected_in_any_script(question):
    assert question_problem(question, [question]) == "it repeats an earlier question"


@pytest.mark.parametrize("original,reworded", [
    (TELUGU_Q, "బ్యాక్‌ప్రొపగేషన్ ఎలా పనిచేస్తుందని మీరు అనుకుంటున్నారు మరి?"),
    (HINDI_Q, "आपको क्या लगता है कि बैकप्रोपेगेशन कैसे काम करता है भला?"),
    (ARABIC_Q, "ما رأيك في كيفية عمل الانتشار الخلفي في الشبكات العصبية بالضبط؟"),
    (JAPANESE_Q, "誤差逆伝播法はどのように機能すると、思いますか？"),
])
def test_substantially_repeated_questions_are_detected_in_any_script(original, reworded):
    assert question_problem(reworded, [original]) == "it repeats an earlier question"


@pytest.mark.parametrize("original,different", [
    (TELUGU_Q, "మీరు ఈ విషయాన్ని ఎందుకు నేర్చుకోవాలనుకుంటున్నారు?"),
    (HINDI_Q, "आप इसे क्यों सीखना चाहते हैं?"),
    (ARABIC_Q, "ما هو هدفك من تعلم هذا الموضوع؟"),
    (JAPANESE_Q, "あなたはなぜこの分野を学びたいのですか？"),
])
def test_genuinely_different_questions_are_not_flagged_in_any_script(original, different):
    assert question_problem(different, [original]) is None


def test_multiple_question_marks_are_counted_for_arabic_and_fullwidth_too():
    assert "more than one question" in question_problem("ما هذا؟ ولماذا يحدث هذا؟", [])
    assert "more than one question" in question_problem("これは何ですか？なぜですか？", [])


# ---------------------------------------------------------------------------
# D9: profile retry and visibility
# ---------------------------------------------------------------------------

def test_profile_retry_after_failure_keeps_answers_and_creates_no_duplicates(client, scripted):
    scripted.push(opening(Q1), turn(question="What do you want to build?"), RuntimeError("down"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass."})

    def snapshot():
        history = client.get(f"/journeys/{journey_id}/discovery").json()
        return [(i["question_index"], i["question_text"], i["learner_answer"]) for i in history["interactions"]]

    before = snapshot()
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").status_code == 503
    assert snapshot() == before and client.get(f"/journeys/{journey_id}/knowledge-profile").status_code == 404

    scripted.push(profile_json())
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").status_code == 200
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").status_code == 200  # retry again: idempotent
    assert snapshot() == before
    db = SessionLocal()
    try:
        assert db.query(KnowledgeProfile).filter_by(journey_id=journey_id).count() == 1
    finally:
        db.close()


def test_fallback_profile_is_flagged_on_create_and_on_later_reads(client, scripted):
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Something."})
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").json()["synthesis_fallback"] is True
    assert client.get(f"/journeys/{journey_id}/knowledge-profile").json()["synthesis_fallback"] is True


def _legacy_journey():
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Legacy topic", status="discovery")
        db.add(journey)
        db.commit()
        db.add(DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Old Q?",
                                    concept_target="T", learner_answer="Old answer", quick_assessment="Old note"))
        db.commit()
        return journey.id
    finally:
        db.close()


def test_legacy_journey_fallback_profile_is_flagged_without_a_discovery_state(client, scripted):
    journey_id = _legacy_journey()
    body = client.post(f"/journeys/{journey_id}/knowledge-profile").json()  # garbage model output
    assert body["synthesis_fallback"] is True and body["overall_confidence"] == "unknown"
    assert client.get(f"/journeys/{journey_id}/knowledge-profile").json()["synthesis_fallback"] is True


def test_legacy_journey_with_a_good_profile_is_not_flagged_and_has_no_context(client, scripted):
    journey_id = _legacy_journey()
    scripted.push(profile_json())
    body = client.post(f"/journeys/{journey_id}/knowledge-profile").json()
    assert body["synthesis_fallback"] is False and body["learner_context"] is None
    assert client.get(f"/journeys/{journey_id}/knowledge-profile").json()["synthesis_fallback"] is False


def test_ui_has_profile_retry_and_fallback_warnings_for_architecture_and_note(client):
    html = client.get("/").text
    assert 'id="arch-fallback-notice"' in html and 'id="note-fallback-notice"' in html
    assert "llm_fallback" in client.get("/static/js/journey.js").text
    assert "llm_partial_fallback" in client.get("/static/js/viewer.js").text


# ---------------------------------------------------------------------------
# Provider deadline
# ---------------------------------------------------------------------------

def test_request_deadline_returns_a_retryable_error_and_keeps_the_answer(client, scripted, test_settings):
    test_settings.discovery_request_timeout_seconds = 0.3
    scripted.push(opening(Q1), Sleep(30))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")

    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "My saved answer"})
    assert res.status_code == 503 and "took too long" in res.json()["detail"] and "saved" in res.json()["detail"]

    history = client.get(f"/journeys/{journey_id}/discovery").json()
    assert history["interactions"][0]["learner_answer"] == "My saved answer"
    assert len(history["interactions"]) == 1 and history["status"] == "discovery"
    assert stored_analysis(journey_id, 1).get("state") is None  # no half-written analysis

    # Resume works and creates exactly one successor
    scripted.push(turn(question="What would you like to do with it?"))
    resumed = client.post(f"/journeys/{journey_id}/discovery/start")
    assert resumed.status_code == 200 and resumed.json()["question_index"] == 2
    assert len(client.get(f"/journeys/{journey_id}/discovery").json()["interactions"]) == 2


def test_opening_deadline_leaves_no_partial_state(client, scripted, test_settings):
    test_settings.discovery_request_timeout_seconds = 0.3
    scripted.push(Sleep(30))
    journey_id = new_journey(client)
    res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert res.status_code == 503 and "took too long" in res.json()["detail"]
    assert client.get(f"/journeys/{journey_id}/discovery").json()["interactions"] == []
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "created"
    scripted.push(opening(Q1))
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["questions"] == [Q1]


def test_deadline_is_generous_enough_for_one_slow_provider_attempt():
    from backend.app.config import Settings
    s = Settings()
    assert s.discovery_request_timeout_seconds >= s.llm_timeout_seconds  # one full provider attempt fits


# ---------------------------------------------------------------------------
# Status protection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("later_status", ["architecture_ready", "note_generated"])
def test_regenerating_the_profile_never_moves_a_later_journey_backwards(client, scripted, later_status):
    scripted.push(opening(Q1), turn(question="What do you want to build?"), profile_json(), profile_json())
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass."})
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").status_code == 200
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "profile_ready"

    db = SessionLocal()
    try:
        db.query(LearningJourney).filter_by(id=journey_id).one().status = later_status
        db.commit()
    finally:
        db.close()
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").status_code == 200  # the "Regenerate profile" action
    assert client.get(f"/journeys/{journey_id}").json()["status"] == later_status


def test_same_finding_helper_is_conservative():
    assert same_finding("Believes ReLU is linear", "believes relu is LINEAR")
    assert not same_finding("Understands forward propagation", "Understands backpropagation")
