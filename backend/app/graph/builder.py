import json
import logging
import re
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.note import Note, NoteSection
from backend.app.schemas.graph import GraphNode, GraphEdge, ConceptGraphResponse
from backend.app.providers.base import LLMProvider
from backend.app.graph.prompts import (
    GRAPH_SYNTHESIS_SYSTEM_PROMPT,
    GRAPH_SYNTHESIS_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


def safe_load_json(val: Any) -> Any:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val if val is not None else []


def extract_graph_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


async def build_journey_concept_graph(
    journey_id: str,
    db: Session,
    provider: Optional[LLMProvider] = None,
) -> ConceptGraphResponse:
    """
    Agent 10: Synthesizes an interactive concept dependency graph for a specific journey.
    """
    journey = db.query(LearningJourney).filter(LearningJourney.id == journey_id).first()
    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journey '{journey_id}' not found.",
        )

    note = db.query(Note).filter(Note.journey_id == journey_id).first()
    profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == journey_id).first()

    nodes: List[GraphNode] = []
    node_id_map: Dict[str, GraphNode] = {}
    node_names_lower: Dict[str, str] = {}

    def add_node(
        name: str,
        status_val: str,
        sec_id: Optional[str] = None,
        sec_title: Optional[str] = None,
        depth: str = "standard",
        group: str = "concept",
        summary_val: Optional[str] = None,
    ) -> str:
        clean_name = name.strip()
        low = clean_name.lower()
        if low in node_names_lower:
            existing_id = node_names_lower[low]
            # Upgrade status if more specific (e.g. misconception or gap)
            if status_val in ["misconception", "gap"]:
                node_id_map[existing_id].status = status_val
            if sec_id and not node_id_map[existing_id].section_id:
                node_id_map[existing_id].section_id = sec_id
                node_id_map[existing_id].section_title = sec_title
            return existing_id

        node_id = f"node-{len(nodes) + 1}"
        node = GraphNode(
            id=node_id,
            name=clean_name,
            status=status_val if status_val in ["known", "partial", "gap", "misconception"] else "known",
            journey_id=journey_id,
            journey_topic=journey.topic,
            section_id=sec_id,
            section_title=sec_title,
            depth=depth,
            size=26 if group == "topic" else (22 if status_val == "misconception" else 20),
            group=group,
            summary=summary_val,
        )
        nodes.append(node)
        node_id_map[node_id] = node
        node_names_lower[low] = node_id
        return node_id

    # 1. Add Journey Topic as central Anchor Node
    topic_node_id = add_node(
        name=journey.topic,
        status_val="known",
        group="topic",
        summary_val=f"Central technical topic for learning journey: {journey.topic}",
    )

    # 2. Extract from Profile Concepts
    misconceptions_list = []
    if profile:
        raw_misc = safe_load_json(profile.misconceptions)
        for m in raw_misc:
            text = m if isinstance(m, str) else m.get("misconception", "")
            if text:
                misconceptions_list.append(text)

        gaps_list = []
        raw_gaps = safe_load_json(profile.gaps)
        for g in raw_gaps:
            text = g if isinstance(g, str) else g.get("gap", "")
            if text:
                gaps_list.append(text)

        for c in profile.concepts:
            # Determine status
            c_status = "known"
            if any(m.lower() in c.name.lower() or c.name.lower() in m.lower() for m in misconceptions_list):
                c_status = "misconception"
            elif any(g.lower() in c.name.lower() or c.name.lower() in g.lower() for m in gaps_list):
                c_status = "gap"
            elif c.category == "known" or c.level == "strong":
                c_status = "known"
            elif c.category == "partially_known" or c.level == "moderate":
                c_status = "partial"
            else:
                c_status = "gap"

            add_node(
                name=c.name,
                status_val=c_status,
                depth=c.level or "standard",
                summary_val=c.notes or f"{c_status.capitalize()} concept in {journey.topic}",
            )

        # Ensure explicit misconceptions are mapped
        for misc in misconceptions_list:
            clean_misc = misc[:45].strip().rstrip(".")
            add_node(
                name=f"Pitfall: {clean_misc}",
                status_val="misconception",
                summary_val=misc,
            )

        # Ensure explicit gaps are mapped
        for gap in gaps_list:
            clean_gap = gap[:45].strip().rstrip(".")
            add_node(
                name=clean_gap,
                status_val="gap",
                summary_val=gap,
            )

    # 3. Associate and supplement with Note Sections
    if note and note.sections:
        for sec in note.sections:
            sec_node_id = add_node(
                name=sec.title,
                status_val="known" if sec.depth == "brief" else ("partial" if sec.depth == "standard" else "gap"),
                sec_id=sec.id,
                sec_title=sec.title,
                depth=sec.depth,
                group="section",
                summary_val=f"Section {sec.order_index}: {sec.section_type} ({sec.depth})",
            )

    # 4. Generate Edges (Prerequisites, Subconcepts, Implementations)
    edges: List[GraphEdge] = []
    seen_edges: Set[str] = set()

    def add_edge(src_name_or_id: str, tgt_name_or_id: str, rel: str = "prerequisite", label: Optional[str] = None):
        src_id = node_names_lower.get(src_name_or_id.lower(), src_name_or_id)
        tgt_id = node_names_lower.get(tgt_name_or_id.lower(), tgt_name_or_id)
        if src_id == tgt_id or src_id not in node_id_map or tgt_id not in node_id_map:
            return
        edge_key = f"{src_id}->{tgt_id}"
        if edge_key in seen_edges:
            return
        seen_edges.add(edge_key)
        edges.append(
            GraphEdge(
                source=src_id,
                target=tgt_id,
                relationship=rel if rel in ["prerequisite", "subconcept", "compares_to", "implements", "relates_to"] else "prerequisite",
                label=label or rel.replace("_", " "),
            )
        )

    # Agent 10 LLM Graph Synthesis if provider is available
    llm_succeeded = False
    if provider and len(nodes) > 2:
        try:
            sec_summaries = []
            if note and note.sections:
                for s in note.sections:
                    sec_summaries.append(f"- Section {s.order_index}: {s.title} ({s.section_type})")
            
            concepts_summaries = [f"- {n.name} [{n.status}]" for n in nodes if n.group != "topic"]

            prompt = GRAPH_SYNTHESIS_PROMPT_TEMPLATE.format(
                topic=journey.topic,
                sections_summary="\n".join(sec_summaries) if sec_summaries else "Core foundations and trade-offs.",
                concepts_summary="\n".join(concepts_summaries[:15]),
                gaps_summary=f"Misconceptions: {len(misconceptions_list)}, Gaps: {len(gaps_list)}",
            )

            raw_res = await provider.generate(
                prompt=prompt,
                system_prompt=GRAPH_SYNTHESIS_SYSTEM_PROMPT,
                temperature=0.2,
            )
            parsed = extract_graph_json(raw_res)
            if parsed and isinstance(parsed.get("edges"), list) and len(parsed["edges"]) > 0:
                for e in parsed["edges"]:
                    if isinstance(e, dict) and e.get("source") and e.get("target"):
                        add_edge(e["source"], e["target"], e.get("relationship", "prerequisite"), e.get("label"))
                llm_succeeded = len(edges) > 0
        except Exception as err:
            logger.warning(f"Agent 10 LLM graph generation fallback triggered: {err}")

    # Fallback deterministic topological linking if LLM produced no edges or was not called
    if not llm_succeeded:
        # Link topic anchor to main sections / core concepts
        for n in nodes:
            if n.id != topic_node_id:
                if n.group == "section":
                    add_edge(topic_node_id, n.id, "subconcept", "contains")
                elif n.status in ["known", "partial"]:
                    add_edge(topic_node_id, n.id, "prerequisite", "foundational")
                elif n.status == "misconception":
                    # Link misconception to topic or related section
                    add_edge(n.id, topic_node_id, "compares_to", "contrasts")
                elif n.status == "gap":
                    add_edge(topic_node_id, n.id, "implements", "targets gap")

        # Link sequential sections as a prerequisite chain
        sec_nodes = [n for n in nodes if n.group == "section"]
        for i in range(len(sec_nodes) - 1):
            add_edge(sec_nodes[i].id, sec_nodes[i + 1].id, "prerequisite", "builds into")

    # Calculate mastery breakdown
    breakdown = {"known": 0, "partial": 0, "gap": 0, "misconception": 0}
    for n in nodes:
        if n.group != "topic" and n.status in breakdown:
            breakdown[n.status] += 1

    summary_text = (
        f"Graph of {len(nodes)} concepts and {len(edges)} dependency relationships for {journey.topic}. "
        f"{breakdown['known']} mastered, {breakdown['partial']} in-progress, "
        f"{breakdown['gap']} gaps, and {breakdown['misconception']} misconceptions."
    )

    return ConceptGraphResponse(
        journey_id=journey_id,
        title=f"Knowledge Graph: {journey.topic}",
        is_global=False,
        total_nodes=len(nodes),
        total_edges=len(edges),
        nodes=nodes,
        edges=edges,
        summary=summary_text,
        mastery_breakdown=breakdown,
    )


