"""The nine learner dimensions, coverage computed from evidence, stopping rules, and adaptive + coverage-driven selection."""
import json

from backend.app.discovery.dimensions import (
    CONFLICTING, CONFUSIONS, CORE_DIMENSIONS, DESIRED_DEPTH, DESIRED_OUTCOME, DIMENSIONS, FAMILIARITY, LEARNING_APPROACH,
    LEARNING_INTENTION, MENTAL_MODEL, NONE, NOT_RELEVANT, OUTDATED, PARTIAL, SUFFICIENT, COMMITMENT, CONSTRAINTS,
    DimensionNote, attempts_by_dimension, blocking_dimensions, compute_coverage, coverage_guard, neglected_core,
    parse_dimension_notes, unprobed_misconceptions,
)
from backend.app.discovery.state import DiscoveryLearnerState, Finding, ResolvedItem
from backend.app.db.session import SessionLocal
from backend.app.models.discovery import DiscoveryInteraction
from discovery_helpers import core_state, finding, opening, profile_json, turn

TOPIC = "How do convolutional neural networks work?"
R1 = "I started learning CNNs because my team needs an image classifier. I want to build a working classifier for product photos."
R2 = "I learn best from diagrams and worked examples. I'd like to understand the mechanisms in detail, not just the overview."
R3 = ("A filter slides over the image and multiplies local pixels by weights to detect edges, then deeper layers combine those into shapes. "
      "I am not sure how the network learns the filter weights, and I can only give this an hour or two each week.")

INTENT = finding("Needs to build an image classifier for work", "stated", "my team needs an image classifier")
OUTCOME = finding("Build a working product-photo classifier", "stated", "build a working classifier for product photos")
APPROACH = finding("Diagrams and worked examples", "stated", "I learn best from diagrams and worked examples")
DEPTH = finding("Detailed mechanisms", "stated", "understand the mechanisms in detail")
MODEL = finding("Filters detect edges, deeper layers combine them", "demonstrated", "A filter slides over the image and multiplies local pixels by weights to detect edges")
GAP = finding("How filter weights are learned", "stated", "not sure how the network learns the filter weights")

M = lambda n: f"I'd like to understand aspect{n}x1 aspect{n}x2 aspect{n}x3 aspect{n}x4 aspect{n}x5 about you, so the notes fit."


def new_journey(client, topic=TOPIC):
    return client.post("/journeys", json={"topic": topic}).json()["id"]


def answer(client, journey_id, text, **extra):
    return client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": text, **extra})


def analysis_of(journey_id, index):
    db = SessionLocal()
    try:
        row = db.query(DiscoveryInteraction).filter_by(journey_id=journey_id, question_index=index).one()
        return json.loads(row.analysis)
    finally:
        db.close()


def F(value, basis="stated", **kw):
    return Finding(value=value, basis=basis, evidence=kw.pop("evidence", "quote text here"), **kw)


def g(targets=None, answered=True, index=1):
    return {"question_index": index, "targets": targets or [], "learner_answer": "a reply" if answered else None}


# ---------------------------------------------------------------------------
# Coverage is computed from evidence, for all nine dimensions
# ---------------------------------------------------------------------------

def test_all_nine_dimensions_are_tracked_and_start_empty():
    coverage = compute_coverage(DiscoveryLearnerState())
    assert list(coverage) == list(DIMENSIONS) and len(DIMENSIONS) == 9
    assert all(c.status == NONE and c.grounded == 0 and c.attempts == 0 for c in coverage.values())
    assert set(CORE_DIMENSIONS) == {LEARNING_INTENTION, DESIRED_OUTCOME, LEARNING_APPROACH, DESIRED_DEPTH, MENTAL_MODEL}


def test_every_dimension_has_a_place_in_the_learner_state():
    state = DiscoveryLearnerState(
        intent=F("a"), desired_outcome=F("b"), explanation_preferences=[F("c")], challenge_willingness=F("d"), understanding=F("e"),
        related_familiarity=[F("f")], desired_depth=F("g"), gaps=[F("h")], available_time=F("i"),
    )
    coverage = compute_coverage(state)
    assert {d: c.status for d, c in coverage.items()} == {d: SUFFICIENT for d in DIMENSIONS}
    # the extra fields that carry more of dimensions 3, 8 and 9
    for extra, dim in (("observed_approach", LEARNING_APPROACH), ("questions_to_answer", CONFUSIONS), ("constraints", "practical_constraints"),
                       ("misconceptions", CONFUSIONS)):
        assert compute_coverage(DiscoveryLearnerState(**{extra: [F("x")]}))[dim].status == SUFFICIENT


