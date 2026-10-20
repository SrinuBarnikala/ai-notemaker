"""Question groups: a motive plus zero to five peer questions, one combined reply, and an individual-question budget."""
import json

import pytest

from backend.app.discovery.groups import (
    MAX_QUESTIONS_PER_GROUP,
    MAX_ZERO_QUESTION_GROUPS,
    dump_questions,
    fallback_group,
    group_text,
    motive_problem,
    normalize_interaction,
    question_problem,
    sanitize_question,
    validate_group,
)
from backend.app.discovery.parser import DiscoveryParseError, parse_group, parse_judge, parse_turn
from backend.app.db.session import SessionLocal
from backend.app.models.discovery import DiscoveryInteraction
from discovery_helpers import distinct_group_model, group, judge, opening, turn

TOPIC = "How do convolutional neural networks work?"
MOTIVE = "I'd like to understand what you want to achieve with CNNs, so the notes can aim at it."
QS = [
    "What prompted you to want to learn CNNs right now?",
    "What would you eventually like to understand or build with them?",
    "Is there a particular problem or concept that made you curious about them?",
]
REPLY = "I'm curious because my team does image work. I'd like to build a classifier, and filters sliding across an image confuse me."


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


def analysis_of(journey_id, index):
    return json.loads([r for r in rows(journey_id) if r.question_index == index][0].analysis)


def validate(raw, *, asked=(), motives=(), remaining=10, zero_allowed=False):
    return validate_group(raw, asked_questions=list(asked), earlier_motives=list(motives), remaining_units=remaining, zero_allowed=zero_allowed)


# ---------------------------------------------------------------------------
# The structure: motive + zero to five peer questions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 3, 5])
def test_a_motive_with_one_to_five_peer_questions_is_valid(n):
    questions = [
        "What prompted you to learn this topic right now?",
        "What would you like to understand or build with it?",
        "Which problem made you curious about it in the first place?",
        "Who else on your team would use what you learn here?",
        "How soon do you hope to apply any of this?",
    ][:n]
    result = validate(group(MOTIVE, questions))
    assert result.problems == [] and result.group.questions == questions


def test_a_motive_with_zero_questions_is_valid_only_when_allowed():
    assert validate(group(MOTIVE, []), zero_allowed=True).group.questions == []
    refused = validate(group(MOTIVE, []), zero_allowed=False)
    assert refused.group is None and refused.problems == ["a group without questions is not allowed now"]


def test_more_than_five_questions_are_rejected_not_trimmed():
    six = [f"What do you think about the {w} part of how this works?" for w in ("first", "second", "third", "fourth", "fifth", "sixth")]
    result = validate(group(MOTIVE, six))
    assert result.group is None and result.problems == [f"more than {MAX_QUESTIONS_PER_GROUP} questions"]


def test_there_is_no_main_question_and_no_subquestion_in_the_model():
    result = validate({"motive": MOTIVE, "main_question": "What?", "subquestions": ["Why?"], "questions": QS[:2]})
    assert result.group.questions == QS[:2]
    assert not hasattr(result.group, "main_question") and not hasattr(result.group, "subquestions")


@pytest.mark.parametrize("motive,expected", [
    ("What do you want to achieve with CNNs?", "the motive must be a statement, not a question"),
    ("", "the motive is missing or too short"),
    ("Too short", "the motive is missing or too short"),
    ("I'd like to understand " + "very " * 80 + "much about this.", "the motive is too long to be a short statement"),
])
def test_a_motive_is_a_short_statement(motive, expected):
    assert expected in validate(group(motive, QS[:1])).problems


def test_a_repeated_motive_is_rejected_by_meaning_not_just_exact_text():
    reworded = "I'd like to understand what you want to achieve with CNNs so that the notes can aim at it."
    assert motive_problem(reworded, [MOTIVE]) == "the motive repeats an earlier motive"
    assert motive_problem("I'd like to hear how you currently picture a convolution filter working.", [MOTIVE]) is None


