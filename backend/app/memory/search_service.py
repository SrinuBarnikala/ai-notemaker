import json
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.assessment import Assessment
from backend.app.schemas.memory import SearchResultItem, SearchResponse


def highlight_snippet(text: str, query: str, max_chars: int = 160) -> str:
    """
    Extracts a contextual snippet containing the query terms, wrapped in <mark> tags.
    """
    if not text:
        return ""
    
    clean_text = re.sub(r"\s+", " ", text).strip()
    query_terms = [re.escape(t) for t in query.strip().split() if len(t) > 1]
    if not query_terms:
        return clean_text[:max_chars] + ("..." if len(clean_text) > max_chars else "")
    
    pattern = re.compile(f"({'|'.join(query_terms)})", re.IGNORECASE)
    match = pattern.search(clean_text)
    
    if not match:
        return clean_text[:max_chars] + ("..." if len(clean_text) > max_chars else "")
    
    start_pos = max(0, match.start() - 50)
    end_pos = min(len(clean_text), match.end() + 110)
    
    snippet = clean_text[start_pos:end_pos]
    if start_pos > 0:
        snippet = "..." + snippet
    if end_pos < len(clean_text):
        snippet = snippet + "..."
    
    # Highlight query terms
    highlighted = pattern.sub(r"<mark>\1</mark>", snippet)
    return highlighted


def calculate_relevance(query: str, title: str, body: str) -> int:
    q_low = query.lower()
    score = 0
    t_low = title.lower()
    b_low = body.lower()
    
    if q_low == t_low:
        score += 100
    elif q_low in t_low:
        score += 50
        
    terms = q_low.split()
    for term in terms:
        if term in t_low:
            score += 20
        if term in b_low:
            score += 5
            
    return score


