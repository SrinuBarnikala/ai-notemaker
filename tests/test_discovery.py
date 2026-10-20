"""Discovery flow and reliability under the motive + peer-questions model."""
import json

import pytest

from backend.app.db.session import SessionLocal
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.journey import LearningJourney
from discovery_helpers import core_state, opening, turn

TOPIC = "How do hash tables handle collisions?"
MOTIVE = "I'd like to understand how you currently think hash tables avoid clashes, so the notes start in the right place."
QS = ["How would you explain what happens when two keys land in the same slot?", "Which strategies for handling that have you come across?"]


def new_journey(client, topic=TOPIC):
    return client.post("/journeys", json={"topic": topic}).json()["id"]


def answer(client, journey_id, text, **extra):
    return client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": text, **extra})


def rows(journey_id):
    db = SessionLocal()
    try:
        return db.query(DiscoveryInteraction).filter_by(journey_id=journey_id).order_by(DiscoveryInteraction.question_index).all()
    finally:
        db.close()


def history(client, journey_id):
    return client.get(f"/journeys/{journey_id}/discovery").json()


# ---------------------------------------------------------------------------
# Starting and resuming
# ---------------------------------------------------------------------------

def test_start_uses_the_submitted_topic_and_is_idempotent(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS, targets=["current_mental_model"]))
    journey_id = new_journey(client)
    res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert res.status_code == 200
    data = res.json()
    assert data["motive"] == MOTIVE and data["questions"] == QS and data["question_index"] == 1 and data["is_finished"] is False
    assert TOPIC in scripted.prompts[0]                                      # the actual submitted topic drives the group

    again = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert again["motive"] == MOTIVE and scripted.calls == 1 and len(rows(journey_id)) == 1
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "discovery"


def test_unknown_journeys_and_ordering_errors(client, scripted):
    assert client.post("/journeys/unknown-id-123/discovery/start").status_code == 404
    assert answer(client, "unknown-id-123", "x").status_code == 404
    journey_id = new_journey(client)
    assert answer(client, journey_id, "too early").status_code == 400                # nothing to answer yet
    scripted.push(opening(motive=MOTIVE, questions=QS))
    client.post(f"/journeys/{journey_id}/discovery/start")
    assert answer(client, journey_id, "   ").status_code == 422