def test_numbering_and_bullets_are_stripped_because_questions_are_unnumbered_peers():
    raw = group(MOTIVE, ["1. What prompted you to learn CNNs right now?", "- What would you like to build with them?", "(3) Which problem made you curious?"])
    questions = validate(raw).group.questions
    assert questions == ["What prompted you to learn CNNs right now?", "What would you like to build with them?", "Which problem made you curious?"]
    assert sanitize_question("2) Why?") == "Why?"


@pytest.mark.parametrize("bad,why", [
    (42, "a question was not text"),
    ("Why?", "dropped a question: it is empty or too short"),
    ("What drew you in? And why now?", "dropped a question: it asks more than one question"),
    ("Tell me about your background with images in detail", "dropped a question: it is not phrased as a question"),
    ("Why " + "really " * 60 + "does this matter to you personally?", "dropped a question: it is too long to be a single conversational question"),
])
def test_unusable_questions_are_dropped_individually_with_a_note(bad, why):
    result = validate(group(MOTIVE, [QS[0], bad, QS[1]]))
    assert result.group.questions == [QS[0], QS[1]] and why in result.notes


def test_repeated_and_overlapping_questions_are_dropped():
    result = validate(group(MOTIVE, [QS[0], "What prompted you to want to learn CNNs right now, then?", QS[1]]), asked=[QS[2]])
    assert result.group.questions == [QS[0], QS[1]]
    assert "dropped a question that repeats another question in the group" in result.notes

    again = validate(group(MOTIVE, [QS[2], QS[1]]), asked=[QS[2]])
    assert again.group.questions == [QS[1]] and "dropped a question: it repeats an earlier question" in again.notes


def test_a_group_whose_questions_are_all_unusable_is_a_problem_not_a_silent_empty_group():
    result = validate(group(MOTIVE, ["Why?", "How?"]), zero_allowed=True)
    assert result.group is None and result.problems == ["no usable questions remained"]


def test_a_group_is_trimmed_to_the_remaining_budget_never_beyond():
    result = validate(group(MOTIVE, QS), remaining=2)
    assert result.group.questions == QS[:2] and any("trimmed to the 2 question(s)" in n for n in result.notes)
    assert validate(group(MOTIVE, QS), remaining=0, zero_allowed=False).group is None


@pytest.mark.parametrize("raw,problem", [
    (None, "the group is missing or not an object"),
    ("text", "the group is missing or not an object"),
    ({"motive": MOTIVE}, "the questions list is missing"),
    ({"motive": MOTIVE, "questions": "What is it?"}, "questions must be a list"),
])
def test_malformed_groups_are_problems(raw, problem):
    assert problem in validate(raw).problems


def test_targets_are_limited_to_known_dimensions():
    result = validate({**group(MOTIVE, QS[:1]), "targets": ["learning_approach", "nonsense", "learning_approach", "desired_depth", "desired_outcome", "learning_intention"]})
    assert result.group.targets == ["learning_approach", "desired_depth", "desired_outcome"]


def test_question_problem_still_requires_one_question_and_works_in_any_script():
    assert question_problem("What is a filter?", []) is None
    assert question_problem("ما هذا؟ ولماذا؟", []) == "it asks more than one question"
    telugu = "ఈ అంశాన్ని మీరు ఎందుకు నేర్చుకోవాలనుకుంటున్నారు?"
    assert question_problem(telugu, [telugu]) == "it repeats an earlier question"


# ---------------------------------------------------------------------------
# Parsing model output
# ---------------------------------------------------------------------------

def test_parse_group_reads_a_group_at_top_level_or_nested():
    flat = parse_group(opening(motive=MOTIVE, questions=QS)).group
    nested = parse_group(json.dumps({"group": group(MOTIVE, QS)})).group
    assert flat["questions"] == nested["questions"] == QS
    for bad in ("not json", json.dumps({"questions": QS}), json.dumps(["x"])):
        with pytest.raises(DiscoveryParseError):
            parse_group(bad)


