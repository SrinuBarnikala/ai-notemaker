import json
import pytest

from backend.app.db.session import SessionLocal
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.journey import LearningJourney
from backend.app.discovery.parser import (
    DiscoveryParseError,
    extract_json_object,
    fallback_question,
    parse_opening,
    parse_turn,
    question_problem,
)
from backend.app.discovery.state import (
    DiscoveryLearnerState,
    Finding,
    ground_findings,
    merge_states,
    parse_state,
)
from discovery_helpers import finding, opening, rewrite, turn

TOPIC = "How do hash tables handle collisions?"
TOPIC_STEM = "How do hash tables handle collisions"  # fallbacks quote the topic without its trailing "?"
Q1 = "Before we start: why do you think a plain array isn't enough for fast key lookups?"


# ---------------------------------------------------------------------------
# Parser and state rules (pure, no API)
# ---------------------------------------------------------------------------

def test_parser_extract_json_from_markdown():
    text = 'Here you go:\n```json\n{"focus": "Idea", "next_question": "Why does this exist?"}\n```\nHope this helps!'
    data = extract_json_object(text)
    assert data is not None and data["focus"] == "Idea"


def test_parse_opening_requires_a_question():
    assert parse_opening(opening(Q1)).question == Q1
    with pytest.raises(DiscoveryParseError):
        parse_opening("I am an AI and I don't feel like returning JSON.")
    with pytest.raises(DiscoveryParseError):
        parse_opening(json.dumps({"focus": "x"}))


def test_parse_turn_needs_question_unless_finishing():
    with pytest.raises(DiscoveryParseError):
        parse_turn(turn(question=None), TOPIC)  # not finishing and no question
    with pytest.raises(DiscoveryParseError):
        parse_turn(json.dumps({"next_question": "A real question here?"}), TOPIC)  # no state
    done = parse_turn(turn(ready=True), TOPIC)
    assert done.ready_to_finish is True and done.next_question is None


@pytest.mark.parametrize("question,expected", [
    ("What is a hash function?", None),
    ("Quick note: you mentioned chaining. How would you describe it to a friend?", None),
    ("What is a hash function? And why do collisions happen?", "more than one question"),
    ("1. What is hashing?\n2. What is chaining?", "list"),
    ("", "empty"),
])
def test_question_problem_enforces_one_question(question, expected):
    problem = question_problem(question, [])
    if expected is None:
        assert problem is None
    else:
        assert expected in problem


def test_question_problem_rejects_near_duplicates():
    asked = ["Why do you think a plain array isn't enough for fast key lookups?"]
    assert "repeats" in question_problem("Why do you think a plain array is not enough for fast key lookups?", asked)
    assert question_problem("What do you want to build with this?", asked) is None


def test_unsupported_claims_are_downgraded_to_inferred():
    state = parse_state({
        "intent": finding("Wants to build a cache", "stated", "I want to build a cache"),
        "understanding": finding("Knows hashing", "demonstrated", "invented quote the learner never said"),
        "desired_depth": finding("Deep", "stated", None),
        "available_time": {"value": "ignored", "basis": "unknown"},
    }, TOPIC)
    grounded = ground_findings(state, ["Honestly I want to build a cache for my app."])
    assert grounded.intent.basis == "stated"
    assert grounded.understanding.basis == "inferred"
    assert grounded.desired_depth.basis == "inferred"
    assert grounded.available_time is None  # unknown stays unknown


def test_merge_keeps_earlier_findings_when_later_reply_omits_them():
    earlier = DiscoveryLearnerState(
        intent=Finding(value="Pass an interview", basis="stated", evidence="interview"),
        gaps=[Finding(value="Open addressing")],
    )
    later = DiscoveryLearnerState(understanding=Finding(value="Knows chaining"), gaps=[Finding(value="Resizing")])
    merged = merge_states(earlier, later)
    assert merged.intent.value == "Pass an interview"
    assert {g.value for g in merged.gaps} == {"Open addressing", "Resizing"}


def test_fallback_question_follows_what_is_unknown_and_never_repeats():
    q1, _ = fallback_question(TOPIC, None, [])
    assert TOPIC_STEM in q1  # parameterised by the learner's topic, not a hardcoded subject
    q2, _ = fallback_question(TOPIC, None, [q1])
    assert q2 != q1
    confirmed = DiscoveryLearnerState(
        understanding=Finding(value="x", basis="stated", evidence="x"),
        intent=Finding(value="y", basis="stated", evidence="y"),
        desired_depth=Finding(value="z", basis="demonstrated", evidence="z"),
    )
    _, focus = fallback_question(TOPIC, confirmed, [])
    assert focus not in ("Current understanding", "Learning goal", "Desired depth")
    # Merely inferred findings do not count as established, so they are still worth asking about
    inferred_only = DiscoveryLearnerState(understanding=Finding(value="x"), intent=Finding(value="y"))
    _, focus = fallback_question(TOPIC, inferred_only, [])
    assert focus == "Current understanding"