def test_evidence_decides_the_status_inferences_alone_are_only_partial():
    state = DiscoveryLearnerState(intent=Finding(value="probably curious", basis="inferred"), understanding=F("knows layers", "demonstrated"))
    coverage = compute_coverage(state)
    assert coverage[LEARNING_INTENTION].status == PARTIAL and coverage[LEARNING_INTENTION].inferred == 1
    assert coverage[MENTAL_MODEL].status == SUFFICIENT and coverage[MENTAL_MODEL].grounded == 1
    assert coverage[DESIRED_OUTCOME].status == NONE


def test_a_conflict_flagged_by_the_model_outranks_apparent_sufficiency():
    state = DiscoveryLearnerState(understanding=F("knows layers", "demonstrated"),
                                  dimension_notes={MENTAL_MODEL: DimensionNote(conflict=True, reason="says they know backprop but described it wrongly")})
    c = compute_coverage(state)[MENTAL_MODEL]
    assert c.status == CONFLICTING and "described it wrongly" in c.reason


def test_a_corrected_dimension_is_outdated_until_something_replaces_it():
    state = DiscoveryLearnerState(resolved=[ResolvedItem(field="intent", value="pass an exam", corrected_in=2)])
    assert compute_coverage(state)[LEARNING_INTENTION].status == OUTDATED
    state.intent = F("wants to build a product")
    assert compute_coverage(state)[LEARNING_INTENTION].status == SUFFICIENT


def test_irrelevance_is_honoured_only_for_supporting_dimensions_and_only_with_a_reason():
    notes = parse_dimension_notes([
        {"dimension": CONSTRAINTS, "status": "not_relevant", "reason": "no deadline or special environment"},
        {"dimension": COMMITMENT, "status": "not_relevant"},                          # no reason: ignored
        {"dimension": LEARNING_APPROACH, "status": "not_relevant", "reason": "skip"},  # core: never allowed
        {"dimension": "made_up", "status": "not_relevant", "reason": "x"},
        {"dimension": MENTAL_MODEL, "status": "conflicting", "reason": "contradicts itself"},
        "junk",
    ])
    assert set(notes) == {CONSTRAINTS, MENTAL_MODEL}
    coverage = compute_coverage(DiscoveryLearnerState(dimension_notes=notes))
    assert coverage[CONSTRAINTS].status == NOT_RELEVANT and coverage[CONSTRAINTS].reason == "no deadline or special environment"
    assert coverage[LEARNING_APPROACH].status == NONE                                  # the core dimension still counts
    assert parse_dimension_notes([{"dimension": MENTAL_MODEL, "status": "relevant"}])[MENTAL_MODEL].conflict is False


def test_attempts_count_answered_groups_per_dimension():
    groups = [g([LEARNING_INTENTION, DESIRED_OUTCOME], True, 1), g([LEARNING_APPROACH], True, 2), g([LEARNING_APPROACH], False, 3), g(["nonsense"], True, 4)]
    assert attempts_by_dimension(groups) == {LEARNING_INTENTION: 1, DESIRED_OUTCOME: 1, LEARNING_APPROACH: 1}   # a pending group has produced nothing


def test_blocking_dimensions_relax_after_repeated_unanswered_attempts():
    state = DiscoveryLearnerState(intent=F("a"), desired_outcome=F("b"), understanding=F("c"), desired_depth=F("d"))
    assert blocking_dimensions(compute_coverage(state)) == [LEARNING_APPROACH]
    assert blocking_dimensions(compute_coverage(state, {LEARNING_APPROACH: 1})) == [LEARNING_APPROACH]
    assert blocking_dimensions(compute_coverage(state, {LEARNING_APPROACH: 2})) == []      # asked twice: stop nagging, record it
    conflicted = DiscoveryLearnerState(**{**state.model_dump(), "explanation_preferences": [], "dimension_notes": {LEARNING_APPROACH: DimensionNote(conflict=True, reason="mixed")}})
    assert blocking_dimensions(compute_coverage(conflicted, {LEARNING_APPROACH: 2})) == [LEARNING_APPROACH]   # conflicts get a third try


def test_neglected_core_dimensions_are_the_unevidenced_never_asked_ones():
    state = DiscoveryLearnerState(intent=F("a"))
    assert neglected_core(compute_coverage(state, {LEARNING_APPROACH: 1})) == [DESIRED_OUTCOME, DESIRED_DEPTH, MENTAL_MODEL]


