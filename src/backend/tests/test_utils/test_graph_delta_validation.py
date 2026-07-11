import networkx as nx

from app.utils.graph_delta_validation import ALLOWED_RELATIONS, validate_graph_enhancements


def _graph():
    g = nx.DiGraph()
    g.add_node("Skill:Cross-Impact Balance", type="Skill", name="Cross-Impact Balance")
    g.add_node("Person:양필성", type="Person", name="양필성")
    return g


def test_duplicate_node_gets_annotated_not_dropped():
    enhancements = {
        "nodes": [{"type": "Skill", "name": "Cross-Impact Balance (CIB)", "description": "d", "evidence": "e"}],
        "edges": [],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert result["nodes"][0]["duplicate_of"] == "Skill:Cross-Impact Balance"


def test_edge_endpoint_remapped_to_existing_duplicate():
    enhancements = {
        "nodes": [{"type": "Skill", "name": "Cross-Impact Balance (CIB)", "description": "d", "evidence": "e"}],
        "edges": [{
            "source_type": "Person", "source_name": "양필성",
            "target_type": "Skill", "target_name": "Cross-Impact Balance (CIB)",
            "relation": "USES_SKILL", "evidence": "e", "confidence": 0.7,
        }],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert result["edges"][0]["target_name"] == "Cross-Impact Balance"


def test_off_schema_relation_normalized_to_related_to():
    enhancements = {
        "nodes": [],
        "edges": [{
            "source_type": "Person", "source_name": "양필성",
            "target_type": "Skill", "target_name": "Cross-Impact Balance",
            "relation": "TARGET_COMPETENCE", "evidence": "e", "confidence": 0.7,
        }],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert result["edges"][0]["relation"] == "RELATED_TO"
    assert result["edges"][0]["relation_raw"] == "TARGET_COMPETENCE"


def test_new_node_and_valid_relation_pass_through():
    enhancements = {
        "nodes": [{"type": "Skill", "name": "Monte Carlo Simulation", "description": "d", "evidence": "e"}],
        "edges": [{
            "source_type": "Person", "source_name": "양필성",
            "target_type": "Skill", "target_name": "Monte Carlo Simulation",
            "relation": "USES_SKILL", "evidence": "e", "confidence": 0.7,
        }],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert "duplicate_of" not in result["nodes"][0]
    assert result["edges"][0]["relation"] == "USES_SKILL"
    assert "relation_raw" not in result["edges"][0]


def test_allowed_relations_contains_fixed_vocabulary():
    assert {"WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED", "COLLABORATED_WITH",
            "ACHIEVED", "PARTICIPATED_IN", "PUBLISHED_AT", "MENTORED_BY", "LED_BY"} <= ALLOWED_RELATIONS