# ---------------------------------------------------------------------------
# Starting a session
# ---------------------------------------------------------------------------

def new_journey(client, topic=TOPIC):
    res = client.post("/journeys", json={"topic": topic})
    assert res.status_code == 201
    return res.json()["id"]


def test_start_uses_topic_specific_opening_question(client, scripted):
    scripted.push(opening(Q1, focus="Why lookup tables exist"))
    journey_id = new_journey(client)

    res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert res.status_code == 200
    data = res.json()
    assert data["question_text"] == Q1
    assert data["concept_target"] == "Why lookup tables exist"
    assert data["question_index"] == 1 and data["is_finished"] is False
    assert data["fallback_used"] is False
    assert data["total_questions_answered"] == 0
    assert TOPIC in scripted.prompts[0]  # the actual submitted topic drives the question

    # Starting again is idempotent and does not call the model or create another row
    again = client.post(f"/journeys/{journey_id}/discovery/start")
    assert again.json()["question_text"] == Q1
    assert scripted.calls == 1
    assert len(client.get(f"/journeys/{journey_id}/discovery").json()["interactions"]) == 1


def test_start_with_unusable_model_output_uses_flagged_fallback(client, scripted):
    journey_id = new_journey(client)
    data = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert data["fallback_used"] is True
    assert TOPIC_STEM in data["question_text"]
    assert question_problem(data["question_text"], []) is None  # still exactly one question
    # analysis attempt, exactly one JSON repair, then exactly one plain-text recovery request
    assert scripted.calls == 3


def test_opening_with_two_questions_is_rewritten_to_one(client, scripted):
    scripted.push(opening("What is hashing? And what is a collision?"), rewrite(Q1))
    journey_id = new_journey(client)
    data = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert data["question_text"] == Q1 and data["fallback_used"] is False
    assert "more than one question" in scripted.prompts[1]