def test_a_misconception_is_unprobed_until_a_later_group_targets_confusions():
    state = DiscoveryLearnerState(misconceptions=[F("more layers always means better", "demonstrated", source_card=2)])
    assert unprobed_misconceptions(state, [g([MENTAL_MODEL], True, 2)]) == ["more layers always means better"]
    assert unprobed_misconceptions(state, [g([MENTAL_MODEL], True, 2), g([CONFUSIONS], False, 3)]) != []          # pending: not yet probed
    assert unprobed_misconceptions(state, [g([MENTAL_MODEL], True, 2), g([CONFUSIONS], True, 3)]) == []
    assert unprobed_misconceptions(DiscoveryLearnerState(misconceptions=[Finding(value="x", basis="inferred", source_card=1)]), []) == []   # only evidenced ones count


# ---------------------------------------------------------------------------
# Evidence is attributed to the interaction it came from
# ---------------------------------------------------------------------------

def test_findings_are_traced_to_the_group_whose_reply_contains_their_evidence(client, scripted):
    scripted.push(
        opening(motive=M(1), questions=["What prompted you to learn CNNs?"], targets=[LEARNING_INTENTION, DESIRED_OUTCOME]),
        turn(state={"intent": INTENT, "desired_outcome": OUTCOME}, motive=M(2), questions=["How do you like to learn technical ideas?"], targets=[LEARNING_APPROACH, DESIRED_DEPTH]),
        turn(state={"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH},
             motive=M(3), questions=["How would you explain what a convolution does?"], targets=[MENTAL_MODEL]),
        turn(state={"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH, "understanding": MODEL, "gaps": [GAP]}, ready=True),
    )
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    answer(client, journey_id, R1)
    answer(client, journey_id, R2)
    assert answer(client, journey_id, R3).json()["is_finished"] is True

    state = analysis_of(journey_id, 3)["state"]
    assert state["intent"]["source_card"] == 1 and state["desired_outcome"]["source_card"] == 1       # restated later, still traced to group 1
    assert state["explanation_preferences"][0]["source_card"] == 2 and state["desired_depth"]["source_card"] == 2
    assert state["understanding"]["source_card"] == 3 and state["gaps"][0]["source_card"] == 3
    assert state["intent"]["basis"] == "stated" and state["understanding"]["basis"] == "demonstrated"   # said vs shown stay distinct
    assert analysis_of(journey_id, 3)["stopped_reason"] == "sufficient"


def test_unknown_dimensions_stay_unknown_and_unsupported_claims_are_not_fabricated(client, scripted):
    state = core_state("my team needs an image classifier")
    state["available_time"] = finding("Two hours a week", "stated", "two hours every single week")     # not in the reply
    state["challenge_willingness"] = finding("Loves a challenge", "stated", "I love hard problems")     # not in the reply
    scripted.push(opening(motive=M(1), questions=["What prompted you to learn CNNs?"]), turn(state=state, ready=True))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    assert answer(client, journey_id, R1).json()["is_finished"] is True
    saved = analysis_of(journey_id, 1)["state"]
    for field in ("available_time", "challenge_willingness"):
        assert saved[field]["basis"] == "inferred" and saved[field]["evidence"] is None and saved[field]["source_card"] is None
    coverage = analysis_of(journey_id, 1)["coverage"]
    assert coverage[COMMITMENT]["status"] == PARTIAL and coverage[CONSTRAINTS]["status"] == PARTIAL      # guessed, not established
    assert coverage[FAMILIARITY]["status"] == NONE and coverage[CONFUSIONS]["status"] == NONE            # never mentioned: unknown


# ---------------------------------------------------------------------------
# Stopping considers coverage and evidence quality, not only the model's "done"
# ---------------------------------------------------------------------------

def _session(client, scripted, *items):
    scripted.push(opening(motive=M(1), questions=["What prompted you to learn CNNs?"], targets=[LEARNING_INTENTION, DESIRED_OUTCOME]), *items)
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    return journey_id


def test_the_model_saying_done_is_not_enough_when_core_dimensions_are_only_guessed(client, scripted):
    guessed = {d: finding(f"guess {d}", "inferred") for d in ("intent", "desired_outcome", "understanding", "desired_depth")}
    guessed["explanation_preferences"] = [finding("probably diagrams", "inferred")]
    journey_id = _session(client, scripted, turn(state=guessed, ready=True, finish_reason="seems fine"),
                          opening(motive=M(2), questions=["How do you usually like technical ideas to be explained to you?"], targets=[LEARNING_APPROACH]))
    res = answer(client, journey_id, "I don't know really.").json()
    assert res["is_finished"] is False and res["questions"] == ["How do you usually like technical ideas to be explained to you?"]
    assert "Finish request overridden" not in json.dumps(res)                                           # (logged, not shown to the learner)
    assert all(c["status"] == "partial" for k, c in analysis_of(journey_id, 1)["coverage"].items() if k in ("learning_intention", "learning_approach"))


def test_discovery_can_finish_after_one_group_when_the_evidence_is_there(client, scripted):
    state = {"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH, "understanding": MODEL}
    journey_id = _session(client, scripted, turn(state=state, ready=True, finish_reason="all clear"))
    res = answer(client, journey_id, R1 + " " + R2 + " " + R3).json()
    assert res["is_finished"] is True and res["questions_asked"] == 1
    saved = analysis_of(journey_id, 1)
    assert saved["stopped_reason"] == "sufficient" and saved["state"]["unresolved"] == []
    assert {k: v["status"] for k, v in saved["coverage"].items() if k in CORE_DIMENSIONS} == {d: "sufficient" for d in CORE_DIMENSIONS}


def test_a_dimension_asked_about_twice_without_evidence_stops_blocking_and_stays_visible(client, scripted):
    four = {"intent": INTENT, "desired_outcome": OUTCOME, "desired_depth": DEPTH, "understanding": MODEL}
    reply1 = R1 + " " + R2 + " " + R3
    journey_id = _session(
        client, scripted,
        turn(state=four, motive=M(2), questions=["How do you like to learn technical ideas?"], targets=[LEARNING_APPROACH]),     # attempt 1
        turn(state=four, ready=True),                                                                                           # refused: approach asked once
        opening(motive=M(3), questions=["Which kind of explanation has helped you most before?"], targets=[LEARNING_APPROACH]),  # attempt 2
        turn(state=four, ready=True),                                                                                           # now allowed
    )
    answer(client, journey_id, reply1)
    assert answer(client, journey_id, "No particular preference.").json()["is_finished"] is False
    last = answer(client, journey_id, "Honestly, whatever works.").json()
    assert last["is_finished"] is True
    saved = analysis_of(journey_id, 3)
    assert "Not established: learning approach" in saved["state"]["unresolved"]                                                    # visible, never fabricated
    assert saved["coverage"][LEARNING_APPROACH]["status"] == "none" and saved["coverage"][LEARNING_APPROACH]["attempts"] == 2


def test_an_unresolved_conflict_keeps_discovery_going_until_the_learner_clears_it(client, scripted):
    reply1 = R1 + " " + R2 + " " + R3
    state = {**core_state("my team needs an image classifier"), "understanding": MODEL}
    conflict = [{"dimension": MENTAL_MODEL, "status": "conflicting", "reason": "says they know backprop but described it as random search"}]
    journey_id = _session(
        client, scripted,
        turn(state=state, ready=True, dimension_notes=conflict),
        opening(motive=M(2), questions=["How would you describe, step by step, how a network adjusts its weights?"], targets=[MENTAL_MODEL]),
        turn(state=state, ready=True, dimension_notes=[{"dimension": MENTAL_MODEL, "status": "relevant"}]),
    )
    first = answer(client, journey_id, reply1).json()
    assert first["is_finished"] is False and first["targets"] == [MENTAL_MODEL]
    assert analysis_of(journey_id, 1)["coverage"][MENTAL_MODEL]["status"] == "conflicting"
    assert answer(client, journey_id, "It nudges weights downhill using the error, so not random.").json()["is_finished"] is True


def test_a_correction_makes_a_dimension_outdated_and_blocks_finishing_until_re_established(client, scripted):
    reply2 = "Actually I am not doing this for work anymore; this is a personal project to recognise birds, which I want to build."
    state = {"outcome_only": None, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH, "understanding": MODEL}
    corrected = {k: v for k, v in state.items() if k != "outcome_only"}
    corrected["desired_outcome"] = finding("Recognise birds as a personal project", "stated", "personal project to recognise birds")
    journey_id = _session(
        client, scripted,
        turn(state={"intent": INTENT, **corrected}, motive=M(2), questions=["How is your project going so far?"], targets=[DESIRED_OUTCOME]),
        turn(state=corrected, retractions=[{"field": "intent", "value": "Needs to build an image classifier for work", "reason": "no longer for work"}], ready=True),
        opening(motive=M(3), questions=["What is it about the bird project that made you want to learn this?"], targets=[LEARNING_INTENTION]),
    )
    reply1 = R1 + " " + R2 + " " + R3
    corrected["explanation_preferences"] = [APPROACH]
    answer(client, journey_id, reply1)
    res = answer(client, journey_id, reply2 + " " + R2).json()
    assert res["is_finished"] is False                                           # the intention was retracted and nothing replaced it
    saved = analysis_of(journey_id, 2)
    assert saved["coverage"][LEARNING_INTENTION]["status"] == "outdated"
    assert [(r["field"], r["corrected_in"]) for r in saved["state"]["resolved"]] == [("intent", 2)]    # correction history is preserved


def test_an_irrelevant_supporting_dimension_is_not_forced_and_is_recorded_with_its_reason(client, scripted):
    state = {"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH, "understanding": MODEL}
    notes = [{"dimension": CONSTRAINTS, "status": "not_relevant", "reason": "a personal project with no deadline"},
             {"dimension": LEARNING_APPROACH, "status": "not_relevant", "reason": "model tries to skip a core dimension"}]
    journey_id = _session(client, scripted, turn(state=state, ready=True, dimension_notes=notes), profile_json())
    assert answer(client, journey_id, R1 + " " + R2 + " " + R3).json()["is_finished"] is True
    coverage = analysis_of(journey_id, 1)["coverage"]
    assert coverage[CONSTRAINTS]["status"] == "not_relevant" and coverage[CONSTRAINTS]["reason"] == "a personal project with no deadline"
    assert coverage[LEARNING_APPROACH]["status"] == "sufficient"                  # core dimensions cannot be waved away
    ctx = client.post(f"/journeys/{journey_id}/knowledge-profile").json()["learner_context"]
    assert ctx["dimension_notes"][CONSTRAINTS]["relevance"] == "not_relevant"
    assert all(n["relevance"] != "not_relevant" for d, n in ctx["dimension_notes"].items() if d == LEARNING_APPROACH)


def test_a_group_that_only_revisits_established_dimensions_ends_discovery(client, scripted):
    state = {"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH, "understanding": MODEL}
    journey_id = _session(client, scripted, turn(state=state, motive=M(2), questions=["Why do you want to learn CNNs, once more?"], targets=[LEARNING_INTENTION]))
    res = answer(client, journey_id, R1 + " " + R2 + " " + R3).json()
    assert res["is_finished"] is True and res["questions_asked"] == 1             # nothing material was left, so no padding group
    assert analysis_of(journey_id, 1)["stopped_reason"] == "sufficient"


def test_a_material_open_issue_keeps_discovery_going_but_only_for_a_couple_of_tries(client, scripted):
    state = {"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH], "desired_depth": DEPTH, "understanding": MODEL}
    issue = [{"dimension": CONFUSIONS, "issue": "unclear which framework they must use", "impact": "high"}]
    reply1 = R1 + " " + R2 + " " + R3
    journey_id = _session(
        client, scripted,
        turn(state=state, ready=True, open_issues=issue),
        opening(motive=M(2), questions=["Which framework or tools do you have to use?"], targets=[CONFUSIONS]),
        turn(state=state, ready=True, open_issues=issue),
        opening(motive=M(3), questions=["Is anything about the tooling still unclear to you?"], targets=[CONFUSIONS]),
        turn(state=state, ready=True, open_issues=issue),
    )
    assert answer(client, journey_id, reply1).json()["is_finished"] is False
    assert answer(client, journey_id, "Probably PyTorch, I think.").json()["is_finished"] is False
    assert answer(client, journey_id, "No idea honestly.").json()["is_finished"] is True        # asked twice: it stops blocking
    assert any(u.startswith("Open question (confusions, gaps and open questions): unclear which framework") for u in analysis_of(journey_id, 3)["state"]["unresolved"])


def test_when_the_budget_runs_out_the_unresolved_core_dimensions_are_preserved(client, scripted, test_settings):
    test_settings.discovery_max_questions = 2
    journey_id = _session(client, scripted, turn(state={"intent": INTENT}, motive=M(2), questions=["How do you like to learn technical ideas?"], targets=[LEARNING_APPROACH]))
    answer(client, journey_id, R1)
    res = answer(client, journey_id, "Not sure.").json()
    assert res["is_finished"] is True and res["questions_asked"] == 2
    saved = analysis_of(journey_id, 2)
    assert saved["stopped_reason"] == "safety_limit"
    for label in ("desired outcome", "learning approach", "desired depth", "current mental model"):
        assert f"Not established: {label}" in saved["state"]["unresolved"]
    assert saved["state"]["desired_outcome"] is None and saved["state"]["understanding"] is None


# ---------------------------------------------------------------------------
# Adaptive follow-up and coverage-driven selection work together
# ---------------------------------------------------------------------------

def test_the_opening_group_is_asked_to_establish_intention_outcome_approach_and_depth_first(client, scripted):
    scripted.push(opening(motive=M(1), questions=["What prompted you to learn CNNs?"], targets=[LEARNING_INTENTION]))
    client.post(f"/journeys/{new_journey(client)}/discovery/start")
    prompt = scripted.prompts[0]
    assert "FIRST question group" in prompt and TOPIC in prompt
    assert "learning intention, desired outcome, learning approach and initial desired depth" in prompt
    assert "must not collect every detail now" in prompt and "at most 5 question(s)" in prompt


def test_the_second_group_must_explore_the_learning_approach_unless_it_is_already_known(client, scripted):
    journey_id = _session(
        client, scripted,
        turn(state={"intent": INTENT, "desired_outcome": OUTCOME}, motive=M(2), questions=["How would you explain what a filter does?"], targets=[MENTAL_MODEL]),
        opening(motive=M(3), questions=["How do you like to learn technical ideas?"], targets=[LEARNING_APPROACH, DESIRED_DEPTH]),
    )
    res = answer(client, journey_id, R1).json()
    assert LEARNING_APPROACH in res["targets"] and res["questions"] == ["How do you like to learn technical ideas?"]
    assert "the learning approach has not been explored yet" in scripted.prompts[2]       # the regeneration was told why
    assert res["fallback_used"] is False


def test_the_approach_requirement_is_not_forced_when_the_reply_already_evidenced_it(client, scripted):
    journey_id = _session(
        client, scripted,
        turn(state={"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH]},
             motive=M(2), questions=["How would you explain what a filter does?"], targets=[MENTAL_MODEL]),
    )
    res = answer(client, journey_id, R1 + " " + R2).json()
    assert res["targets"] == [MENTAL_MODEL] and scripted.calls == 2                      # accepted outright: no regeneration


def test_the_next_group_can_switch_dimension_instead_of_following_the_last_answer(client, scripted):
    journey_id = _session(
        client, scripted,
        turn(state={"intent": INTENT, "desired_outcome": OUTCOME, "explanation_preferences": [APPROACH]},
             motive=M(2), questions=["How would you explain what a filter does to an image?"], targets=[MENTAL_MODEL]),
    )
    res = answer(client, journey_id, R1 + " " + R2).json()
    assert res["targets"] == [MENTAL_MODEL]                                              # the reply was all about projects; the next group is not


def test_a_narrowing_tangent_is_cut_off_and_the_conversation_returns_to_neglected_dimensions(client, scripted):
    cheap = lambda n, dim: dict(motive=M(n), questions=[f"What do you make of detail{n}x1 and detail{n}x2 so far?"], targets=[dim])
    journey_id = _session(
        client, scripted,
        turn(state={"explanation_preferences": [APPROACH]}, **cheap(2, CONFUSIONS)),                  # a first tangent is tolerated
        turn(state={"explanation_preferences": [APPROACH]}, **cheap(3, CONFUSIONS)),                  # a second in a row is refused...
        opening(motive=M(4), questions=["How deep would you like to go with the mathematics?"], targets=[DESIRED_DEPTH]),   # ...and replaced
    )
    answer(client, journey_id, R2)
    res = answer(client, journey_id, "Some detail about it.").json()
    assert res["targets"] == [DESIRED_DEPTH] and res["fallback_used"] is False
    assert "(desired_depth, current_mental_model)" in scripted.prompts[3] or "desired_depth, current_mental_model" in scripted.prompts[3]
    assert "two groups in a row ignored dimensions that have never been explored" in scripted.prompts[3]


def test_a_significant_misconception_may_be_investigated_before_switching_dimensions(client, scripted):
    wrong = finding("Believes more layers always means better accuracy", "demonstrated", "more layers is always better")
    reply = "I just assume more layers is always better, so I would simply stack as many as possible."
    journey_id = _session(
        client, scripted,
        turn(state={"explanation_preferences": [APPROACH]}, motive=M(2), questions=["How do you decide how many layers a network needs?"], targets=[MENTAL_MODEL]),
        turn(state={"explanation_preferences": [APPROACH], "misconceptions": [wrong]}, motive=M(3),
             questions=["What do you expect to happen when a network gets much deeper?"], targets=[CONFUSIONS]),    # allowed despite neglected core
        turn(state={"explanation_preferences": [APPROACH], "misconceptions": [wrong], "intent": INTENT, "desired_outcome": OUTCOME, "desired_depth": DEPTH, "understanding": MODEL}, ready=True),
    )
    answer(client, journey_id, R2)
    probe = answer(client, journey_id, reply).json()
    assert probe["targets"] == [CONFUSIONS] and "ignored dimensions" not in "".join(scripted.prompts)
    # while the misconception is unexamined the model cannot end discovery even if every core dimension looks covered
    journey2 = _session(client, scripted,
        turn(state={"explanation_preferences": [APPROACH], "intent": INTENT, "desired_outcome": OUTCOME, "desired_depth": DEPTH, "understanding": MODEL, "misconceptions": [wrong]},
             ready=True),
        opening(motive=M(5), questions=["What would happen to training if the network were far deeper?"], targets=[CONFUSIONS]),
    )
    assert answer(client, journey2, R1 + " " + R2 + " " + R3 + " " + reply).json()["is_finished"] is False


def test_different_replies_produce_different_next_groups_that_use_those_replies(client, scripted):
    results = {}
    for key, reply, nxt in (
        ("diagrams", "I think in pictures: draw it for me. I want to build a classifier.", turn(state={"explanation_preferences": [finding("Pictures", "stated", "I think in pictures")]}, motive=M(2), questions=["Which part of a CNN would you like drawn first?"], targets=[MENTAL_MODEL])),
        ("maths", "Give me the equations. I need this for a research paper.", turn(state={"explanation_preferences": [finding("Equations", "stated", "Give me the equations")]}, motive=M(3), questions=["How comfortable are you with convolution as an integral?"], targets=[DESIRED_DEPTH])),
    ):
        journey_id = _session(client, scripted, nxt)
        results[key] = answer(client, journey_id, reply).json()
        assert reply in scripted.prompts[-1]                                     # the model sees what this learner actually said
    assert results["diagrams"]["motive"] != results["maths"]["motive"] and results["diagrams"]["questions"] != results["maths"]["questions"]


def test_a_repeated_motive_or_question_is_not_asked_again(client, scripted):
    journey_id = _session(
        client, scripted,
        turn(state={"explanation_preferences": [APPROACH]}, motive=M(1), questions=["What prompted you to learn CNNs?"], targets=[MENTAL_MODEL]),   # same motive and question
        opening(motive=M(6), questions=["How would you explain what a filter does?"], targets=[MENTAL_MODEL]),
    )
    res = answer(client, journey_id, R2).json()
    assert res["questions"] == ["How would you explain what a filter does?"]
    assert "the motive repeats an earlier motive" in scripted.prompts[2]


def test_the_model_sees_the_coverage_table_the_budget_and_both_selection_lenses(client, scripted):
    journey_id = _session(client, scripted,
        turn(state={"intent": INTENT}, motive=M(2), questions=["How do you like to learn technical ideas?"], targets=[LEARNING_APPROACH]),
        turn(state={"intent": INTENT}, motive=M(3), questions=["What would you like to build with CNNs?"], targets=[DESIRED_OUTCOME]))
    answer(client, journey_id, R1)
    assert "learning intention [learning_intention, core]: NONE" in scripted.prompts[1]          # nothing was known before the first reply
    answer(client, journey_id, R2)
    prompt = scripted.prompts[2]
    assert "learning intention [learning_intention, core]: SUFFICIENT" in prompt                  # now it is, from the learner's own words
    assert "learning approach [learning_approach, core]: NONE (grounded findings: 0, inferred: 0, groups asked about it: 1" in prompt
    assert "practical constraints [practical_constraints, supporting]" in prompt and "question(s) remain in the whole session" in prompt
    assert "Do not simply follow up on the last answer if a more important dimension is neglected" in prompt


def test_the_coverage_guard_unit_cases():
    cov = compute_coverage(DiscoveryLearnerState(intent=F("a")))
    assert coverage_guard([MENTAL_MODEL], coverage=cov, answered_groups=[], unprobed=[]) is None           # nothing answered yet
    assert coverage_guard([MENTAL_MODEL], coverage=cov, answered_groups=[g([LEARNING_INTENTION], True, 1)], unprobed=[]).startswith("the learning approach")
    assert coverage_guard([LEARNING_APPROACH], coverage=cov, answered_groups=[g([LEARNING_INTENTION], True, 1)], unprobed=[]) is None
    assert coverage_guard([], coverage=cov, answered_groups=[g([LEARNING_INTENTION], True, 1)], unprobed=[]) is None   # undeclared targets cannot be judged
    seen = [g([LEARNING_APPROACH], True, 1), g([CONFUSIONS], True, 2)]
    cov2 = compute_coverage(DiscoveryLearnerState(intent=F("a")), attempts_by_dimension(seen))
    assert "two groups in a row ignored" in coverage_guard([CONFUSIONS], coverage=cov2, answered_groups=seen, unprobed=[])
    assert coverage_guard([CONFUSIONS], coverage=cov2, answered_groups=seen, unprobed=["a misconception"]) is None  # investigating one is allowed
    assert coverage_guard([DESIRED_OUTCOME], coverage=cov2, answered_groups=seen, unprobed=[]) is None


# ---------------------------------------------------------------------------
# What reaches note design
# ---------------------------------------------------------------------------

def test_all_nine_dimensions_reach_the_profile_architecture_and_note_prompts(client, scripted):
    reply = ("I started learning CNNs because my team needs an image classifier. I want to build a working classifier for product photos. "
             "I learn best from diagrams and worked examples, and last time a picture of the sliding filter made it click. I'm happy to work through the maths. "
             "A filter slides over the image and multiplies local pixels by weights to detect edges. I already know gradient descent. I'd like to understand the mechanisms in detail. "
             "I'm not sure how the network learns the filter weights, and I'd love to know why pooling is needed. I can only use a laptop with no GPU.")
    state = {
        "intent": finding("Needs to build an image classifier for work", "stated", "my team needs an image classifier"),
        "desired_outcome": finding("Build a working product-photo classifier", "stated", "build a working classifier for product photos"),
        "explanation_preferences": [finding("Diagrams and worked examples", "stated", "I learn best from diagrams and worked examples")],
        "observed_approach": [finding("A picture of the sliding filter made it click", "demonstrated", "a picture of the sliding filter made it click")],
        "challenge_willingness": finding("Willing to work through maths", "stated", "happy to work through the maths"),
        "understanding": finding("Filters detect edges", "demonstrated", "A filter slides over the image and multiplies local pixels by weights to detect edges"),
        "related_familiarity": [finding("Gradient descent", "stated", "I already know gradient descent")],
        "desired_depth": finding("Detailed mechanisms", "stated", "understand the mechanisms in detail"),
        "gaps": [finding("How filter weights are learned", "stated", "not sure how the network learns the filter weights")],
        "questions_to_answer": [finding("Why pooling is needed", "stated", "why pooling is needed")],
        "constraints": [finding("Laptop without a GPU", "stated", "a laptop with no GPU")],
    }
    scripted.push(opening(motive=M(1), questions=["What prompted you to learn CNNs?"]), turn(state=state, ready=True), profile_json())
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    assert answer(client, journey_id, reply).json()["is_finished"] is True

    profile = client.post(f"/journeys/{journey_id}/knowledge-profile").json()
    ctx = profile["learner_context"]
    for key in ("intention", "desired_outcome", "understanding", "desired_depth", "challenge_willingness"):
        assert ctx[key]["basis"] in ("stated", "demonstrated") and ctx[key]["source_card"] == 1
    for key in ("explanation_preferences", "observed_approach", "related_familiarity", "gaps", "questions_to_answer", "constraints"):
        assert len(ctx[key]) == 1 and ctx[key][0]["source_card"] == 1
    assert set(ctx["discovery"]["coverage"]) == set(DIMENSIONS)
    assert "Sub-question" not in scripted.prompts[-1] and "reply to the whole group" in scripted.prompts[-1]    # the profile reads groups, not cards

    arch = client.post(f"/journeys/{journey_id}/architecture", json={}).json()
    assert arch["learning_goal"] == "Build a working product-photo classifier"
    arch_prompt = scripted.prompts[-1]
    for line in ("Desired outcome: Build a working product-photo classifier [stated]",
                 "Explanation preferences: Diagrams and worked examples [stated]",
                 "Observed response to explanation approaches: A picture of the sliding filter made it click [demonstrated]",
                 "Willingness to engage with challenging material: Willing to work through maths [stated]",
                 "Desired depth: Detailed mechanisms [stated]",
                 "Questions the learner wants answered (address them): Why pooling is needed [stated]",
                 "Practical constraints: Laptop without a GPU [stated]"):
        assert line in arch_prompt, line
    assert "What prompted you to learn CNNs?" not in arch_prompt                     # raw questions are not a substitute for the profile
    before = scripted.calls
    assert client.post(f"/journeys/{journey_id}/generate-note").status_code == 200
    assert any("Why pooling is needed [stated]" in p and "What prompted you" not in p for p in scripted.prompts[before:])