def build_global_concept_graph(db: Session) -> ConceptGraphResponse:
    """
    Agent 10: Merges concepts across all user learning journeys into a cohesive global knowledge map.
    """
    journeys = db.query(LearningJourney).all()
    if not journeys:
        return ConceptGraphResponse(
            journey_id=None,
            title="Global Technical Universe",
            is_global=True,
            total_nodes=0,
            total_edges=0,
            nodes=[],
            edges=[],
            summary="No learning journeys recorded yet.",
            mastery_breakdown={"known": 0, "partial": 0, "gap": 0, "misconception": 0},
        )

    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    seen_nodes: Dict[str, str] = {}
    seen_edges: Set[str] = set()

    for j in journeys:
        # Journey Anchor Node
        j_node_id = f"global-j-{j.id[:8]}"
        if j_node_id not in seen_nodes:
            seen_nodes[j_node_id] = j_node_id
            nodes.append(
                GraphNode(
                    id=j_node_id,
                    name=j.topic,
                    status="known",
                    journey_id=j.id,
                    journey_topic=j.topic,
                    size=28,
                    group="journey",
                    summary=f"Journey: {j.topic} ({j.status})",
                )
            )

        # Profile concepts for this journey
        profile = db.query(KnowledgeProfile).filter(KnowledgeProfile.journey_id == j.id).first()
        if profile and profile.concepts:
            for c in profile.concepts:
                c_low = c.name.strip().lower()
                c_status = "known" if (c.category == "known" or c.level == "strong") else ("partial" if c.category == "partially_known" else "gap")
                c_id = f"c-{abs(hash(c_low)) % 100000}"

                if c_id not in seen_nodes:
                    seen_nodes[c_id] = c_id
                    nodes.append(
                        GraphNode(
                            id=c_id,
                            name=c.name.strip(),
                            status=c_status,
                            journey_id=j.id,
                            journey_topic=j.topic,
                            size=18,
                            group="concept",
                            summary=f"{c_status.capitalize()} concept: {c.name}",
                        )
                    )

                # Connect concept to journey anchor
                edge_key = f"{j_node_id}->{c_id}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(
                        GraphEdge(
                            source=j_node_id,
                            target=c_id,
                            relationship="subconcept",
                            label="covers",
                        )
                    )

    # Interconnect journeys that share similar words/domain concepts
    journey_nodes = [n for n in nodes if n.group == "journey"]
    for i in range(len(journey_nodes)):
        for k in range(i + 1, len(journey_nodes)):
            j1 = journey_nodes[i]
            j2 = journey_nodes[k]
            # Simple keyword overlap detection
            words1 = set(re.findall(r"\w{4,}", j1.name.lower()))
            words2 = set(re.findall(r"\w{4,}", j2.name.lower()))
            overlap = words1.intersection(words2)
            if overlap or len(journey_nodes) <= 4:
                edge_key = f"{j1.id}->{j2.id}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(
                        GraphEdge(
                            source=j1.id,
                            target=j2.id,
                            relationship="relates_to",
                            label=", ".join(list(overlap)[:2]) if overlap else "cross-domain",
                        )
                    )

    breakdown = {"known": 0, "partial": 0, "gap": 0, "misconception": 0}
    for n in nodes:
        if n.group != "journey" and n.status in breakdown:
            breakdown[n.status] += 1

    return ConceptGraphResponse(
        journey_id=None,
        title="Global Technical Universe",
        is_global=True,
        total_nodes=len(nodes),
        total_edges=len(edges),
        nodes=nodes,
        edges=edges,
        summary=f"Global map connecting {len(journeys)} learning journey(s) with {len(nodes)} technical concepts.",
        mastery_breakdown=breakdown,
    )
