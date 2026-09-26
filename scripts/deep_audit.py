"""
Deep Audit Script: End-to-End Persona Verification & Feature Interaction Test.
Tests two distinct personas:
- Persona A (Novice): Has misconceptions, low confidence, needs fundamental intuition.
- Persona B (Expert): Deep systems knowledge, only specific gaps in production tuning.
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import SessionLocal, Base, engine
from backend.app.models.journey import LearningJourney
from backend.app.models.note import Note, NoteSection, NoteRevision
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept

client = TestClient(app)

def run_audit():
    print("=" * 70)
    print("STARTING FULL END-TO-END SYSTEM AUDIT (PHASES 0-15)")
    print("=" * 70)
    
    findings = []
    
    # -------------------------------------------------------------
    # 1. PERSONA A: NOVICE LEARNER
    # -------------------------------------------------------------
    print("\n--- Testing Persona A: Novice on 'Vector Databases' ---")
    res = client.post("/journeys", json={"topic": "Vector Databases for Beginners"})
    assert res.status_code == 201, f"Failed intake: {res.text}"
    j_a = res.json()["id"]
    print(f"Created Journey A: {j_a}")
    
    # Discovery Q1
    res = client.post(f"/journeys/{j_a}/discovery/start")
    assert res.status_code == 200
    q1_a = res.json()
    print(f"Q1 (A): {q1_a['question_text']}")
    
    # Answer Q1 with beginner / misconception answer
    res = client.post(f"/journeys/{j_a}/discovery/answer", json={
        "answer": "I have never used vector databases. I thought search was just string matching with SQL LIKE '%pattern%'."
    })
    assert res.status_code == 200
    q2_a = res.json()
    print(f"Q2 (A): {q2_a['question_text']}")
    
    # Answer Q2 with unfamiliarity
    res = client.post(f"/journeys/{j_a}/discovery/answer", json={
        "answer": "I don't know what embeddings are or how cosine similarity works, this is completely new to me."
    })
    assert res.status_code == 200
    
    # Complete discovery
    res = client.post(f"/journeys/{j_a}/discovery/answer", json={
        "answer": "I am uncertain about high dimensions, need basic visual intuition from scratch."
    })
    assert res.status_code == 200
    
    # Synthesize Profile A
    res = client.post(f"/journeys/{j_a}/knowledge-profile")
    assert res.status_code == 200, f"Failed profile A: {res.text}"
    prof_a = res.json()
    print(f"Profile A Confidence: {prof_a['overall_confidence']}")
    print(f"Profile A Summary: {prof_a['summary']}")
    print(f"Profile A Gaps: {prof_a['gaps']}")
    print(f"Profile A Concepts: {[(c['name'], c['level'], c['category']) for c in prof_a['concepts']]}")
    
    # Generate Architecture A
    res = client.post(f"/journeys/{j_a}/architecture", json={"learning_goal": "Understand vector databases from first principles"})
    assert res.status_code == 200, f"Failed arch A: {res.text}"
    arch_a = res.json()
    print(f"Architecture A Sections: {[s['title'] for s in arch_a['sections']]}")
    
    # Generate Note A
    res = client.post(f"/journeys/{j_a}/generate-note")
    assert res.status_code == 200, f"Failed note A: {res.text}"
    note_a = res.json()
    print(f"Note A Version: {note_a['version']}, Section count: {len(note_a['sections'])}")
    
    # -------------------------------------------------------------
    # 2. PERSONA B: EXPERT LEARNER
    # -------------------------------------------------------------
    print("\n--- Testing Persona B: Expert on 'Vector Databases' ---")
    res = client.post("/journeys", json={"topic": "Vector Databases Architecture"})
    assert res.status_code == 201
    j_b = res.json()["id"]
    print(f"Created Journey B: {j_b}")
    
    # Discovery Q1
    res = client.post(f"/journeys/{j_b}/discovery/start")
    assert res.status_code == 200
    
    # Answer Q1 with expert production experience
    res = client.post(f"/journeys/{j_b}/discovery/answer", json={
        "answer": "I have deployed Milvus and Qdrant in production at scale with 50M embeddings and OpenAI text-embedding-3-large."
    })
    assert res.status_code == 200
    
    # Answer Q2 with expert nuance
    res = client.post(f"/journeys/{j_b}/discovery/answer", json={
        "answer": "I understand cosine vs dot product vs euclidean distance thoroughly. I have built custom SIMD distance functions in C++."
    })
    assert res.status_code == 200
    
    # Answer Q3 with specific advanced gap
    res = client.post(f"/journeys/{j_b}/discovery/answer", json={
        "answer": "My primary gap is Product Quantization (PQ) vs Scalar Quantization (SQ) trade-offs and tuning HNSW M and efConstruction for memory constraints."
    })
    assert res.status_code == 200
    
    # Synthesize Profile B
    res = client.post(f"/journeys/{j_b}/knowledge-profile")
    assert res.status_code == 200
    prof_b = res.json()
    print(f"Profile B Confidence: {prof_b['overall_confidence']}")
    print(f"Profile B Summary: {prof_b['summary']}")
    print(f"Profile B Gaps: {prof_b['gaps']}")
    print(f"Profile B Concepts: {[(c['name'], c['level'], c['category']) for c in prof_b['concepts']]}")
    
    # Generate Architecture B
    res = client.post(f"/journeys/{j_b}/architecture", json={"learning_goal": "Master HNSW index tuning and quantization trade-offs in production"})
    assert res.status_code == 200
    arch_b = res.json()
    print(f"Architecture B Sections: {[s['title'] for s in arch_b['sections']]}")
    
    # Generate Note B
    res = client.post(f"/journeys/{j_b}/generate-note")
    assert res.status_code == 200
    note_b = res.json()
    print(f"Note B Version: {note_b['version']}, Section count: {len(note_b['sections'])}")
    
    # -------------------------------------------------------------
    # 3. PERSONALIZATION COMPARISON AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 1: Personalization Differentiation ---")
    conf_diff = prof_a["overall_confidence"] != prof_b["overall_confidence"]
    print(f"Confidence differentiated: {conf_diff} (A: {prof_a['overall_confidence']} vs B: {prof_b['overall_confidence']})")
    if not conf_diff:
        findings.append({
            "severity": "MEDIUM",
            "category": "Personalization",
            "issue": f"Confidence was identical ({prof_a['overall_confidence']}) between novice and expert personas.",
            "impact": "May produce overly similar architectures if the LLM/fallback does not strongly separate beginner from advanced."
        })
        
    arch_titles_a = [s["title"] for s in arch_a["sections"]]
    arch_titles_b = [s["title"] for s in arch_b["sections"]]
    print(f"Architecture A titles: {arch_titles_a}")
    print(f"Architecture B titles: {arch_titles_b}")
    
    # -------------------------------------------------------------
    # 4. SELECTIVE EVOLUTION AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 2: Selective Note Evolution & State Preservation ---")
    note_id_a = note_a["id"]
    sections_before = {s["id"]: s["blocks"] for s in note_a["sections"]}
    target_sec_id = note_a["sections"][1]["id"]
    target_sec_title = note_a["sections"][1]["title"]
    sec_0_id = note_a["sections"][0]["id"]
    sec_0_blocks_before = json.dumps(sections_before[sec_0_id], sort_keys=True)
    
    print(f"Evolving section index 1: '{target_sec_title}' (id: {target_sec_id})...")
    res = client.post(f"/notes/{note_id_a}/evolve", json={
        "section_id": target_sec_id,
        "evolution_type": "add_code",
        "user_prompt": "Add production Python code demonstrating this concept with error handling."
    })
    assert res.status_code == 200, f"Evolution failed: {res.text}"
    evolved_note = res.json()
    print(f"Evolved Note Version: {evolved_note['version']} (was {note_a['version']})")
    
    # Check if Version bumped
    assert evolved_note["version"] == note_a["version"] + 1, "Note version failed to increment"
    
    # Check if section 0 was preserved exactly
    sec_0_blocks_after = json.dumps([b for b in evolved_note["sections"] if b["id"] == sec_0_id][0]["blocks"], sort_keys=True)
    unaffected_preserved = (sec_0_blocks_before == sec_0_blocks_after)
    print(f"Unaffected Section 0 preserved byte-for-byte: {unaffected_preserved}")
    if not unaffected_preserved:
        findings.append({
            "severity": "HIGH",
            "category": "State Preservation",
            "issue": "Evolving section 1 mutated or destroyed content in section 0.",
            "impact": "Violates the Core Living Note principle: unaffected sections must be strictly preserved."
        })
    else:
        print("PASS: Selective Evolution correctly preserved untouched sections.")
        
    # Check if Revision was logged
    res = client.get(f"/notes/{note_id_a}/versions")
    assert res.status_code == 200
    versions_data = res.json()
    print(f"Versions logged: {len(versions_data['versions'])}, Total versions: {versions_data['total_versions']}")
    assert len(versions_data["versions"]) >= 2, "Failed to log version history"
    
    # -------------------------------------------------------------
    # 5. COPILOT GROUNDING & PIN-TO-NOTE AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 3: Agent 9 Copilot Grounding & Pin-to-Note ---")
    res = client.post(f"/journeys/{j_a}/copilot/ask", json={
        "question": "Can you explain why cosine similarity is normalized?",
        "section_id": target_sec_id,
        "selected_text": "cosine similarity"
    })
    assert res.status_code == 200, f"Copilot ask failed: {res.text}"
    copilot_ans = res.json()
    print(f"Copilot answered ({len(copilot_ans['answer'])} chars): {copilot_ans['answer'][:120]}...")
    
    # Pin to Note
    ver_before_pin = evolved_note["version"]
    res = client.post(f"/journeys/{j_a}/copilot/pin", json={
        "section_id": target_sec_id,
        "content": copilot_ans["answer"],
        "title": "Cosine Normalization Insight"
    })
    assert res.status_code == 200, f"Pin failed: {res.text}"
    pin_res = res.json()
    pinned_note_id = pin_res["note_id"]
    pinned_version = pin_res["note_version"]
    print(f"Pinned! Note version is now: {pinned_version} (was {ver_before_pin})")
    assert pinned_version == ver_before_pin + 1, "Pinning did not increment version"
    
    # -------------------------------------------------------------
    # 6. ACTIVE RECALL ASSESSMENT & KNOWLEDGE PROFILE PROGRESSION
    # -------------------------------------------------------------
    print("\n--- AUDIT 4: Agent 6 Assessment & Knowledge Profile Progression ---")
    res = client.post(f"/journeys/{j_a}/assessment/generate")
    assert res.status_code == 200, f"Assessment gen failed: {res.text}"
    assessment = res.json()
    print(f"Flashcards generated: {len(assessment['flashcards'])}, Quiz questions: {len(assessment['quiz_questions'])}")
    
    # Submit 100% correct quiz
    quiz_submission = {
        q["id"]: q["correct_index"]
        for q in assessment["quiz_questions"]
    }
    res = client.post(f"/journeys/{j_a}/assessment/submit", json={"answers": quiz_submission})
    assert res.status_code == 200, f"Quiz submit failed: {res.text}"
    quiz_res = res.json()
    print(f"Quiz Score: {quiz_res['percentage']}% ({quiz_res['score']}/{quiz_res['total']})")
    print(f"Mastered concepts: {quiz_res.get('mastered_concepts', [])}")
    
    # Verify Profile was updated in DB
    db = SessionLocal()
    updated_prof = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == j_a).first()
    print(f"Updated profile confidence after perfect quiz: {updated_prof.overall_confidence}")
    db.close()
    
    # -------------------------------------------------------------
    # 7. KNOWLEDGE GRAPH TOPOLOGY AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 5: Agent 10 Concept Knowledge Graph ---")
    res = client.get(f"/journeys/{j_a}/graph")
    assert res.status_code == 200, f"Graph failed: {res.text}"
    graph_data = res.json()
    print(f"Graph nodes: {len(graph_data['nodes'])}, edges: {len(graph_data['edges'])}")
    has_mastered = any(n.get("state") == "mastered" for n in graph_data["nodes"])
    print(f"Graph reflects updated mastery state: {has_mastered}")
    
    # -------------------------------------------------------------
    # 8. DERIVED PDF EXPORT AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 6: Phase 14 Publication PDF Export ---")
    res = client.get(f"/notes/{pinned_note_id}/export/pdf")
    assert res.status_code == 200, f"PDF export failed: {res.text}"
    assert res.headers.get("content-type") == "application/pdf"
    pdf_bytes = res.content
    print(f"Generated PDF size: {len(pdf_bytes)} bytes. Starts with %PDF: {pdf_bytes.startswith(b'%PDF')}")
    assert pdf_bytes.startswith(b"%PDF"), "PDF did not return valid PDF magic bytes"
    
    # -------------------------------------------------------------
    # 9. SEARCH & KNOWLEDGE MEMORY AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 7: Phase 15 Search & Knowledge Memory ---")
    res = client.get("/search?q=Vector")
    assert res.status_code == 200, f"Search failed: {res.text}"
    search_res = res.json()
    print(f"Search for 'Vector' returned {search_res['total_results']} results")
    assert search_res["total_results"] > 0, "Universal search returned 0 results for existing topic"
    
    res = client.get("/memory/history")
    assert res.status_code == 200
    history_res = res.json()
    print(f"Learning History entries: {len(history_res)}")
    assert len(history_res) >= 2, "Learning history missing recorded journeys"
    
    res = client.get(f"/memory/related/{j_a}")
    assert res.status_code == 200
    related_res = res.json()
    print(f"Related recommendations for Journey A: {[r['topic'] for r in related_res['related_topics']]}")
    
    # -------------------------------------------------------------
    # 10. REVERSION & ROLLBACK AUDIT
    # -------------------------------------------------------------
    print("\n--- AUDIT 8: Phase 13 Version Rollback ---")
    res = client.post(f"/notes/{pinned_note_id}/versions/1/restore")
    assert res.status_code == 200, f"Restore failed: {res.text}"
    restore_data = res.json()
    restored_note = restore_data["note"]
    print(f"Restored note version is now: {restored_note['version']} (restored from v1 snapshot)")
    assert restored_note["version"] > pinned_version, "Restore did not append an audit-safe new version"
    
    print("\n" + "=" * 70)
    print("AUDIT EXECUTION COMPLETE")
    print(f"Total findings logged: {len(findings)}")
    print("=" * 70)
    for idx, f in enumerate(findings, 1):
        print(f"[{idx}] {f['severity']} - {f['category']}: {f['issue']}")

if __name__ == "__main__":
    run_audit()
