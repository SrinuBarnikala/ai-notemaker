import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.note import Note, NoteSection
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.schemas.memory import (
    ConceptProvenance,
    ConceptEvolutionStep,
    RelatedTopicItem,
    RelatedTopicsResponse,
    CrossReferenceTag,
    NoteMemoryReferencesResponse,
    LearningHistoryJourney,
    KnowledgeMemoryOverview,
)

logger = logging.getLogger(__name__)


def safe_json_load(val: Any) -> Any:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val if val is not None else []


def get_all_concept_memories(db: Session) -> List[ConceptProvenance]:
    """
    Constructs a comprehensive concept memory inventory across all learner journeys.
    Identifies provenance, first encountered journey, subsequent appearances, and mastery trajectory.
    """
    # Fetch all journeys ordered by created_at ascending (chronological)
    journeys = db.query(LearningJourney).order_by(LearningJourney.created_at.asc()).all()
    if not journeys:
        return []

    # Map concepts: lowercase concept name -> tracking dict
    concept_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "display_name": "",
        "steps": [],
        "notes": set(),
        "related": set(),
        "first_journey_id": "",
        "first_journey_topic": "",
        "first_encountered_at": None,
        "first_encountered_category": "unknown",
        "current_status": "known",
    })

    # 1. Process each journey chronologically
    for j in journeys:
        profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == j.id).first()
        note = db.query(Note).filter(Note.journey_id == j.id).first()
        assessment = db.query(Assessment).filter(Assessment.journey_id == j.id).first()

        mastered_in_quiz: Set[str] = set()
        if assessment and assessment.submissions:
            for sub in assessment.submissions:
                m_list = safe_json_load(sub.mastered_concepts)
                for m in m_list:
                    mastered_in_quiz.add(m.strip().lower())

        if profile and profile.concepts:
            # Cross-pollinate related concepts within the same journey
            journey_concept_names = [c.name.strip() for c in profile.concepts]

            for c in profile.concepts:
                name_clean = c.name.strip()
                name_low = name_clean.lower()
                c_data = concept_map[name_low]

                if not c_data["display_name"]:
                    c_data["display_name"] = name_clean

                # Determine effective status
                status_val = c.category
                if name_low in mastered_in_quiz:
                    status_val = "mastered"
                elif c.category == "known" or c.level == "strong":
                    status_val = "known"
                elif c.category == "partially_known" or c.level == "moderate":
                    status_val = "partial"
                else:
                    status_val = "gap"

                # If first encounter
                if c_data["first_encountered_at"] is None:
                    c_data["first_journey_id"] = j.id
                    c_data["first_journey_topic"] = j.topic
                    c_data["first_encountered_at"] = j.created_at
                    c_data["first_encountered_category"] = c.category

                # Update current status
                c_data["current_status"] = status_val

                # Record evolution step
                step = ConceptEvolutionStep(
                    journey_id=j.id,
                    journey_topic=j.topic,
                    timestamp=j.created_at,
                    category=c.category,
                    level=c.level,
                    context_note=c.notes,
                    event_type="assessment_mastered" if name_low in mastered_in_quiz else "discovery",
                )
                c_data["steps"].append(step)

                # Link note ID if note exists
                if note:
                    c_data["notes"].add(note.id)

                # Add peer concepts as related
                for peer in journey_concept_names:
                    if peer.lower() != name_low:
                        c_data["related"].add(peer)

    # Convert to ConceptProvenance schema
    provenances: List[ConceptProvenance] = []
    for name_low, data in concept_map.items():
        total_apps = len(data["steps"])
        first_topic = data["first_journey_topic"]
        first_cat = data["first_encountered_category"].replace("_", " ")
        curr_status = data["current_status"]

        # Synthesize human-readable knowledge provenance story
        if total_apps == 1:
            story = (
                f"You first encountered '{data['display_name']}' while learning '{first_topic}', "
                f"where it was mapped as a {first_cat} concept."
            )
        else:
            story = (
                f"You first encountered '{data['display_name']}' while exploring '{first_topic}' (as a {first_cat}). "
                f"It has since reappeared across {total_apps} learning journeys and is currently {curr_status}."
            )

        provenances.append(
            ConceptProvenance(
                concept_name=data["display_name"],
                first_encountered_journey_id=data["first_journey_id"],
                first_encountered_journey_topic=data["first_journey_topic"],
                first_encountered_at=data["first_encountered_at"] or datetime.now(timezone.utc),
                first_encountered_category=data["first_encountered_category"],
                current_status=curr_status,
                total_appearances=total_apps,
                provenance_story=story,
                history=data["steps"],
                linked_note_ids=list(data["notes"]),
                related_concepts=list(data["related"])[:8],
            )
        )

    # Sort by total appearances descending, then by name
    provenances.sort(key=lambda p: (p.total_appearances, p.concept_name), reverse=True)
    return provenances