def test_start_provider_failure_is_retryable_and_leaves_no_partial_state(client, scripted):
    scripted.push(RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom"))
    journey_id = new_journey(client)
    res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert res.status_code == 503
    assert client.get(f"/journeys/{journey_id}/discovery").json()["interactions"] == []

    scripted.push(opening(Q1))
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["question_text"] == Q1


def test_discovery_unknown_journey(client):
    assert client.post("/journeys/unknown-id-123/discovery/start").status_code == 404
    assert client.post("/journeys/unknown-id-123/discovery/answer", json={"answer": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# Adaptive behavior
# ---------------------------------------------------------------------------

def test_next_question_depends_on_the_answer_and_conversation(client, scripted):
    scripted.push(
        opening(Q1),
        turn(question="You mentioned chaining. What happens to a bucket when it gets very long?",
             state={"understanding": finding("Knows chaining", "demonstrated", "separate chaining")}),
    )
    a = new_journey(client)
    client.post(f"/journeys/{a}/discovery/start")
    ra = client.post(f"/journeys/{a}/discovery/answer", json={"answer": "I use separate chaining with linked lists."}).json()

    scripted.push(
        opening(Q1),
        turn(question="No problem. What made you curious about hash tables?",
             state={"understanding": finding("No prior familiarity", "stated", "I have no idea")}),
    )
    b = new_journey(client)
    client.post(f"/journeys/{b}/discovery/start")
    rb = client.post(f"/journeys/{b}/discovery/answer", json={"answer": "Honestly I have no idea."}).json()

    assert ra["question_text"] != rb["question_text"]
    turn_prompt_a = scripted.prompts[1]
    assert "I use separate chaining with linked lists." in turn_prompt_a
    assert Q1 in turn_prompt_a  # the whole conversation reaches the model, not just the last answer


def test_established_information_is_carried_into_later_turns(client, scripted):
    scripted.push(
        opening(Q1),
        turn(question="What do you want to build with this?",
             state={"understanding": finding("Understands chaining", "demonstrated", "separate chaining")}),
        turn(question="How deep do you want to go?", state={}),  # later reply omits earlier findings
    )
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I use separate chaining."})
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "A cache for my app."})

    third_prompt = scripted.prompts[2]
    assert "Understands chaining [demonstrated]" in third_prompt  # model is told what is already known
    db = SessionLocal()
    try:
        rows = db.query(DiscoveryInteraction).filter_by(journey_id=journey_id).order_by(DiscoveryInteraction.question_index).all()
        second_state = json.loads(rows[1].analysis)["state"]
        assert second_state["understanding"]["value"] == "Understands chaining"  # not lost
    finally:
        db.close()


def test_repeated_question_is_rejected_and_rewritten(client, scripted):
    scripted.push(opening(Q1), turn(question=Q1), rewrite("What are you hoping to build?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Not sure."}).json()
    assert res["question_text"] == "What are you hoping to build?"
    assert "repeats an earlier question" in scripted.prompts[2]


def test_multi_question_turn_is_rewritten_to_one(client, scripted):
    scripted.push(opening(Q1), turn(question="Why? And how? And when?"), rewrite("What are you hoping to build?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Not sure."}).json()
    assert res["question_text"].count("?") == 1 and res["fallback_used"] is False


def test_malformed_turn_gets_one_repair_then_succeeds(client, scripted):
    scripted.push(opening(Q1), "not json at all", turn(question="What are you hoping to build?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "A bit."}).json()
    assert res["question_text"] == "What are you hoping to build?" and res["fallback_used"] is False
    assert scripted.calls == 3 and "could not be used" in scripted.prompts[2]


def test_persistently_malformed_turn_uses_flagged_fallback_without_fabricating(client, scripted):
    scripted.push(opening(Q1))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Not sure."}).json()
    assert res["is_finished"] is False
    assert res["fallback_used"] is True
    assert res["quick_assessment"] is None  # no invented assessment of the learner
    history = client.get(f"/journeys/{journey_id}/discovery").json()
    assert history["interactions"][0]["quick_assessment"] is None


# ---------------------------------------------------------------------------
# Completion behavior
# ---------------------------------------------------------------------------

def test_early_finish_when_enough_is_known(client, scripted):
    state = {
        "understanding": finding("Understands chaining and resizing", "demonstrated", "chaining"),
        "intent": finding("Wants to implement one in Rust", "stated", "implement one in Rust"),
    }
    scripted.push(opening(Q1), turn(state=state, ready=True, finish_reason="Goal and level are clear."))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer",
                      json={"answer": "I know chaining and resizing; I want to implement one in Rust."}).json()

    assert res["is_finished"] is True and res["total_questions_answered"] == 1
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "discovery_completed"

    db = SessionLocal()
    try:
        row = db.query(DiscoveryInteraction).filter_by(journey_id=journey_id).one()
        analysis = json.loads(row.analysis)
        assert analysis["stopped_reason"] == "sufficient"
        # Depth was never established, so it is recorded as unresolved instead of being asked or guessed
        assert any("desired depth" in u for u in analysis["state"]["unresolved"])
    finally:
        db.close()

    # Concluded sessions are idempotent and reject further answers
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["is_finished"] is True
    assert client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "more"}).status_code == 400


def test_finish_request_is_overridden_while_core_information_is_missing(client, scripted):
    scripted.push(opening(Q1), turn(state={}, ready=True), rewrite("In your own words, what is a hash table?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Hmm."}).json()
    assert res["is_finished"] is False
    assert res["question_text"] == "In your own words, what is a hash table?"


def test_garbage_model_never_ends_discovery_before_the_safety_limit(client, scripted):
    """Fallback questions must not complete discovery; only the cap does, and it is a ceiling, not a target."""
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    seen = set()
    for i in range(1, 7):
        res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": f"answer {i}"}).json()
        if i < 6:
            assert res["is_finished"] is False, f"finished early at answer {i}"
            assert res["question_text"] not in seen and res["fallback_used"] is True
            seen.add(res["question_text"])
            assert res["max_questions"] == 6
        else:
            assert res["is_finished"] is True
    history = client.get(f"/journeys/{journey_id}/discovery").json()
    assert len(history["interactions"]) == 6 and history["is_finished"] is True
    assert client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "7"}).status_code == 400


def test_safety_limit_records_what_is_unknown(client, scripted):
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    for i in range(6):
        client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": f"a{i}"})
    db = SessionLocal()
    try:
        last = db.query(DiscoveryInteraction).filter_by(journey_id=journey_id, question_index=6).one()
        analysis = json.loads(last.analysis)
        assert analysis["stopped_reason"] == "safety_limit"
        assert len(analysis["state"]["unresolved"]) == 3
        assert analysis["state"]["intent"] is None  # unknown stays unknown
    finally:
        db.close()


