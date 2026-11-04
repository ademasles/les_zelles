"""A typed knowledge graph of one CCTP.

Nodes: the document, its lots and articles, passages, requirements, and the
standards, certifications and materials they mention, plus the topic
categories of the domain ontology. Edges carry meaning an agent can traverse:

    document -CONTAINS-> lot -CONTAINS-> section -CONTAINS-> passage
    passage  -STATES-> requirement -ABOUT-> topic
    requirement -APPLIES_TO-> section
    passage  -CITES-> standard -GOVERNS-> topic
    section  -REFERS_TO-> section        (cross-references: "voir article 3.2")
    section  -USES-> material
    requirement -CONFLICTS_WITH-> requirement

The graph is small (hundreds of nodes per CCTP) and lives in memory; it
exports to node-link JSON for the UI and to Cypher for Neo4j when a portfolio
of tenders needs to be queried together.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from zelles.domain.documents import Chunk
from zelles.domain.spec import Category, Requirement, RequirementStatus, SpecField, SpecSheet
from zelles.graph.ontology import lookup, standard_key


class NodeType(StrEnum):
    DOCUMENT = "Document"
    LOT = "Lot"
    SECTION = "Section"
    PASSAGE = "Passage"
    REQUIREMENT = "Requirement"
    STANDARD = "Standard"
    CERTIFICATION = "Certification"
    MATERIAL = "Material"
    TOPIC = "Topic"


class EdgeType(StrEnum):
    CONTAINS = "CONTAINS"
    STATES = "STATES"
    ABOUT = "ABOUT"
    APPLIES_TO = "APPLIES_TO"
    CITES = "CITES"
    GOVERNS = "GOVERNS"
    REFERS_TO = "REFERS_TO"
    USES = "USES"
    REQUIRES = "REQUIRES"
    CONFLICTS_WITH = "CONFLICTS_WITH"


class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    props: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    source: str
    target: str
    type: EdgeType
    props: dict[str, Any] = Field(default_factory=dict)


class Conflict(BaseModel):
    field: SpecField
    scope: str | None
    values: list[str]
    requirement_ids: list[str]
    message: str


_CROSS_REF = re.compile(
    r"(?:voir|cf\.?|se\s+reporter\s+(?:à\s+l'|au|aux)|conformément\s+(?:à\s+l'|au)|"
    r"définie?s?\s+(?:à\s+l'|au)|décrite?s?\s+(?:à\s+l'|au))\s*"
    r"(?:article|art\.?|§|chapitre|paragraphe)?\s*(\d{1,2}(?:\.\d{1,3}){0,4})",
    re.IGNORECASE,
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


class KnowledgeGraph(BaseModel):
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)

    # ---------------------------------------------------------------- building
    def add_node(self, node_id: str, type_: NodeType, label: str, **props: Any) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(id=node_id, type=type_, label=label, props=props)
        else:
            self.nodes[node_id].props.update({k: v for k, v in props.items() if v is not None})
        return node_id

    def add_edge(self, source: str, target: str, type_: EdgeType, **props: Any) -> None:
        if source == target:
            return
        for edge in self.edges:
            if edge.source == source and edge.target == target and edge.type == type_:
                return
        self.edges.append(Edge(source=source, target=target, type=type_, props=props))

    # ---------------------------------------------------------------- queries
    def neighbors(
        self, node_id: str, edge_type: EdgeType | None = None, direction: str = "both"
    ) -> list[tuple[Edge, Node]]:
        out: list[tuple[Edge, Node]] = []
        for edge in self.edges:
            if edge_type is not None and edge.type != edge_type:
                continue
            if direction in ("out", "both") and edge.source == node_id:
                out.append((edge, self.nodes[edge.target]))
            elif direction in ("in", "both") and edge.target == node_id:
                out.append((edge, self.nodes[edge.source]))
        return out

    def find(self, text: str, type_: NodeType | None = None, limit: int = 20) -> list[Node]:
        needle = text.lower()
        hits = [
            n
            for n in self.nodes.values()
            if (type_ is None or n.type == type_) and (needle in n.label.lower() or needle in n.id)
        ]
        return hits[:limit]

    def subgraph(self, node_id: str, depth: int = 1) -> KnowledgeGraph:
        keep = {node_id}
        frontier = {node_id}
        for _ in range(depth):
            nxt: set[str] = set()
            for edge in self.edges:
                if edge.source in frontier:
                    nxt.add(edge.target)
                if edge.target in frontier:
                    nxt.add(edge.source)
            frontier = nxt - keep
            keep |= nxt
        return KnowledgeGraph(
            nodes={k: v for k, v in self.nodes.items() if k in keep},
            edges=[e for e in self.edges if e.source in keep and e.target in keep],
        )

    def conflicts(self) -> list[Conflict]:
        out: list[Conflict] = []
        seen: set[tuple[str, str]] = set()
        for edge in self.edges:
            if edge.type != EdgeType.CONFLICTS_WITH:
                continue
            pair = tuple(sorted((edge.source, edge.target)))
            if pair in seen:
                continue
            seen.add(pair)  # type: ignore[arg-type]
            a, b = self.nodes[edge.source], self.nodes[edge.target]
            out.append(
                Conflict(
                    field=SpecField(a.props["field"]),
                    scope=a.props.get("scope"),
                    values=[a.label, b.label],
                    requirement_ids=[a.id, b.id],
                    message=str(edge.props.get("reason", "")),
                )
            )
        return out

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            counts[node.type.value] += 1
        counts["edges"] = len(self.edges)
        return dict(counts)

    # ---------------------------------------------------------------- exports
    def to_node_link(self) -> dict[str, Any]:
        return {
            "nodes": [n.model_dump(mode="json") for n in self.nodes.values()],
            "links": [e.model_dump(mode="json") for e in self.edges],
        }

    def to_cypher(self) -> str:
        """Cypher statements to load the graph into Neo4j or Memgraph."""
        lines = []
        for node in self.nodes.values():
            props = {"id": node.id, "label": node.label, **_flat(node.props)}
            lines.append(
                f"MERGE (n:{node.type.value} {{id: {json.dumps(node.id)}}}) SET n += {_cypher_map(props)};"
            )
        for edge in self.edges:
            lines.append(
                f"MATCH (a {{id: {json.dumps(edge.source)}}}), (b {{id: {json.dumps(edge.target)}}}) "
                f"MERGE (a)-[r:{edge.type.value}]->(b) SET r += {_cypher_map(_flat(edge.props))};"
            )
        return "\n".join(lines)


def _flat(props: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v if isinstance(v, str | int | float | bool) else json.dumps(v)
        for k, v in props.items()
        if v is not None
    }


def _cypher_map(props: dict[str, Any]) -> str:
    return (
        "{"
        + ", ".join(f"`{k}`: {json.dumps(v, ensure_ascii=False)}" for k, v in props.items())
        + "}"
    )


# ------------------------------------------------------------------------ builder
def build_graph(sheet: SpecSheet, chunks: list[Chunk]) -> KnowledgeGraph:
    g = KnowledgeGraph()
    doc_id = g.add_node(f"doc:{sheet.document_id}", NodeType.DOCUMENT, sheet.filename)
    for category in Category:
        g.add_node(f"topic:{category.value}", NodeType.TOPIC, category.value.replace("_", " "))

    section_ids: dict[tuple[str | None, str], str] = {}  # (lot, article number) -> node id
    chunk_section: dict[str, str] = {}
    for chunk in chunks:
        parent = doc_id
        if chunk.lot:
            parent = g.add_node(f"lot:{_slug(chunk.lot)}", NodeType.LOT, chunk.lot)
            g.add_edge(doc_id, parent, EdgeType.CONTAINS)
        for label in chunk.section_path:
            if label == chunk.lot:
                continue
            number = label.split(" ", 1)[0] if label[:1].isdigit() else None
            sid = g.add_node(
                f"sec:{_slug(chunk.lot or '')}:{_slug(label)}",
                NodeType.SECTION,
                label,
                number=number,
            )
            g.add_edge(parent, sid, EdgeType.CONTAINS)
            if number:
                section_ids[(chunk.lot, number)] = sid
            parent = sid
        pid = g.add_node(
            f"chunk:{chunk.id}",
            NodeType.PASSAGE,
            chunk.locator() or chunk.id,
            chunk_id=chunk.id,
            page=chunk.page_start,
            text=chunk.text[:500],
        )
        g.add_edge(parent, pid, EdgeType.CONTAINS)
        chunk_section[chunk.id] = parent

    # cross-references between articles
    for chunk in chunks:
        for match in _CROSS_REF.finditer(chunk.text):
            target = section_ids.get((chunk.lot, match.group(1)))
            if target:
                g.add_edge(chunk_section[chunk.id], target, EdgeType.REFERS_TO, text=match.group(0))

    for i, req in enumerate(sheet.requirements):
        rid = g.add_node(
            f"req:{i}",
            NodeType.REQUIREMENT,
            f"{req.field.value}: {req.value}",
            field=req.field.value,
            value=req.value,
            scope=req.scope,
            status=req.status.value,
            confidence=req.confidence,
            numeric_value=req.numeric_value,
            comparator=req.comparator,
        )
        g.add_edge(rid, f"topic:{req.category.value}", EdgeType.ABOUT)
        if req.citation:
            g.add_edge(
                f"chunk:{req.citation.chunk_id}", rid, EdgeType.STATES, quote=req.citation.quote
            )
            section = chunk_section.get(req.citation.chunk_id)
            if section and section != doc_id:
                g.add_edge(rid, section, EdgeType.APPLIES_TO)
        _link_entities(g, req, rid, chunk_section)

    _detect_conflicts(g, sheet.requirements)
    return g


def _link_entities(
    g: KnowledgeGraph, req: Requirement, rid: str, chunk_section: dict[str, str]
) -> None:
    source = f"chunk:{req.citation.chunk_id}" if req.citation else rid
    if req.field == SpecField.STANDARDS:
        info = lookup(req.value)
        sid = g.add_node(
            f"std:{standard_key(req.value)}",
            NodeType.STANDARD,
            req.value,
            title=info.title if info else None,
        )
        g.add_edge(source, sid, EdgeType.CITES)
        for category in info.categories if info else ():
            g.add_edge(sid, f"topic:{category.value}", EdgeType.GOVERNS)
    elif req.field == SpecField.CERTIFICATIONS:
        cid = g.add_node(f"cert:{_slug(req.value)}", NodeType.CERTIFICATION, req.value)
        g.add_edge(source, cid, EdgeType.REQUIRES)
    elif req.field == SpecField.FRAME_MATERIAL and req.citation:
        mid = g.add_node(f"mat:{_slug(req.value)}", NodeType.MATERIAL, req.value)
        section = chunk_section.get(req.citation.chunk_id)
        if section:
            g.add_edge(section, mid, EdgeType.USES)


SINGLE_VALUE_FIELDS = {
    SpecField.UW,
    SpecField.UG,
    SpecField.UJN,
    SpecField.SW,
    SpecField.TLW,
    SpecField.AEV,
}


def _detect_conflicts(g: KnowledgeGraph, requirements: list[Requirement]) -> None:
    """Flag one field with two different values for the same scope."""
    groups: dict[tuple[SpecField, str], list[int]] = defaultdict(list)
    for i, req in enumerate(requirements):
        if req.field in SINGLE_VALUE_FIELDS and req.status == RequirementStatus.VERIFIED:
            groups[(req.field, (req.scope or "").lower())].append(i)
    for (field, _scope), indices in groups.items():
        for a_pos, a in enumerate(indices):
            for b in indices[a_pos + 1 :]:
                ra, rb = requirements[a], requirements[b]
                va = ra.numeric_value if ra.numeric_value is not None else ra.value
                vb = rb.numeric_value if rb.numeric_value is not None else rb.value
                if va != vb:
                    g.add_edge(
                        f"req:{a}",
                        f"req:{b}",
                        EdgeType.CONFLICTS_WITH,
                        reason=f"{field.value} has two values for the same scope: {ra.value} / {rb.value}",
                    )