def test_parse_turn_needs_a_group_unless_finishing():
    assert parse_turn(turn(ready=True), TOPIC).group is None
    with pytest.raises(DiscoveryParseError):
        parse_turn(turn(group_override=None), TOPIC)
    with pytest.raises(DiscoveryParseError):
        parse_turn(json.dumps({"ready_to_finish": False, "group": group(MOTIVE, QS)}), TOPIC)  # no state


def test_parse_judge_reads_the_review_and_rejects_empty_replies():
    verdict = parse_judge(judge(irrelevant=[1], overlapping=[[0, 2]], revisits=[3], motive_matches=False, purpose_served=False))
    assert (verdict.irrelevant, verdict.overlapping, verdict.revisits_known) == ([1], [(0, 2)], [3])
    assert verdict.motive_matches is False and verdict.purpose_served is False
    with pytest.raises(DiscoveryParseError):
        parse_judge(json.dumps({"hello": "world"}))


# ---------------------------------------------------------------------------
# Presenting groups through the API
# ---------------------------------------------------------------------------

def test_a_group_is_stored_returned_and_resumed_as_a_motive_with_peer_questions(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS, targets=["learning_intention", "desired_outcome"]))
    journey_id = new_journey(client)
    shown = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert shown["motive"] == MOTIVE and shown["questions"] == QS
    assert shown["targets"] == ["learning_intention", "desired_outcome"] and shown["legacy"] is False
    assert shown["question_text"] == group_text(MOTIVE, QS)                    # readable flattened form for older clients
    assert shown["questions_asked"] == 3 and shown["questions_remaining"] == 7 and shown["max_questions"] == 10
    assert shown["total_questions_answered"] == 0

    again = client.post(f"/journeys/{journey_id}/discovery/start").json()       # resume: same group, no model call
    assert again["motive"] == MOTIVE and again["questions"] == QS and scripted.calls == 1

    row = rows(journey_id)[0]
    assert row.motive == MOTIVE and json.loads(row.questions) == QS
    assert row.question_text == group_text(MOTIVE, QS) and row.subquestions is None
    meta = json.loads(row.analysis)["group"]
    assert meta["targets"] == ["learning_intention", "desired_outcome"] and meta["semantic_check"] == "passed"
    history = client.get(f"/journeys/{journey_id}/discovery").json()
    item = history["interactions"][0]
    assert item["motive"] == MOTIVE and item["questions"] == QS and item["legacy"] is False
    assert history["questions_asked"] == 3 and history["max_questions"] == 10


def test_a_motive_with_zero_questions_is_never_allowed_as_the_opening_group(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=[]), opening(motive=MOTIVE.replace("achieve", "accomplish") + " Truly.", questions=QS[:1]))
    shown = client.post(f"/journeys/{new_journey(client)}/discovery/start").json()
    assert shown["questions"] == QS[:1]                       # the zero-question opening was refused and regenerated


def test_the_learner_answers_the_whole_group_in_one_free_form_message(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), turn(question="Which part of a filter confuses you most?"))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    # the reply is not required to follow the questions: it is stored whole and given to the model whole
    reply = "  Because my team uses them.\n\nNo idea about the rest, honestly, but filters confuse me — తెలుగు ok?  "
    res = answer(client, journey_id, reply)
    assert res.status_code == 200
    assert rows(journey_id)[0].learner_answer == reply.strip()
    assert reply.strip() in scripted.prompts[1] and "reply to the whole group" in scripted.prompts[1]
    assert MOTIVE in scripted.prompts[1] and all(q in scripted.prompts[1] for q in QS)


