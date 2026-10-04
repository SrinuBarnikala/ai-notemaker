"""
Non-persistent in-memory PersonalizationContext data models.
These models represent the unified composition of:
1. UserProfile defaults (experience level, preferred language, explanation depth, learning style)
2. Topic & Journey targets
3. Topic-specific mental model & concept mastery (KnowledgeProfile, KnowledgeConcept)
4. Empirical verification (AssessmentSubmission)
5. Cross-journey prior memory (MemoryService)

CRITICAL ARCHITECTURAL INVARIANT:
This is an in-memory composition layer, NOT a database table.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class LearnerProfileContext(BaseModel):
    """
    Baseline pedagogical preferences from UserProfile or safe defaults.
    """
    experience_level: str = Field(
        default="intermediate",
        description="Learner experience level: beginner, intermediate, advanced, staff",
    )
    preferred_language: str = Field(
        default="python",
        description="Primary programming language for code blocks and examples",
    )
    secondary_languages: List[str] = Field(
        default_factory=list,
        description="Secondary programming languages of interest",
    )
    explanation_depth: str = Field(
        default="standard",
        description="Pedagogical depth: intuitive, standard, internals, theoretical",
    )
    learning_style: str = Field(
        default="code_and_visual",
        description="Learning style preference: code_and_visual, practical, theory_first",
    )
    target_goals: Optional[str] = Field(
        default=None,
        description="Explicit learning aspirations or qualitative goals",
    )


class TopicKnowledgeContext(BaseModel):
    """
    Topic-specific mental model synthesized from discovery probing & knowledge concepts.
    """
    overall_confidence: str = Field(
        default="unknown",
        description="Overall confidence level: beginner, intermediate, advanced, mixed, unknown",
    )
    mental_model_summary: str = Field(
        default="",
        description="Holistic summary of the learner's mental model for this topic",
    )
    known_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts already understood; avoid basic re-explanation",
    )
    partially_known_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts with partial understanding",
    )
    active_gaps: List[str] = Field(
        default_factory=list,
        description="Active knowledge gaps requiring deep-dive explanations",
    )
    misconceptions: List[str] = Field(
        default_factory=list,
        description="Explicit misconceptions to correct or warn against",
    )


class EmpiricalMasteryContext(BaseModel):
    """
    Empirically verified mastery results from quizzes/assessments.
    """
    verified_mastered_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts verified through assessment submissions",
    )
    latest_quiz_score: Optional[str] = Field(
        default=None,
        description="Score on latest quiz attempt (e.g. '4/5')",
    )
    total_submissions: int = Field(
        default=0,
        description="Total quiz attempts submitted",
    )


class CrossJourneyPriorContext(BaseModel):
    """
    Relevant prior concepts and bridge opportunities from earlier learning journeys.
    """
    prior_related_concepts: List[str] = Field(
        default_factory=list,
        description="Prior mastered concepts from other journeys of this user",
    )
    total_prior_journeys: int = Field(
        default=0,
        description="Number of past journeys completed/started by this user",
    )


class PersonalizationContext(BaseModel):
    """
    Transient, in-memory composition object representing the unified learner state
    for AI generation agents (Architecture, Note, Copilot, Code Planner).
    NOT a database table.
    """
    # 1. Target Anchor
    journey_id: str = Field(..., description="Unique journey identifier")
    topic: str = Field(..., description="Topic of the current learning journey")
    journey_status: str = Field(default="created", description="Lifecycle status of journey")
    user_id: Optional[str] = Field(default=None, description="Owning user ID if authenticated")

    # 2. Components
    learner_profile: LearnerProfileContext = Field(default_factory=LearnerProfileContext)
    topic_knowledge: TopicKnowledgeContext = Field(default_factory=TopicKnowledgeContext)
    empirical_mastery: EmpiricalMasteryContext = Field(default_factory=EmpiricalMasteryContext)
    cross_journey: CrossJourneyPriorContext = Field(default_factory=CrossJourneyPriorContext)

    # Convenience accessors / flattening properties:
    @property
    def experience_level(self) -> str:
        return self.learner_profile.experience_level

    @property
    def preferred_language(self) -> str:
        return self.learner_profile.preferred_language

    @property
    def secondary_languages(self) -> List[str]:
        return self.learner_profile.secondary_languages

    @property
    def explanation_depth(self) -> str:
        return self.learner_profile.explanation_depth

    @property
    def learning_style(self) -> str:
        return self.learner_profile.learning_style

    @property
    def target_goals(self) -> Optional[str]:
        return self.learner_profile.target_goals

    @property
    def overall_confidence(self) -> str:
        return self.topic_knowledge.overall_confidence

    @property
    def mental_model_summary(self) -> str:
        return self.topic_knowledge.mental_model_summary

    @property
    def known_concepts(self) -> List[str]:
        return self.topic_knowledge.known_concepts

    @property
    def partially_known_concepts(self) -> List[str]:
        return self.topic_knowledge.partially_known_concepts

    @property
    def active_gaps(self) -> List[str]:
        return self.topic_knowledge.active_gaps

    @property
    def misconceptions(self) -> List[str]:
        return self.topic_knowledge.misconceptions

    @property
    def verified_mastered_concepts(self) -> List[str]:
        return self.empirical_mastery.verified_mastered_concepts

    @property
    def latest_quiz_score(self) -> Optional[str]:
        return self.empirical_mastery.latest_quiz_score

    @property
    def prior_related_concepts(self) -> List[str]:
        return self.cross_journey.prior_related_concepts

    @property
    def total_prior_journeys(self) -> int:
        return self.cross_journey.total_prior_journeys

    def format_for_prompt(self) -> str:
        """
        Synthesizes a standardized, human-readable prompt section for AI agents.
        """
        lines = [
            "=== PERSONALIZED LEARNER CONTEXT ===",
            f"Topic: {self.topic}",
            f"Learner Experience Level: {self.experience_level.capitalize()}",
            f"Preferred Programming Language: {self.preferred_language}",
            f"Explanation Depth: {self.explanation_depth}",
            f"Learning Style: {self.learning_style}",
        ]
        if self.target_goals:
            lines.append(f"Learner Goal: {self.target_goals}")

        if self.overall_confidence and self.overall_confidence != "unknown":
            lines.append(f"Topic Confidence: {self.overall_confidence}")

        if self.mental_model_summary:
            lines.append(f"Mental Model Assessment: {self.mental_model_summary}")

        if self.known_concepts:
            lines.append(f"Known Concepts (Do not re-explain basic definitions): {', '.join(self.known_concepts)}")

        if self.active_gaps:
            lines.append(f"Active Knowledge Gaps (Focus deep-dives and clear explanations here): {', '.join(self.active_gaps)}")

        if self.misconceptions:
            lines.append(f"Identified Misconceptions (Debunk or warn against): {', '.join(self.misconceptions)}")

        if self.verified_mastered_concepts:
            lines.append(f"Empirically Verified Mastery (From quizzes): {', '.join(self.verified_mastered_concepts)}")

        if self.prior_related_concepts:
            lines.append(f"Cross-Journey Prior Knowledge: {', '.join(self.prior_related_concepts)}")

        lines.append("====================================")
        return "\n".join(lines)

    def to_prompt_context(self) -> Dict[str, Any]:
        """
        Returns a dictionary formatted for LLM prompt variable substitution.
        """
        return {
            "topic": self.topic,
            "journey_id": self.journey_id,
            "user_id": self.user_id,
            "experience_level": self.experience_level,
            "preferred_language": self.preferred_language,
            "secondary_languages": self.secondary_languages,
            "explanation_depth": self.explanation_depth,
            "learning_style": self.learning_style,
            "target_goals": self.target_goals or "",
            "overall_confidence": self.overall_confidence,
            "mental_model_summary": self.mental_model_summary,
            "known_concepts": self.known_concepts,
            "partially_known_concepts": self.partially_known_concepts,
            "active_gaps": self.active_gaps,
            "misconceptions": self.misconceptions,
            "verified_mastered_concepts": self.verified_mastered_concepts,
            "latest_quiz_score": self.latest_quiz_score or "",
            "prior_related_concepts": self.prior_related_concepts,
            "total_prior_journeys": self.total_prior_journeys,
            "formatted_context_block": self.format_for_prompt(),
        }
