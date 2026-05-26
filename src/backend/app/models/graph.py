from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    source_file: str
    file_type: str          # "cv" | "project" | "publication" | "note"
    page_num: Optional[int]
    char_offset: int


@dataclass
class EntityTypeDef:
    name: str
    description: str
    examples: list = field(default_factory=list)


@dataclass
class EdgeTypeDef:
    name: str
    description: str
    source_types: list = field(default_factory=list)
    target_types: list = field(default_factory=list)


@dataclass
class Ontology:
    entity_types: list
    edge_types: list
    analysis_summary: str


@dataclass
class CareerProfile:
    name: str
    expertise: list
    skills: list
    projects: list
    organizations: list
    publications: list
    achievements: list
    persona_summary: str
    timeline: list


@dataclass
class GraphStats:
    total_nodes: int
    total_edges: int
    nodes_by_type: dict
    edges_by_type: dict