def test_empty_and_oversized_replies_are_rejected_before_anything_is_saved(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    for bad in ("", "   ", "\n\t "):
        assert answer(client, journey_id, bad).status_code == 422
    assert answer(client, journey_id, "x" * 5001).status_code == 422
    assert rows(journey_id)[0].learner_answer is None


# ---------------------------------------------------------------------------
# Semantic review (the model judges meaning; code enforces the rest)
# ---------------------------------------------------------------------------

def test_the_review_drops_irrelevant_overlapping_and_already_known_questions(client, scripted):
    questions = QS + ["Which GPU would you train a model on?", "What drew you toward CNNs in particular today?"]
    scripted.push(opening(motive=MOTIVE, questions=questions, targets=["learning_intention"]))
    scripted.push_judge(judge(irrelevant=[3], overlapping=[[0, 4]], revisits=[2]))
    shown = client.post(f"/journeys/{new_journey(client)}/discovery/start").json()
    # dropped: the GPU question (irrelevant), position 4 (the later of an overlapping pair) and position 2 (already known)
    assert shown["questions"] == [QS[0], QS[1]]
    assert shown["questions_asked"] == 2                       # only what is actually shown is charged to the budget
    assert "Which GPU" in scripted.judge_prompts[0] and "zero-based" in scripted.judge_prompts[0]


def test_the_review_is_told_what_is_already_known_and_what_was_asked(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS[:2], targets=["learning_intention"]))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    scripted.push(turn(motive="I'd like to hear how you picture a filter moving across an image.", questions=["How would you describe what a filter does to an image?"], targets=["current_mental_model"]))
    answer(client, journey_id, REPLY)
    review = scripted.judge_prompts[-1]
    assert QS[0] in review and QS[1] in review                 # earlier questions are shown so repeats can be caught
    assert "What is already known about the learner" in review


@pytest.mark.parametrize("verdict", [judge(motive_matches=False), judge(purpose_served=False), judge(irrelevant=[0, 1, 2])])
def test_a_group_the_review_rejects_is_regenerated_once_and_never_shown(client, scripted, verdict):
    scripted.push(opening(motive=MOTIVE, questions=QS), opening(motive="I'd like to see how you picture images being processed, step by step.", questions=["How do you picture a picture being processed by a network?"]))
    scripted.push_judge(verdict, judge())
    shown = client.post(f"/journeys/{new_journey(client)}/discovery/start").json()
    assert shown["questions"] == ["How do you picture a picture being processed by a network?"]
    assert shown["fallback_used"] is False
    assert scripted.calls == 2 and scripted.judge_calls == 2   # one generation, one regeneration, one review of each
    assert "the questions" in scripted.prompts[1] or "motive" in scripted.prompts[1]


def test_when_the_regeneration_is_also_rejected_a_generic_fallback_group_is_shown(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), opening(motive="I'd like to see how images flow through a network.", questions=["How does an image flow through a network?"]))
    scripted.push_judge(judge(purpose_served=False), judge(purpose_served=False))
    journey_id = new_journey(client)
    shown = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert shown["fallback_used"] is True and shown["motive"] and not shown["motive"].endswith("?")
    assert TOPIC.rstrip("?") in shown["question_text"]         # generic, but still about the learner's topic
    assert analysis_of(journey_id, 1)["question_source"] == "fallback"
    assert scripted.calls == 2 and scripted.judge_calls == 2   # bounded: no third attempt


def test_if_the_review_itself_cannot_be_read_the_group_is_shown_and_flagged_unchecked(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS))
    scripted.push_judge("garbage", "still garbage")
    journey_id = new_journey(client)
    shown = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert shown["questions"] == QS and shown["fallback_used"] is False
    assert analysis_of(journey_id, 1)["group"]["semantic_check"] == "unavailable"
    assert scripted.judge_calls == 2                           # one review attempt plus exactly one repair


def test_no_review_is_wasted_on_groups_with_nothing_to_judge(client, scripted):
    journey_id = new_journey(client)                           # the default scripted model returns garbage: generic fallback
    client.post(f"/journeys/{journey_id}/discovery/start")
    assert scripted.judge_calls == 0                           # a trusted generic group is not reviewed


def test_an_invalid_group_from_the_model_is_never_shown(client, scripted):
    scripted.push(
        opening(motive="Why do you want to learn CNNs at all?", questions=QS),     # the motive is a question
        opening(motive=MOTIVE, questions=["x?"]),                                     # its only question is unusable
    )
    shown = client.post(f"/journeys/{new_journey(client)}/discovery/start").json()
    assert shown["fallback_used"] is True and not shown["motive"].endswith("?")
    assert "Why do you want to learn CNNs at all?" not in shown["question_text"]