def get_concept_memory(concept_name: str, db: Session) -> ConceptProvenance:
    """
    Retrieves deep provenance and evolution memory for a specific concept.
    """
    clean_target = concept_name.strip().lower()
    all_memories = get_all_concept_memories(db)

    for mem in all_memories:
        if mem.concept_name.lower() == clean_target:
            return mem

    # If exact match not found, try partial match
    for mem in all_memories:
        if clean_target in mem.concept_name.lower() or mem.concept_name.lower() in clean_target:
            return mem

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Concept '{concept_name}' not found in learner knowledge memory.",
    )


def get_learning_history(db: Session) -> List[LearningHistoryJourney]:
    """
    Retrieves chronological timeline of all learning journeys, their notes,
    concept breakdowns, and assessment stats.
    """
    journeys = db.query(LearningJourney).order_by(LearningJourney.created_at.desc()).all()
    history_items: List[LearningHistoryJourney] = []

    for j in journeys:
        note = db.query(Note).filter(Note.journey_id == j.id).first()
        profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == j.id).first()
        assessment = db.query(Assessment).filter(Assessment.journey_id == j.id).first()

        concept_names: List[str] = []
        mastered_count = 0
        gap_count = 0

        if profile and profile.concepts:
            for c in profile.concepts:
                concept_names.append(c.name)
                if c.category == "known" or c.level == "strong":
                    mastered_count += 1
                elif c.category in ["unknown", "gap"]:
                    gap_count += 1

        quiz_score_str = None
        if assessment and assessment.submissions:
            latest_sub = assessment.submissions[0]
            quiz_score_str = f"{latest_sub.score}/{latest_sub.total}"

        history_items.append(
            LearningHistoryJourney(
                id=j.id,
                topic=j.topic,
                status=j.status,
                created_at=j.created_at,
                updated_at=j.updated_at,
                note_id=note.id if note else None,
                note_version=note.version if note else None,
                total_sections=len(note.sections) if note else 0,
                total_concepts=len(concept_names),
                concepts_mastered=mastered_count,
                concepts_gap=gap_count,
                concept_names=concept_names,
                latest_quiz_score=quiz_score_str,
            )
        )

    return history_items


def get_memory_overview(db: Session) -> KnowledgeMemoryOverview:
    """
    Computes global knowledge memory statistics across all journeys.
    """
    history = get_learning_history(db)
    all_memories = get_all_concept_memories(db)
    notes_count = db.query(Note).count()

    total_mastered = 0
    total_gaps = 0
    total_misconceptions = 0

    # Count profile misconceptions
    profiles = db.query(KnowledgeProfile).all()
    for p in profiles:
        misc = safe_json_load(p.misconceptions)
        total_misconceptions += len(misc)

    for mem in all_memories:
        if mem.current_status in ["mastered", "known"]:
            total_mastered += 1
        elif mem.current_status in ["gap", "misconception"]:
            total_gaps += 1

    # Find bridging concepts (concepts present in >1 journey)
    bridging = [
        {
            "name": mem.concept_name,
            "appearances": mem.total_appearances,
            "first_topic": mem.first_encountered_journey_topic,
            "status": mem.current_status,
        }
        for mem in all_memories
        if mem.total_appearances > 1
    ][:10]

    return KnowledgeMemoryOverview(
        total_journeys=len(history),
        total_notes=notes_count,
        total_concepts_tracked=len(all_memories),
        total_concepts_mastered=total_mastered,
        total_knowledge_gaps=total_gaps,
        total_misconceptions=total_misconceptions,
        top_bridging_concepts=bridging,
        recent_history=history[:10],
    )


