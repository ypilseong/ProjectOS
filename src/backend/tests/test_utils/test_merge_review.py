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
    # "Scikit learn" (space) scored ~0.917 under the old 0.80 threshold but falls
    # just below the new strict 0.93 (both normalize to "scikitlearn", so containment
    # also doesn't trigger).  "Scikitlearn" (no separator) gives similarity 22/23
    # ≈ 0.957 which qualifies under the strict threshold and is a realistic variant.
    g.add_node(
        "Skill:Scikitlearn", type="Skill", name="Scikitlearn", source_files=[]
    )

    candidates = collect_merge_candidates(g)

    assert len(candidates) == 1
    aliases = set(candidates[0]["aliases"])
    # Both surface forms plus any prior aliases are surfaced for the reviewer.
    assert {"Scikit-learn", "Scikitlearn", "sklearn"} <= aliases


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


def test_denylist_excludes_pair():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])

    denylist = {frozenset({"Skill:TensorFlow", "Skill:Tensorflow"})}
    candidates = collect_merge_candidates(g, denylist=denylist)

    assert candidates == []


def test_denylist_none_keeps_default_behavior():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])

    assert len(collect_merge_candidates(g, denylist=None)) == 1


def test_denylist_only_filters_listed_pair():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])
    g.add_node("Skill:PyTorch", type="Skill", name="PyTorch", source_files=[])
    g.add_node("Skill:Pytorch", type="Skill", name="Pytorch", source_files=[])

    denylist = {frozenset({"Skill:TensorFlow", "Skill:Tensorflow"})}
    candidates = collect_merge_candidates(g, denylist=denylist)

    pairs = {frozenset({c["keep_id"], c["candidate_id"]}) for c in candidates}
    assert frozenset({"Skill:TensorFlow", "Skill:Tensorflow"}) not in pairs
    assert frozenset({"Skill:PyTorch", "Skill:Pytorch"}) in pairs


# ---------------------------------------------------------------------------
# False-positive guard tests (Task 7)
# ---------------------------------------------------------------------------

def _pairs(candidates):
    return {frozenset({c["keep_id"], c["candidate_id"]}) for c in candidates}


def test_short_name_pairs_require_acronym_match():
    g = nx.DiGraph()
    g.add_node("Skill:AI", type="Skill", name="AI")
    g.add_node("Skill:AMI", type="Skill", name="AMI")
    assert collect_merge_candidates(g) == []


def test_single_char_variant_metrics_not_candidates():
    g = nx.DiGraph()
    g.add_node("Skill:cpWER", type="Skill", name="cpWER")
    g.add_node("Skill:cpCER", type="Skill", name="cpCER")
    assert collect_merge_candidates(g) == []


def test_similar_but_semantically_distinct_words_not_candidates():
    g = nx.DiGraph()
    g.add_node("Skill:simulation", type="Skill", name="simulation")
    g.add_node("Skill:estimation", type="Skill", name="estimation")
    assert collect_merge_candidates(g) == []


def test_containment_pairs_still_surface():
    g = nx.DiGraph()
    g.add_node("Skill:SOT fine-tuning", type="Skill", name="SOT fine-tuning")
    g.add_node("Skill:Fine-Tuning", type="Skill", name="Fine-Tuning")
    g.add_node(
        "Achievement:2024.08 Semester High Honors",
        type="Achievement", name="2024.08 Semester High Honors",
    )
    g.add_node(
        "Achievement:Semester High Honors",
        type="Achievement", name="Semester High Honors",
    )
    pairs = _pairs(collect_merge_candidates(g))
    assert frozenset({"Skill:SOT fine-tuning", "Skill:Fine-Tuning"}) in pairs
    assert frozenset({
        "Achievement:2024.08 Semester High Honors",
        "Achievement:Semester High Honors",
    }) in pairs


def test_different_urls_not_candidates():
    g = nx.DiGraph()
    g.add_node(
        "Publication:https://arxiv.org/html/2603.02128v1",
        type="Publication", name="https://arxiv.org/html/2603.02128v1",
    )
    g.add_node(
        "Publication:https://arxiv.org/html/2602.19623v1",
        type="Publication", name="https://arxiv.org/html/2602.19623v1",
    )
    assert collect_merge_candidates(g) == []