def test_the_regeneration_is_told_exactly_what_was_wrong(client, scripted):
    scripted.push(opening(motive="Why do you want to learn CNNs?", questions=QS), opening(motive=MOTIVE, questions=QS[:1]))
    client.post(f"/journeys/{new_journey(client)}/discovery/start")
    assert "the motive must be a statement, not a question" in scripted.prompts[1]
    assert "Write ONE new question group" in scripted.prompts[1]


# ---------------------------------------------------------------------------
# Zero-question groups cannot loop forever
# ---------------------------------------------------------------------------

def _two_groups_in(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS[:1]))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    return journey_id


def test_a_zero_question_group_is_allowed_after_a_first_group_and_costs_nothing(client, scripted):
    journey_id = _two_groups_in(client, scripted)
    scripted.push(turn(motive="Tell me anything else that comes to mind about why you are learning this.", questions=[]))
    res = answer(client, journey_id, REPLY).json()
    assert res["questions"] == [] and res["motive"] and res["is_finished"] is False
    assert res["questions_asked"] == 1 and res["questions_remaining"] == 9      # no question units were spent
    assert "no specific questions" not in json.dumps(res).lower()                # (the UI supplies its own invitation line)
    assert analysis_of(journey_id, 2)["group"]["semantic_check"] == "skipped"


def test_two_zero_question_groups_in_a_row_are_refused(client, scripted):
    journey_id = _two_groups_in(client, scripted)
    scripted.push(turn(motive="Tell me anything else that comes to mind about why you are learning this.", questions=[]))
    answer(client, journey_id, REPLY)
    scripted.push(
        turn(motive="Share whatever else seems important to you about your reasons for learning CNNs.", questions=[]),   # refused: back to back
        opening(motive="I'd like to see how you picture a filter working on an image.", questions=["How would you explain what a filter does?"]),
    )
    res = answer(client, journey_id, "Nothing more, really.").json()
    assert res["questions"] == ["How would you explain what a filter does?"]


def test_zero_question_groups_are_rationed_even_when_not_consecutive(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS[:1]))
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    shown = []
    for i in range(1, 2 * MAX_ZERO_QUESTION_GROUPS + 3):
        zero = (i % 2 == 1)
        scripted.push(turn(motive=f"Note number {i}: tell me whatever comes to mind about aspect{i}x1 aspect{i}x2 aspect{i}x3 aspect{i}x4.", questions=[]) if zero
                      else turn(motive=f"Group {i} looks at aspect{i}x1 aspect{i}x2 aspect{i}x3 aspect{i}x4 in more detail.", questions=[f"What do you make of aspect{i}x1 and aspect{i}x2 so far?"]),
                      "garbage", "garbage")
        res = answer(client, journey_id, f"reply number {i}").json()
        shown.append(len(res["questions"]))
        if res["is_finished"]:
            break
    assert shown.count(0) <= MAX_ZERO_QUESTION_GROUPS
    assert len(rows(journey_id)) <= 10 + MAX_ZERO_QUESTION_GROUPS         # groups are bounded even though motives are free


# ---------------------------------------------------------------------------
# The individual-question budget
# ---------------------------------------------------------------------------

def _drive(client, scripted, per_group, budget=None, test_settings=None, max_groups=40, targets=None):
    if budget is not None:
        test_settings.discovery_max_questions = budget
    scripted.default = distinct_group_model(questions_per_group=per_group, targets=targets)
    journey_id = new_journey(client)
    shown = [client.post(f"/journeys/{journey_id}/discovery/start").json()]
    for i in range(max_groups):
        res = answer(client, journey_id, f"My reply to group {i + 1}.").json()
        if res["is_finished"]:
            return journey_id, shown, res
        shown.append(res)
    raise AssertionError("discovery never finished")


