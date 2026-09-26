"""
Comprehensive End-to-End Integration Test for the Personalized Technical Note Maker.
Tests the complete multi-phase pipeline in a single continuous user journey:
1. Topic Intake (Phase 1)
2. Adaptive Knowledge Discovery (Phase 2)
3. Knowledge Profile Synthesis (Phase 3)
4. Personalized Architecture Blueprinting (Phase 4)
5. Living Structured Note Generation (Phase 5 & 6)
6. Socratic Copilot Q&A & Note Pinning (Phase 11)
7. Active Recall Quiz & Knowledge Profile Progression (Phase 8)
8. Selective Section Evolution & Unaffected Section Invariance (Phase 7 & 12)
9. Concept Knowledge Graph Topology (Phase 12)
10. Publication-Ready PDF Export (Phase 14)
11. Universal Search & Knowledge Memory (Phase 15)
12. Version Snapshot Rollback & Audit Trail (Phase 13)
"""
import pytest
import json
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import SessionLocal
from backend.app.models.profile import KnowledgeProfile

def test_complete_end_to_end_journey_and_personalization(client):
    # 1. Topic Intake
    intake_res = client.post("/journeys", json={"topic": "Distributed Consensus & Paxos"})
    assert intake_res.status_code == 201
    journey_id = intake_res.json()["id"]

    # 2. Adaptive Knowledge Discovery (Phase 2)
    start_res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert start_res.status_code == 200
    assert "question_text" in start_res.json()

    ans1_res = client.post(f"/journeys/{journey_id}/discovery/answer", json={
        "answer": "I understand basic replication, but I am uncertain about leader leases, split-brain, and Paxos rounds."
    })
    assert ans1_res.status_code == 200

    ans2_res = client.post(f"/journeys/{journey_id}/discovery/answer", json={
        "answer": "I have not implemented Paxos in production; need clear mechanical steps and state machine breakdown."
    })
    assert ans2_res.status_code == 200

    # 3. Knowledge Profile Synthesis (Phase 3)
    prof_res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert prof_res.status_code == 200
    profile = prof_res.json()
    assert profile["overall_confidence"] in ["beginner", "intermediate", "advanced", "mixed"]
    assert len(profile["concepts"]) >= 1

    # 4. Personalized Architecture Blueprinting (Phase 4)
    arch_res = client.post(f"/journeys/{journey_id}/architecture", json={
        "learning_goal": "Master Paxos two-phase consensus and leader election"
    })
    assert arch_res.status_code == 200
    architecture = arch_res.json()
    assert len(architecture["sections"]) >= 3

    # 5. Living Structured Note Generation (Phase 5)
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    note = note_res.json()
    note_id = note["id"]
    assert note["version"] == 1
    assert len(note["sections"]) == len(architecture["sections"])

    # 6. Socratic Copilot Q&A and Pin-to-Note (Phase 11)
    target_section = note["sections"][1]
    copilot_res = client.post(f"/journeys/{journey_id}/copilot/ask", json={
        "question": "Why does Paxos require a majority quorum rather than full agreement?",
        "section_id": target_section["id"],
        "selected_text": "majority quorum",
    })
    assert copilot_res.status_code == 200
    copilot_data = copilot_res.json()
    assert len(copilot_data["answer"]) > 20

    pin_res = client.post(f"/journeys/{journey_id}/copilot/pin", json={
        "section_id": target_section["id"],
        "content": copilot_data["answer"],
        "title": "Quorum Intersection Invariant",
    })
    assert pin_res.status_code == 200
    pinned_data = pin_res.json()
    assert pinned_data["note_version"] == 2

    # 7. Active Recall Quiz & Knowledge Profile Progression (Phase 8)
    assess_res = client.post(f"/journeys/{journey_id}/assessment/generate")
    assert assess_res.status_code == 200
    assessment = assess_res.json()
    assert len(assessment["quiz_questions"]) >= 1

    perfect_answers = {q["id"]: q["correct_index"] for q in assessment["quiz_questions"]}
    submit_res = client.post(f"/journeys/{journey_id}/assessment/submit", json={"answers": perfect_answers})
    assert submit_res.status_code == 200
    assert submit_res.json()["percentage"] == 100.0

    # 8. Selective Section Evolution & Unaffected Section Invariance (Phase 7 & 12)
    # Check that section 0 is unaffected when evolving section 1
    fetch_note_res = client.get(f"/notes/{note_id}")
    current_note = fetch_note_res.json()
    sec0_before = json.dumps(current_note["sections"][0]["blocks"], sort_keys=True)

    evolve_res = client.post(f"/notes/{note_id}/evolve", json={
        "section_id": target_section["id"],
        "evolution_type": "add_code",
        "user_prompt": "Add a Python state machine for Paxos Prepare and Accept phases.",
    })
    assert evolve_res.status_code == 200
    evolved_note = evolve_res.json()
    assert evolved_note["version"] == 3

    sec0_after = json.dumps([s for s in evolved_note["sections"] if s["order_index"] == 1][0]["blocks"], sort_keys=True)
    assert sec0_before == sec0_after, "Unaffected section was unexpectedly modified during selective evolution"

    # 9. Concept Knowledge Graph Topology (Phase 12)
    graph_res = client.get(f"/journeys/{journey_id}/graph")
    assert graph_res.status_code == 200
    graph = graph_res.json()
    assert graph["total_nodes"] >= 3
    assert graph["total_edges"] >= 2

    # 10. Publication-Ready PDF Export (Phase 14)
    pdf_res = client.get(f"/notes/{note_id}/export/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")

    # 11. Universal Search & Knowledge Memory (Phase 15)
    search_res = client.get("/search?q=Paxos")
    assert search_res.status_code == 200
    assert search_res.json()["total_results"] >= 1

    memory_res = client.get("/memory/history")
    assert memory_res.status_code == 200
    assert len(memory_res.json()) >= 1

    related_res = client.get(f"/memory/related/{journey_id}")
    assert related_res.status_code == 200
    assert len(related_res.json()["related_topics"]) >= 1

    # 12. Version Snapshot Rollback & Audit Trail (Phase 13)
    restore_res = client.post(f"/notes/{note_id}/versions/1/restore")
    assert restore_res.status_code == 200
    restore_data = restore_res.json()
    assert restore_data["new_version"] == 4
    assert restore_data["note"]["version"] == 4