def get_related_topics(journey_id: str, db: Session) -> RelatedTopicsResponse:
    """
    Identifies related technical topics and suggests next learning paths
    derived from bridging concepts, unresolved gaps, and cross-journey linkages.
    """
    current_journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not current_journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journey '{journey_id}' not found.",
        )

    profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()
    other_journeys = db.query(LearningJourney).filter(LearningJourney.id != journey_id).all()
    
    current_concepts: Set[str] = set()
    current_gaps: List[str] = []
    if profile:
        for c in profile.concepts:
            current_concepts.add(c.name.strip().lower())
            if c.category in ["unknown", "gap"] or c.level == "weak":
                current_gaps.append(c.name.strip())
        
        # Add gaps from profile.gaps
        raw_gaps = safe_json_load(profile.gaps)
        for g in raw_gaps:
            if isinstance(g, str) and g not in current_gaps:
                current_gaps.append(g)

    related_items: List[RelatedTopicItem] = []
    bridging_concepts_all: Set[str] = set()

    # 1. Check existing journeys that share concepts
    for other_j in other_journeys:
        other_profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == other_j.id).first()
        other_note = db.query(Note).filter(Note.journey_id == other_j.id).first()
        
        if other_profile and other_profile.concepts:
            shared = []
            for oc in other_profile.concepts:
                oc_name = oc.name.strip()
                if oc_name.lower() in current_concepts:
                    shared.append(oc_name)
                    bridging_concepts_all.add(oc_name)
            
            if shared:
                related_items.append(
                    RelatedTopicItem(
                        topic=other_j.topic,
                        reason=f"Shares {len(shared)} foundational concepts ({', '.join(shared[:3])}) with your current exploration.",
                        relationship_type="shared_prerequisite",
                        bridging_concepts=shared,
                        existing_journey_id=other_j.id,
                        existing_note_id=other_note.id if other_note else None,
                    )
                )

    # 2. Formulate recommended next topics based on open knowledge gaps
    topic_heuristics = {
        "rag": ["Vector Databases & Similarity Search", "Advanced Reranking & Cross-Encoders", "Fine-Tuning Embedding Models"],
        "retrieval": ["Vector Indexing with HNSW", "BM25 Hybrid Search Architecture", "GraphRAG & Knowledge Graphs"],
        "transformer": ["FlashAttention & Memory Optimizations", "Positional Encodings (RoPE & ALiBi)", "Quantization: GGUF, AWQ, and GPTQ"],
        "attention": ["Transformer Multi-Query & Grouped-Query Attention", "Sparse Attention Mechanisms", "KV Cache Management"],
        "consensus": ["Raft vs Paxos Distributed Consensus", "Vector Clock Causal Consistency", "Distributed Transactions & 2PC"],
        "ebpf": ["Linux Kernel Tracing with BPF CO-RE", "XDP High-Performance Packet Filtering", "eBPF Security Auditing with Tetragon"],
        "python": ["Python AsyncIO Event Loop Internals", "Memory Management & Garbage Collection", "Cython & C-Extensions"],
    }

    low_current_topic = current_journey.topic.lower()
    matched_suggestions: List[str] = []
    for keyword, suggestions in topic_heuristics.items():
        if keyword in low_current_topic or any(keyword in g.lower() for g in current_gaps):
            matched_suggestions.extend(suggestions)

    # If gaps exist, formulate direct gap-closing topics
    for gap in current_gaps[:3]:
        related_items.append(
            RelatedTopicItem(
                topic=f"Mastering {gap}",
                reason=f"Identified as an active knowledge gap during your '{current_journey.topic}' discovery session.",
                relationship_type="builds_on_gap",
                bridging_concepts=[gap],
                existing_journey_id=None,
                existing_note_id=None,
            )
        )

    # Add matched heuristics
    for sugg in matched_suggestions:
        if not any(r.topic.lower() == sugg.lower() for r in related_items):
            related_items.append(
                RelatedTopicItem(
                    topic=sugg,
                    reason=f"Logical architectural continuation from '{current_journey.topic}'.",
                    relationship_type="logical_next_step",
                    bridging_concepts=list(current_concepts)[:2],
                    existing_journey_id=None,
                    existing_note_id=None,
                )
            )

    return RelatedTopicsResponse(
        journey_id=journey_id,
        journey_topic=current_journey.topic,
        related_topics=related_items[:6],
        bridging_concepts=list(bridging_concepts_all),
    )


def get_note_cross_references(note_id: str, db: Session) -> NoteMemoryReferencesResponse:
    """
    Identifies concepts within a canonical note that have prior memory provenance
    from EARLIER learning journeys (e.g. "You first encountered reranking in RAG").
    """
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note '{note_id}' not found.",
        )

    current_journey = note.journey
    all_memories = get_all_concept_memories(db)

    # Filter memories that originated in EARLIER journeys (not this journey)
    cross_refs: List[CrossReferenceTag] = []
    
    for mem in all_memories:
        # Check if concept first appeared in a different journey
        if mem.first_encountered_journey_id != note.journey_id:
            c_name_low = mem.concept_name.lower()
            
            # Check if this concept is mentioned in any section of the current note
            for sec in note.sections:
                sec_text = sec.title + " " + sec.blocks
                if c_name_low in sec_text.lower():
                    cross_refs.append(
                        CrossReferenceTag(
                            concept_name=mem.concept_name,
                            provenance_story=mem.provenance_story,
                            first_journey_id=mem.first_encountered_journey_id,
                            first_journey_topic=mem.first_encountered_journey_topic,
                            first_encountered_at=mem.first_encountered_at,
                            current_status=mem.current_status,
                            section_id=sec.id,
                            section_title=sec.title,
                        )
                    )
                    break  # One tag per concept across note sections

    return NoteMemoryReferencesResponse(
        note_id=note.id,
        journey_id=note.journey_id,
        cross_references=cross_refs,
        total_memory_bridges=len(cross_refs),
    )