def test_the_default_budget_is_ten_individual_questions_never_eleven(client, scripted):
    journey_id, shown, final = _drive(client, scripted, per_group=3)
    sizes = [len(g["questions"]) for g in shown]
    assert sizes == [3, 3, 3, 1] and sum(sizes) == 10          # the last group was trimmed to the one unit that was left
    assert final["questions_asked"] == 10 and final["questions_remaining"] == 0 and final["max_questions"] == 10
    assert final["total_questions_answered"] == 10
    stored = rows(journey_id)
    assert sum(len(json.loads(r.questions)) for r in stored) == 10 and all(r.learner_answer for r in stored)
    assert analysis_of(journey_id, 4)["stopped_reason"] == "safety_limit"
    assert answer(client, journey_id, "an eleventh?").status_code == 400


def test_motives_are_free_only_questions_cost_budget(client, scripted):
    _, shown, _ = _drive(client, scripted, per_group=1)
    assert len(shown) == 10 and all(len(g["questions"]) == 1 and g["motive"] for g in shown)   # ten motives, ten questions


def test_groups_never_exceed_the_remaining_budget(client, scripted):
    _, shown, _ = _drive(client, scripted, per_group=5)
    sizes = [len(g["questions"]) for g in shown]
    assert sizes == [5, 5] and all(g["questions_remaining"] >= 0 for g in shown)
    asked = 0
    for g in shown:
        asked += len(g["questions"])
        assert asked <= 10


@pytest.mark.parametrize("budget,per_group,expected", [(1, 5, [1]), (3, 2, [2, 1]), (4, 4, [4]), (7, 3, [3, 3, 1])])
def test_a_smaller_limit_is_honoured_exactly(client, scripted, test_settings, budget, per_group, expected):
    journey_id, shown, final = _drive(client, scripted, per_group, budget=budget, test_settings=test_settings)
    assert [len(g["questions"]) for g in shown] == expected
    assert final["questions_asked"] == budget and final["max_questions"] == budget
    assert sum(len(json.loads(r.questions)) for r in rows(journey_id)) == budget


def test_the_budget_is_not_spent_twice_when_a_step_fails_and_is_retried(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS))
    journey_id = new_journey(client)
    first = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert first["questions_asked"] == 3
    scripted.push(RuntimeError("down"), RuntimeError("down"), RuntimeError("down"))
    assert answer(client, journey_id, REPLY).status_code == 503
    assert client.get(f"/journeys/{journey_id}/discovery").json()["questions_asked"] == 3      # nothing extra was charged
    scripted.push(turn(motive="I'd like to hear how you picture a filter working on an image.", questions=["How would you describe what a filter does?"]))
    resumed = client.post(f"/journeys/{journey_id}/discovery/start").json()                   # the retry
    assert resumed["questions_asked"] == 4 and len(rows(journey_id)) == 2
    assert client.post(f"/journeys/{journey_id}/discovery/start").json()["questions_asked"] == 4   # and again: still 4


def test_a_regeneration_inside_one_step_charges_only_the_group_finally_shown(client, scripted):
    scripted.push(opening(motive=MOTIVE, questions=QS), opening(motive="I'd like to see how you picture an image being processed here.", questions=QS[:1]))
    scripted.push_judge(judge(purpose_served=False), judge())
    shown = client.post(f"/journeys/{new_journey(client)}/discovery/start").json()
    assert shown["questions_asked"] == 1 and scripted.calls == 2


def test_the_budget_survives_a_resume_because_it_is_derived_from_what_is_stored(client, scripted):
    scripted.default = distinct_group_model(questions_per_group=2)
    journey_id = new_journey(client)
    client.post(f"/journeys/{journey_id}/discovery/start")
    answer(client, journey_id, "first reply")
    # a "restart": nothing is held in memory between requests, so the answers below come only from the database
    state = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert state["questions_asked"] == 4 and state["questions_remaining"] == 6 and state["total_questions_answered"] == 2