def test_the_question_index_guard_refuses_a_stale_submission(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), turn(question="Which load factor do you think is too high?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    assert answer(client, journey_id, "my reply", question_index=2).status_code == 409        # not the active group
    assert rows(journey_id)[0].learner_answer is None
    assert answer(client, journey_id, "my reply", question_index=1).status_code == 200


# ---------------------------------------------------------------------------
# Malformed output
# ---------------------------------------------------------------------------

def test_a_malformed_opening_gets_one_repair_then_succeeds(client, scripted):
    scripted.push("not json", opening(motive=MOTIVE, questions=QS))
    data = client.post(f"/journeys/{new_journey(client)}/discovery/start").json()
    assert data["questions"] == QS and data["fallback_used"] is False
    assert scripted.calls == 2 and "could not be used" in scripted.prompts[1]


def test_a_persistently_malformed_opening_regenerates_once_and_then_uses_a_flagged_generic_group(client, scripted):
    journey_id = new_journey(client)                                          # everything the model says is unusable
    data = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert data["fallback_used"] is True and data["motive"] and data["questions"]
    assert TOPIC.rstrip("?") in data["question_text"]
    assert scripted.calls == 3                                                # attempt, one repair, one regeneration; nothing more
    assert json.loads(rows(journey_id)[0].analysis)["question_source"] == "fallback"


def test_a_malformed_turn_gets_one_repair_then_succeeds(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), "garbage", turn(question="Which load factor do you think is too high?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = answer(client, journey_id, "Chaining, mostly.").json()
    assert res["questions"] == ["Which load factor do you think is too high?"] and res["fallback_used"] is False
    assert scripted.calls == 3 and "could not be used" in scripted.prompts[2]


def test_a_persistently_malformed_turn_changes_nothing_about_the_learner_and_invents_no_assessment(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = answer(client, journey_id, "Chaining, mostly.").json()
    assert res["is_finished"] is False and res["fallback_used"] is True and res["quick_assessment"] is None
    saved = json.loads(rows(journey_id)[0].analysis)
    assert saved["analysis_failed"] is True
    assert saved["state"]["understanding"] is None and saved["state"]["intent"] is None and saved["state"]["gaps"] == []
    assert history(client, journey_id)["interactions"][0]["quick_assessment"] is None


def test_a_state_reply_without_a_group_is_malformed_unless_the_model_is_finishing(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), turn(group_override=None), turn(question="Which load factor do you think is too high?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = answer(client, journey_id, "Chaining, mostly.").json()                  # the first reply had no group, so it was repaired
    assert res["questions"] == ["Which load factor do you think is too high?"]


# ---------------------------------------------------------------------------
# Provider failures, retries and resume
# ---------------------------------------------------------------------------

def test_a_provider_failure_while_starting_is_retryable_and_leaves_nothing_behind(client, scripted):
    scripted.push(RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom"))
    journey_id = new_journey(client)
    assert client.post(f"/journeys/{journey_id}/discovery/start").status_code == 503
    assert history(client, journey_id)["interactions"] == []
    scripted.push(opening(motive=MOTIVE, questions=QS))
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["questions"] == QS


def test_a_provider_failure_keeps_the_answer_and_resume_creates_no_duplicates(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), RuntimeError("down"), RuntimeError("down"), RuntimeError("down"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")

    failed = answer(client, journey_id, "My precious answer")
    assert failed.status_code == 503 and "saved" in failed.json()["detail"]
    saved = history(client, journey_id)
    assert len(saved["interactions"]) == 1 and saved["interactions"][0]["learner_answer"] == "My precious answer"
    assert answer(client, journey_id, "again").status_code == 409                          # a resubmission is refused, not duplicated

    scripted.push(turn(question="Which load factor do you think is too high?"))
    resumed = client.post(f"/journeys/{journey_id}/discovery/start")
    assert resumed.status_code == 200 and resumed.json()["question_index"] == 2
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["question_index"] == 2
    assert len(history(client, journey_id)["interactions"]) == 2


def test_a_transient_provider_error_is_retried_within_bounds(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), RuntimeError("blip"), turn(question="Which load factor do you think is too high?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = answer(client, journey_id, "Chaining, mostly.")
    assert res.status_code == 200 and res.json()["questions"] == ["Which load factor do you think is too high?"]


def test_answering_an_already_answered_group_conflicts(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    db = SessionLocal()
    try:
        db.query(DiscoveryInteraction).filter_by(journey_id=journey_id).one().learner_answer = "already here"
        db.commit()
    finally:
        db.close()
    assert answer(client, journey_id, "second").status_code == 409


# ---------------------------------------------------------------------------
# Finishing and journeys that moved on
# ---------------------------------------------------------------------------

def test_finishing_marks_the_journey_and_refuses_further_answers(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), turn(state=core_state("chaining with linked lists"), ready=True))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    done = answer(client, journey_id, "I'd use chaining with linked lists for everything.").json()
    assert done["is_finished"] is True and done["questions"] == [] and done["motive"] is None
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "discovery_completed"
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["is_finished"] is True
    assert answer(client, journey_id, "more").status_code == 400


@pytest.mark.parametrize("later_status", ["profile_ready", "architecture_ready", "note_generated"])
def test_finishing_never_moves_a_later_journey_backwards(client, scripted, later_status):
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Past discovery", status=later_status)
        db.add(journey)
        db.commit()
        db.add(DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Still pending?", concept_target="T",
                                    motive=MOTIVE, questions=json.dumps(["Still pending?"])))
        db.commit()
        journey_id = journey.id
    finally:
        db.close()
    scripted.push(turn(state=core_state("chaining with linked lists"), ready=True))
    res = answer(client, journey_id, "I'd use chaining with linked lists for everything.")
    assert res.status_code == 200 and res.json()["is_finished"] is True
    assert client.get(f"/journeys/{journey_id}").json()["status"] == later_status


def test_completed_or_later_journeys_do_not_restart_discovery(client, scripted):
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Done", status="profile_ready")
        db.add(journey)
        db.commit()
        db.add(DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Q?", concept_target="T", learner_answer="A"))
        db.commit()
        journey_id = journey.id
    finally:
        db.close()
    res = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert res["is_finished"] is True and scripted.calls == 0
    assert len(history(client, journey_id)["interactions"]) == 1
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "profile_ready"


# ---------------------------------------------------------------------------
# The interface
# ---------------------------------------------------------------------------

def test_the_interface_shows_a_motive_peer_questions_one_answer_field_and_question_based_progress(client):
    html = client.get("/").text
    assert 'id="disc-motive"' in html and 'id="disc-questions"' in html and 'class="peer-questions"' in html
    assert "Why I'm asking" in html                                            # the motive is labelled as a reason, never as a question
    assert html.count('id="disc-answer-input"') == 1 and html.count('id="btn-answer-submit"') == 1
    assert 'id="disc-progress"' in html and 'id="disc-step-label"' in html
    assert "in one message" in html and "numbered" not in html.split('id="disc-answer-input"')[1].split("</textarea>")[0]
    assert "<ol" not in html.split('id="disc-motive-block"')[1].split('id="disc-answer-input"')[0]      # peers are not numbered or nested
    assert "Question 1 of 4" not in html and 'id="disc-steps"' not in html and "disc-subquestions" not in html


def test_the_script_renders_text_safely_and_counts_individual_questions(client):
    js = client.get("/static/js/journey.js").text
    assert "li.textContent = text" in js and "document.getElementById('disc-motive').textContent = data.motive" in js
    assert "Questions asked: ${asked} of up to ${max}" in js and "data.questions_asked" in js
    assert "item.motive" in js and "escapeHtml(item.motive)" in js and "item.questions.map(q => `<li>${escapeHtml(q)}</li>`" in js
    assert "subquestion" not in js.lower() and "renderStepDots" not in js
    assert "setAwaitingResume" in js and "question_index: currentQuestionIndex" in js


def test_the_stylesheet_has_the_motive_and_peer_question_styles(client):
    css = client.get("/static/css/main.css").text
    for selector in (".motive-label", ".peer-questions", ".peer-questions li", ".group-hint", ".qa-motive", ".qa-questions"):
        assert selector in css
    assert ".question-subs" not in css and ".disc-step-dot" not in css