def search_knowledge_base(
    db: Session,
    query: str,
    result_type: str = "all",
    journey_id: Optional[str] = None,
    limit: int = 30,
) -> SearchResponse:
    """
    Executes unified full-text search across journeys, notes, sections,
    knowledge concepts, code blocks, and flashcards.
    """
    q_clean = query.strip()
    if not q_clean:
        return SearchResponse(
            query=query,
            total_results=0,
            results=[],
            filters_applied={"result_type": result_type, "journey_id": journey_id},
        )
    
    results: List[Dict[str, Any]] = []
    q_pattern = re.compile(re.escape(q_clean), re.IGNORECASE)
    terms = [re.escape(t) for t in q_clean.split() if len(t) > 1]
    any_term_pattern = re.compile("|".join(terms), re.IGNORECASE) if terms else q_pattern

    # 1. Search Learning Journeys
    if result_type in ["all", "journey"]:
        journeys_query = db.query(LearningJourney)
        if journey_id:
            journeys_query = journeys_query.filter(LearningJourney.id == journey_id)
        
        for j in journeys_query.all():
            if any_term_pattern.search(j.topic):
                score = calculate_relevance(q_clean, j.topic, j.status)
                results.append({
                    "score": score,
                    "item": SearchResultItem(
                        id=f"journey-{j.id}",
                        result_type="journey",
                        title=j.topic,
                        subtitle=f"Learning Journey • Status: {j.status}",
                        snippet=highlight_snippet(j.topic, q_clean),
                        journey_id=j.id,
                        journey_topic=j.topic,
                        metadata={"created_at": j.created_at.isoformat(), "status": j.status},
                    )
                })

    # 2. Search Notes & Sections
    if result_type in ["all", "note", "section", "code"]:
        notes_query = db.query(Note)
        if journey_id:
            notes_query = notes_query.filter(Note.journey_id == journey_id)
        
        for note in notes_query.all():
            j_topic = note.journey.topic if note.journey else note.topic
            
            # Check note summary
            if result_type in ["all", "note"] and any_term_pattern.search(note.summary):
                score = calculate_relevance(q_clean, note.topic, note.summary)
                results.append({
                    "score": score,
                    "item": SearchResultItem(
                        id=f"note-{note.id}",
                        result_type="note",
                        title=note.topic,
                        subtitle=f"Living Note (v{note.version})",
                        snippet=highlight_snippet(note.summary, q_clean),
                        journey_id=note.journey_id,
                        journey_topic=j_topic,
                        note_id=note.id,
                        metadata={"version": note.version, "summary": note.summary},
                    )
                })
            
            # Check sections and structured blocks
            for sec in note.sections:
                sec_match = False
                matched_snippet = ""
                is_code_block = False
                code_lang = ""
                
                # Check section title
                if any_term_pattern.search(sec.title):
                    sec_match = True
                    matched_snippet = highlight_snippet(sec.title, q_clean)
                
                # Check blocks
                try:
                    blocks = json.loads(sec.blocks) if isinstance(sec.blocks, str) else (sec.blocks or [])
                except Exception:
                    blocks = []
                
                for block in blocks:
                    b_type = block.get("type", "")
                    b_content = block.get("content", "")
                    
                    if b_type == "code":
                        code_content = block.get("code", "")
                        explanation = block.get("explanation", "")
                        lang = block.get("language", "python")
                        if any_term_pattern.search(code_content) or any_term_pattern.search(explanation):
                            if result_type in ["all", "code"]:
                                score = calculate_relevance(q_clean, f"{sec.title} ({lang})", code_content) + 15
                                results.append({
                                    "score": score,
                                    "item": SearchResultItem(
                                        id=f"code-{sec.id}-{block.get('id', 'blk')}",
                                        result_type="code",
                                        title=f"Code: {sec.title}",
                                        subtitle=f"Executable {lang.upper()} snippet in '{j_topic}'",
                                        snippet=highlight_snippet(f"{explanation}\n{code_content}", q_clean),
                                        journey_id=note.journey_id,
                                        journey_topic=j_topic,
                                        note_id=note.id,
                                        section_id=sec.id,
                                        metadata={"language": lang, "order": sec.order_index},
                                    )
                                })
                    elif b_type in ["paragraph", "definition", "warning", "example", "comparison"]:
                        text_to_check = b_content or block.get("term", "") + " " + block.get("definition", "")
                        if any_term_pattern.search(text_to_check):
                            sec_match = True
                            if not matched_snippet:
                                matched_snippet = highlight_snippet(text_to_check, q_clean)
                
                if sec_match and result_type in ["all", "section"]:
                    score = calculate_relevance(q_clean, sec.title, matched_snippet)
                    results.append({
                        "score": score,
                        "item": SearchResultItem(
                            id=f"section-{sec.id}",
                            result_type="section",
                            title=sec.title,
                            subtitle=f"Section in '{j_topic}' (v{note.version})",
                            snippet=matched_snippet or f"Section '{sec.title}'",
                            journey_id=note.journey_id,
                            journey_topic=j_topic,
                            note_id=note.id,
                            section_id=sec.id,
                            metadata={"order_index": sec.order_index, "section_type": sec.section_type},
                        )
                    })

    # 3. Search Knowledge Concepts
    if result_type in ["all", "concept"]:
        concepts_query = db.query(KnowledgeConcept)
        if journey_id:
            concepts_query = concepts_query.join(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id)
        
        for c in concepts_query.all():
            j_id = c.profile.journey_id if c.profile else None
            j_topic = c.profile.journey.topic if (c.profile and c.profile.journey) else "Unknown Journey"
            
            c_text = f"{c.name} {c.notes or ''} {c.category} {c.level}"
            if any_term_pattern.search(c_text):
                score = calculate_relevance(q_clean, c.name, c.notes or "") + 25
                results.append({
                    "score": score,
                    "item": SearchResultItem(
                        id=f"concept-{c.id}",
                        result_type="concept",
                        title=c.name,
                        subtitle=f"Knowledge Concept • Category: {c.category.replace('_', ' ').capitalize()} ({c.level})",
                        snippet=highlight_snippet(f"{c.name}: {c.notes or 'Mapped in knowledge profile'}", q_clean),
                        journey_id=j_id,
                        journey_topic=j_topic,
                        metadata={
                            "category": c.category,
                            "level": c.level,
                            "notes": c.notes,
                        },
                    )
                })

    # 4. Search Flashcards & Assessment Quizzes
    if result_type in ["all", "flashcard"]:
        assessments_query = db.query(Assessment)
        if journey_id:
            assessments_query = assessments_query.filter(Assessment.journey_id == journey_id)
        
        for assess in assessments_query.all():
            j_topic = assess.journey.topic if assess.journey else "Mastery Assessment"
            
            # Flashcards
            try:
                flashcards = json.loads(assess.flashcards) if isinstance(assess.flashcards, str) else (assess.flashcards or [])
            except Exception:
                flashcards = []
            
            for fc in flashcards:
                front = fc.get("front", "")
                back = fc.get("back", "")
                concept = fc.get("concept", "")
                
                if any_term_pattern.search(front) or any_term_pattern.search(back) or any_term_pattern.search(concept):
                    score = calculate_relevance(q_clean, f"Flashcard: {concept or front[:30]}", back)
                    results.append({
                        "score": score,
                        "item": SearchResultItem(
                            id=f"fc-{assess.id}-{fc.get('id', 'item')}",
                            result_type="flashcard",
                            title=f"Flashcard: {concept or 'Active Recall'}",
                            subtitle=f"Assessment Card in '{j_topic}'",
                            snippet=highlight_snippet(f"Q: {front} | A: {back}", q_clean),
                            journey_id=assess.journey_id,
                            journey_topic=j_topic,
                            note_id=assess.note_id,
                            metadata={"front": front, "back": back, "concept": concept},
                        )
                    })

            # Quiz questions
            try:
                questions = json.loads(assess.quiz_questions) if isinstance(assess.quiz_questions, str) else (assess.quiz_questions or [])
            except Exception:
                questions = []
            
            for q in questions:
                q_text = q.get("question", "")
                exp = q.get("explanation", "")
                concept = q.get("concept", "")
                
                if any_term_pattern.search(q_text) or any_term_pattern.search(exp) or any_term_pattern.search(concept):
                    score = calculate_relevance(q_clean, f"Quiz: {concept or q_text[:30]}", exp)
                    results.append({
                        "score": score,
                        "item": SearchResultItem(
                            id=f"quiz-{assess.id}-{q.get('id', 'q')}",
                            result_type="flashcard",
                            title=f"Quiz Question: {concept or 'Mastery Check'}",
                            subtitle=f"Scenario Quiz in '{j_topic}'",
                            snippet=highlight_snippet(f"{q_text} ({exp})", q_clean),
                            journey_id=assess.journey_id,
                            journey_topic=j_topic,
                            note_id=assess.note_id,
                            metadata={"question": q_text, "concept": concept, "explanation": exp},
                        )
                    })

    # Sort results by relevance descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Deduplicate items by ID
    seen_ids = set()
    unique_items: List[SearchResultItem] = []
    for r in results:
        item = r["item"]
        if item.id not in seen_ids:
            seen_ids.add(item.id)
            unique_items.append(item)
            if len(unique_items) >= limit:
                break
                
    return SearchResponse(
        query=query,
        total_results=len(unique_items),
        results=unique_items,
        filters_applied={"result_type": result_type, "journey_id": journey_id},
    )