def test_an_exhausted_generic_bank_ends_discovery_honestly_instead_of_repeating(client, scripted):
    journey_id = new_journey(client)                           # the default scripted model returns garbage for everything
    first = client.post(f"/journeys/{journey_id}/discovery/start").json()
    seen_questions = set(first["questions"])
    seen_motives = {first["motive"]}
    steps = 0
    for i in range(1, 15):
        res = answer(client, journey_id, f"answer {i}").json()
        steps += 1
        if res["is_finished"]:
            break
        assert res["fallback_used"] is True and res["questions_asked"] <= 10
        assert not (set(res["questions"]) & seen_questions) and res["motive"] not in seen_motives      # never a repeat
        seen_questions |= set(res["questions"])
        seen_motives.add(res["motive"])
    last = analysis_of(journey_id, steps)
    assert last["stopped_reason"] in ("safety_limit", "no_further_question")
    assert last["state"]["unresolved"], "what was never established must stay visible"
    assert last["state"]["intent"] is None and last["state"]["understanding"] is None            # nothing was fabricated


def test_fallback_groups_have_a_motive_coherent_questions_and_respect_the_budget():
    g = fallback_group(TOPIC, ["learning_approach", "desired_depth"], asked_questions=[], earlier_motives=[], remaining_units=1)
    assert g.targets == ["learning_approach"] and len(g.questions) == 1 and g.motive and not g.motive.endswith("?")
    assert fallback_group(TOPIC, ["learning_approach"], asked_questions=g.questions, earlier_motives=[g.motive], remaining_units=5) is None
    assert fallback_group(TOPIC, ["desired_depth"], asked_questions=[], earlier_motives=[], remaining_units=0) is None


# ---------------------------------------------------------------------------
# Older interactions stay readable
# ---------------------------------------------------------------------------

def test_legacy_single_questions_and_v2_cards_are_normalized_on_read_without_inventing_a_motive():
    single = normalize_interaction("Why did you choose CNNs?", None, None, None)
    assert single.legacy and single.motive is None and single.questions == ["Why did you choose CNNs?"] and single.units == 1
    card = normalize_interaction("What do you want to achieve?", json.dumps(["Why now?", "Where will you use it?"]), None, None)
    assert card.legacy and card.questions == ["What do you want to achieve?", "Why now?", "Where will you use it?"] and card.units == 3
    current = normalize_interaction(group_text(MOTIVE, QS[:1]), None, MOTIVE, dump_questions(QS[:1]))
    assert not current.legacy and current.motive == MOTIVE and current.questions == QS[:1]
    empty = normalize_interaction(MOTIVE, None, MOTIVE, dump_questions([]))
    assert not empty.legacy and empty.questions == [] and empty.units == 0


def test_legacy_sessions_resume_count_their_questions_and_continue(client, scripted):
    from backend.app.models.journey import LearningJourney
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Legacy topic", status="discovery")
        db.add(journey)
        db.commit()
        db.add_all([
            DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Old plain question?", concept_target="Old",
                                 learner_answer="Old answer", quick_assessment="Old note"),
            DiscoveryInteraction(journey_id=journey.id, question_index=2, question_text="Old card question?", concept_target="Old",
                                 subquestions=json.dumps(["Old subquestion one?", "Old subquestion two?"])),
        ])
        db.commit()
        journey_id = journey.id
    finally:
        db.close()

    pending = client.post(f"/journeys/{journey_id}/discovery/start").json()
    assert pending["legacy"] is True and pending["motive"] is None
    assert pending["questions"] == ["Old card question?", "Old subquestion one?", "Old subquestion two?"]
    assert pending["questions_asked"] == 4 and pending["total_questions_answered"] == 1      # 1 + 3 units, nothing rewritten
    history = client.get(f"/journeys/{journey_id}/discovery").json()
    assert [i["legacy"] for i in history["interactions"]] == [True, True] and history["questions_asked"] == 4

    scripted.push(turn(motive="I'd like to see how you picture the idea working.", questions=["How would you explain the idea in your own words?"]))
    res = answer(client, journey_id, "Old-style answer.")
    assert res.status_code == 200 and res.json()["legacy"] is False and res.json()["questions_asked"] == 5
    assert "Old answer" in scripted.prompts[0] and "an earlier question; no motive was recorded" in scripted.prompts[0]
