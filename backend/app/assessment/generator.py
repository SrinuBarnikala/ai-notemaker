import json
import logging
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.config import Settings
from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.schemas.assessment import (
    FlashcardItem,
    QuizQuestion,
    AssessmentResponse,
    QuizSubmissionRequest,
    QuestionResult,
    QuizSubmissionResult,
)
from backend.app.providers.factory import get_llm_provider
from backend.app.assessment.prompts import (
    ASSESSMENT_SYSTEM_PROMPT,
    ASSESSMENT_PROMPT_TEMPLATE,
)
from backend.app.note.parser import extract_json_array_or_object

logger = logging.getLogger(__name__)


def parse_assessment_json(
    raw_text: str,
    topic: str,
    concepts: List[str],
    llm_error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parses LLM generation output into flashcards and quiz questions,
    with a deterministic, topic-grounded fallback if generation or parsing fails.
    """
    data = extract_json_array_or_object(raw_text) if raw_text else None
    flashcards: List[FlashcardItem] = []
    quiz_questions: List[QuizQuestion] = []

    if isinstance(data, dict):
        raw_fc = data.get("flashcards", [])
        if isinstance(raw_fc, list):
            for i, it in enumerate(raw_fc):
                if isinstance(it, dict) and it.get("front") and it.get("back"):
                    flashcards.append(
                        FlashcardItem(
                            id=f"fc-{i+1}",
                            concept=str(it.get("concept") or topic),
                            front=str(it.get("front")),
                            back=str(it.get("back")),
                            difficulty=it.get("difficulty") if it.get("difficulty") in ["easy", "medium", "hard"] else "medium",
                        )
                    )

        raw_quiz = data.get("quiz_questions", [])
        if isinstance(raw_quiz, list):
            for i, q in enumerate(raw_quiz):
                if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list) and len(q.get("options")) >= 2:
                    quiz_questions.append(
                        QuizQuestion(
                            id=f"q-{i+1}",
                            concept=str(q.get("concept") or topic),
                            question=str(q.get("question")),
                            options=[str(opt) for opt in q.get("options")],
                            correct_index=int(q.get("correct_index", 0)) if 0 <= int(q.get("correct_index", 0)) < len(q.get("options")) else 0,
                            explanation=str(q.get("explanation") or "Correct understanding verified."),
                        )
                    )

    # Determine why we're about to fall back, for observability.
    failure_reason: Optional[str] = None
    if not flashcards or not quiz_questions:
        if llm_error:
            failure_reason = f"LLM generation call failed: {llm_error}"
        elif data is None:
            failure_reason = "LLM output was empty or not parseable as JSON"
        elif not flashcards and not quiz_questions:
            failure_reason = "LLM output did not contain any valid flashcards or quiz questions"
        elif not flashcards:
            failure_reason = "LLM output did not contain any valid flashcards"
        else:
            failure_reason = "LLM output did not contain any valid quiz questions"

    # Deterministic, topic-grounded fallback if the model output was missing/corrupt.
    # Intentionally avoids inventing domain-specific "facts" (e.g. distributed-systems
    # jargon) that would be wrong for whatever the actual topic is - it stays generic
    # about *how to study the topic* rather than pretending to teach unrelated content.
    used_fallback = False
    if not flashcards:
        used_fallback = True
        primary = concepts[0] if concepts else topic
        secondary = concepts[1] if len(concepts) > 1 else f"{topic} fundamentals"
        flashcards = [
            FlashcardItem(
                id="fc-1",
                concept=primary,
                front=f"What is the core idea behind {primary} in the context of {topic}?",
                back=f"{primary} is a specific concept within {topic}; understanding its structure and role is key to reasoning about {topic} correctly.",
                difficulty="medium",
            ),
            FlashcardItem(
                id="fc-2",
                concept=secondary,
                front=f"What distinguishes {secondary} from other closely related ideas in {topic}?",
                back=f"{secondary} has boundaries and behavior that are easy to conflate with adjacent concepts in {topic} without deliberate comparison.",
                difficulty="medium",
            ),
            FlashcardItem(
                id="fc-3",
                concept=topic,
                front=f"What is a common misconception learners have when first approaching {topic}?",
                back=f"Learners often oversimplify {topic}, missing the specific mechanics or trade-offs that only become clear with deeper study.",
                difficulty="hard",
            ),
        ]

    if not quiz_questions:
        used_fallback = True
        primary = concepts[0] if concepts else topic
        quiz_questions = [
            QuizQuestion(
                id="q-1",
                concept=primary,
                question=f"Which statement best reflects how {primary} actually behaves within {topic}?",
                options=[
                    f"{primary} follows specific, well-defined mechanics that can be reasoned about precisely",
                    f"{primary} behaves randomly with no consistent rules",
                    f"{primary} has no relationship to the rest of {topic}",
                    f"{primary} cannot be understood without unrelated background",
                ],
                correct_index=0,
                explanation=f"Option A is correct: {primary}, like any well-defined technical concept in {topic}, follows specific mechanics that can be studied and reasoned about. Options B, C, and D describe traits that would make {primary} impossible to teach or apply, which contradicts it being a core part of {topic}.",
            ),
            QuizQuestion(
                id="q-2",
                concept=primary,
                question=f"When distinguishing {primary} from related ideas in {topic}, what is the most reliable approach?",
                options=[
                    f"Compare their defining characteristics and how each is actually used within {topic}",
                    "Assume they are interchangeable since they sound similar",
                    "Ignore the differences since terminology doesn't matter in practice",
                    "Rely only on the order they were introduced in the material",
                ],
                correct_index=0,
                explanation=f"Option A is correct: distinguishing concepts within {topic} requires comparing their actual defining characteristics and usage, not surface-level similarity. Options B, C, and D skip the comparison entirely and would lead to genuine misunderstandings about {topic}.",
            ),
            QuizQuestion(
                id="q-3",
                concept=topic,
                question=f"What is the best way to solidify understanding of {topic} after an initial pass through the material?",
                options=[
                    f"Apply {topic}'s concepts to a concrete example or problem and check that the reasoning holds",
                    "Memorize definitions without testing them against examples",
                    "Assume understanding is complete after a single read-through",
                    "Avoid revisiting any concept once it has been introduced",
                ],
                correct_index=0,
                explanation="Option A is correct: applying concepts to a concrete example and checking whether the reasoning holds is what converts passive exposure into durable understanding for any technical topic, including this one. Options B, C, and D all skip active practice, which is the step most likely to reveal gaps.",
            ),
        ]

    return {
        "flashcards": flashcards,
        "quiz_questions": quiz_questions,
        "used_fallback": used_fallback,
        "failure_reason": failure_reason,
    }


async def generate_assessment_for_journey(
    journey_id: str,
    db: Session,
    settings: Settings,
) -> AssessmentResponse:
    """
    Generates and persists personalized active recall flashcards and quiz questions.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning journey '{journey_id}' not found.",
        )

    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate assessment before generating a living note. Complete Phase 5 first.",
        )

    sections = (
        db.query(NoteSection)
        .filter(NoteSection.note_id == note.id)
        .order_by(NoteSection.order_index.asc())
        .all()
    )
    sections_summary = "\n".join([f"- {s.title} ({s.section_type})" for s in sections])

    profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()
    concepts_list = []
    gaps_and_misconceptions = "None identified"
    if profile:
        concepts = db.query(KnowledgeConcept).filter(KnowledgeConcept.profile_id == profile.id).all()
        concepts_list = [c.name for c in concepts]
        misc = json.loads(profile.misconceptions or "[]")
        gaps = json.loads(profile.gaps or "[]")
        gaps_and_misconceptions = f"Gaps: {gaps}, Misconceptions: {misc}"

    provider = get_llm_provider(settings)
    prompt = ASSESSMENT_PROMPT_TEMPLATE.format(
        topic=journey.topic,
        note_summary=note.summary,
        sections_summary=sections_summary,
        concepts_list=concepts_list,
        gaps_and_misconceptions=gaps_and_misconceptions,
    )

    llm_error: Optional[str] = None
    try:
        raw_output = await provider.generate(
            prompt=prompt,
            system_prompt=ASSESSMENT_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except Exception as err:
        logger.error("Assessment generation failed: %s", err)
        raw_output = ""
        llm_error = str(err)

    parsed = parse_assessment_json(raw_output, journey.topic, concepts_list, llm_error=llm_error)
    flashcards = parsed["flashcards"]
    quiz_questions = parsed["quiz_questions"]
    if parsed.get("used_fallback"):
        logger.warning(
            "Assessment for journey '%s' used deterministic fallback content (reason: %s)",
            journey_id, parsed.get("failure_reason"),
        )

    assessment = db.query(Assessment).filter(Assessment.journey_id == journey_id).first()
    if not assessment:
        assessment = Assessment(
            journey_id=journey_id,
            note_id=note.id,
            flashcards=json.dumps([f.model_dump() for f in flashcards]),
            quiz_questions=json.dumps([q.model_dump() for q in quiz_questions]),
        )
        db.add(assessment)
    else:
        assessment.flashcards = json.dumps([f.model_dump() for f in flashcards])
        assessment.quiz_questions = json.dumps([q.model_dump() for q in quiz_questions])

    db.commit()
    db.refresh(assessment)

    return AssessmentResponse(
        id=assessment.id,
        journey_id=journey_id,
        note_id=note.id,
        flashcards=flashcards,
        quiz_questions=quiz_questions,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


def evaluate_quiz_submission(
    journey_id: str,
    request: QuizSubmissionRequest,
    db: Session,
) -> QuizSubmissionResult:
    """
    Evaluates submitted quiz answers, records score, and promotes mastered concepts
    in the learner's KnowledgeProfile.
    """
    assessment = db.query(Assessment).filter(Assessment.journey_id == journey_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment for journey '{journey_id}' not found. Generate it first.",
        )

    questions_raw = json.loads(assessment.quiz_questions or "[]")
    questions = [QuizQuestion(**q) for q in questions_raw]

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assessment has no quiz questions.",
        )

    score = 0
    total = len(questions)
    breakdown: List[QuestionResult] = []
    correct_concepts = []

    for q in questions:
        chosen = request.answers.get(q.id, -1)
        is_correct = (chosen == q.correct_index)
        if is_correct:
            score += 1
            correct_concepts.append(q.concept)

        selected_text = q.options[chosen] if 0 <= chosen < len(q.options) else None
        correct_text = q.options[q.correct_index] if 0 <= q.correct_index < len(q.options) else None

        breakdown.append(
            QuestionResult(
                question_id=q.id,
                concept=q.concept,
                selected_index=chosen,
                correct_index=q.correct_index,
                is_correct=is_correct,
                explanation=q.explanation,
                selected_text=selected_text,
                correct_text=correct_text,
            )
        )

    percentage = round((score / total) * 100, 1)

    # Update KnowledgeProfile Progression
    profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()
    updated_confidence = "intermediate"
    newly_mastered: List[str] = []

    if profile:
        profile_concepts = (
            db.query(KnowledgeConcept).filter(KnowledgeConcept.profile_id == profile.id).all()
        )
        for c in profile_concepts:
            if c.name in correct_concepts or any(c.name.lower() in cc.lower() for cc in correct_concepts):
                if c.category in ["unknown", "partially_known"]:
                    c.category = "known"
                    c.level = "strong"
                    newly_mastered.append(c.name)

        if percentage >= 80:
            profile.overall_confidence = "advanced"
        elif percentage >= 50:
            profile.overall_confidence = "intermediate"
        else:
            profile.overall_confidence = "developing"
        updated_confidence = profile.overall_confidence

    # Persist Submission
    submission = AssessmentSubmission(
        assessment_id=assessment.id,
        score=score,
        total=total,
        answers=json.dumps(request.answers),
        mastered_concepts=json.dumps(newly_mastered),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    msg = f"Completed assessment: {score}/{total} ({percentage}%). "
    if newly_mastered:
        msg += f"Promoted {len(newly_mastered)} concepts to mastered in your profile!"
    else:
        msg += "Great effort! Review the flashcards to strengthen remaining gaps."

    return QuizSubmissionResult(
        submission_id=submission.id,
        score=score,
        total=total,
        percentage=percentage,
        breakdown=breakdown,
        mastered_concepts=newly_mastered,
        updated_confidence=updated_confidence,
        message=msg,
    )