def test_discovery_empty_answer_and_ordering_errors(client, scripted):
    journey_id = new_journey(client)
    assert client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "hi"}).status_code == 400
    scripted.push(opening(Q1))
    client.post(f"/journeys/{journey_id}/discovery/start")
    assert client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "   "}).status_code == 422


# ---------------------------------------------------------------------------
# Failure, interruption and resume
# ---------------------------------------------------------------------------

def test_provider_failure_keeps_the_answer_and_resume_creates_no_duplicates(client, scripted):
    scripted.push(opening(Q1), RuntimeError("down"), RuntimeError("down"), RuntimeError("down"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")

    failed = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "My precious answer"})
    assert failed.status_code == 503
    assert "saved" in failed.json()["detail"]

    history = client.get(f"/journeys/{journey_id}/discovery").json()
    assert len(history["interactions"]) == 1
    assert history["interactions"][0]["learner_answer"] == "My precious answer"
    assert history["is_finished"] is False

    # A resubmission is refused (the answer already exists) instead of duplicating work
    assert client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "again"}).status_code == 409

    # Resuming completes the interrupted step exactly once
    scripted.push(turn(question="What are you hoping to build?"))
    resumed = client.post(f"/journeys/{journey_id}/discovery/start")
    assert resumed.status_code == 200 and resumed.json()["question_index"] == 2
    again = client.post(f"/journeys/{journey_id}/discovery/start")
    assert again.json()["question_index"] == 2
    assert len(client.get(f"/journeys/{journey_id}/discovery").json()["interactions"]) == 2


def test_transient_provider_error_is_retried_within_bounds(client, scripted):
    scripted.push(opening(Q1), RuntimeError("blip"), turn(question="What are you hoping to build?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "A bit."})
    assert res.status_code == 200 and res.json()["question_text"] == "What are you hoping to build?"


def test_answering_an_already_answered_question_conflicts(client, scripted):
    scripted.push(opening(Q1))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    db = SessionLocal()
    try:
        row = db.query(DiscoveryInteraction).filter_by(journey_id=journey_id).one()
        row.learner_answer = "already here"
        db.commit()
    finally:
        db.close()
    assert client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "second"}).status_code == 409


# ---------------------------------------------------------------------------
# Sessions that existed before the redesign
# ---------------------------------------------------------------------------

def test_in_flight_legacy_session_continues(client, scripted):
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Legacy Topic", status="discovery")
        db.add(journey)
        db.commit()
        db.add_all([
            DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Old Q1?",
                                 concept_target="Old Target", learner_answer="Old answer one",
                                 quick_assessment="Old insight"),
            DiscoveryInteraction(journey_id=journey.id, question_index=2, question_text="Old Q2?",
                                 concept_target="Old Target 2"),
        ])
        db.commit()
        journey_id = journey.id
    finally:
        db.close()

    pending = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert pending["question_text"] == "Old Q2?" and pending["total_questions_answered"] == 1

    scripted.push(turn(question="What would you like to build?"))
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Old answer two"}).json()
    assert res["question_index"] == 3 and res["is_finished"] is False
    assert "Old answer one" in scripted.prompts[0]  # earlier transcript still informs the model


def test_completed_or_later_journeys_do_not_restart_discovery(client, scripted):
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Done", status="profile_ready")
        db.add(journey)
        db.commit()
        db.add(DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Q?",
                                    concept_target="T", learner_answer="A"))
        db.commit()
        journey_id = journey.id
    finally:
        db.close()
    res = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert res["is_finished"] is True
    assert scripted.calls == 0
    assert len(client.get(f"/journeys/{journey_id}/discovery").json()["interactions"]) == 1
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "profile_ready"


# ---------------------------------------------------------------------------
# Frontend (static) expectations for the adaptive UI
# ---------------------------------------------------------------------------

def test_discovery_ui_is_adaptive_not_a_fixed_form(client):
    root = client.get("/")
    assert root.status_code == 200
    html = root.text
    assert 'id="disc-step-label"' in html and 'id="disc-steps"' in html
    assert 'id="disc-error"' in html and 'id="disc-error-retry"' in html
    assert "Question 1 of 4" not in html
    assert "it helps shape your notes" in html  # placeholder attribute is not truncated by stray quotes
    assert 'id="disc-progress"' not in html
    assert "Quick answer starters" not in html
    js = client.get("/static/js/journey.js")
    assert js.status_code == 200
    assert "of ${maxQ}" not in js.text and "addAnswerStarter" not in js.text
