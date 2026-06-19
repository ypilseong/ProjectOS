import networkx as nx

from app.utils.merge_review import collect_merge_candidates


def test_collects_high_similarity_same_type_pair():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=["a.pdf"])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=["b.pdf"])

    candidates = collect_merge_candidates(g)

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand["type"] == "Skill"
    assert {cand["keep_id"], cand["candidate_id"]} == {"Skill:TensorFlow", "Skill:Tensorflow"}
    assert 0.0 < cand["confidence"] <= 1.0


def test_does_not_mutate_graph():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])

    before = set(g.nodes)
    collect_merge_candidates(g)

    # Candidate collection is review-only; it must never merge or drop nodes.
    assert set(g.nodes) == before


def test_skips_different_types():
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", source_files=[])
    g.add_node("Project:Python", type="Project", name="Python", source_files=[])

    assert collect_merge_candidates(g) == []


def test_ignores_low_similarity_pairs():
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", source_files=[])
    g.add_node("Skill:Rust", type="Skill", name="Rust", source_files=[])

    assert collect_merge_candidates(g) == []


def test_candidate_includes_aliases():
    g = nx.DiGraph()
    g.add_node(
        "Skill:Scikit-learn",
        type="Skill",
        name="Scikit-learn",
        source_files=[],
        aliases=["sklearn"],
    )
    g.add_node(
        "Skill:Scikit learn", type="Skill", name="Scikit learn", source_files=[]
    )

    candidates = collect_merge_candidates(g)

    assert len(candidates) == 1
    aliases = set(candidates[0]["aliases"])
    # Both surface forms plus any prior aliases are surfaced for the reviewer.
    assert {"Scikit-learn", "Scikit learn", "sklearn"} <= aliases


def test_skips_meta_nodes():
    g = nx.DiGraph()
    g.add_node("Category:Skills", type="Category", name="Skills")
    g.add_node("Category:Skill", type="Category", name="Skill")

    assert collect_merge_candidates(g) == []


def test_acronym_variants_are_candidates():
    g = nx.DiGraph()
    g.add_node(
        "Skill:NLP",
        type="Skill",
        name="NLP",
        source_files=[],
    )
    g.add_node(
        "Skill:Natural Language Processing",
        type="Skill",
        name="Natural Language Processing",
        source_files=[],
    )

    candidates = collect_merge_candidates(g)

    # Acronym/full-form pairs are plausible duplicates even at low string similarity.
    assert len(candidates) == 1
    assert candidates[0]["confidence"] >= 0.99


def test_sorted_by_confidence_desc():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])
    g.add_node("Skill:Pytorch", type="Skill", name="Pytorch", source_files=[])
    g.add_node("Skill:PyTorchh", type="Skill", name="PyTorchh", source_files=[])

    candidates = collect_merge_candidates(g)

    confidences = [c["confidence"] for c in candidates]
    assert confidences == sorted(confidences, reverse=True)
