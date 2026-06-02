from dataclasses import asdict, dataclass

from app.utils.routing import Role


@dataclass
class SkillDescriptor:
    name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    role: str
    cost_profile: str  # "low" | "high"
    execution_mode: str  # "on_demand" | "scheduled" | "continuous"


CATALOG: list[SkillDescriptor] = [
    SkillDescriptor(
        name="parse_documents",
        description="업로드된 PDF/DOCX/TXT를 청크로 분해한다.",
        inputs=["file_paths"],
        outputs=["chunks"],
        role=Role.CHUNK_EXTRACTION,
        cost_profile="low",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="build_ontology",
        description="청크 샘플에서 엔티티/관계 타입 온톨로지를 정의한다.",
        inputs=["chunks"],
        outputs=["ontology"],
        role=Role.ONTOLOGY,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="build_graph",
        description="청크+온톨로지에서 NetworkX 지식 그래프를 구축한다.",
        inputs=["chunks", "ontology"],
        outputs=["graph"],
        role=Role.CHUNK_EXTRACTION,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="query_career_graph",
        description="자연어 질문에 그래프+vault 컨텍스트로 답한다.",
        inputs=["question", "graph"],
        outputs=["answer_stream"],
        role=Role.QUERY,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="run_analysis",
        description="문서의 약점을 분석하고 개선 초안을 생성한다.",
        inputs=["chunks", "graph"],
        outputs=["issues", "improved_draft"],
        role=Role.ANALYSIS,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="simulate_persona",
        description="그래프 노드에서 페르소나 에이전트를 구성해 멀티에이전트 시뮬레이션을 실행한다.",
        inputs=["graph", "chunks", "query"],
        outputs=["persona_specs", "timeline"],
        role=Role.SIMULATION,
        cost_profile="low",
        execution_mode="on_demand",
    ),
]


def catalog_as_dicts() -> list[dict]:
    return [asdict(s) for s in CATALOG]
