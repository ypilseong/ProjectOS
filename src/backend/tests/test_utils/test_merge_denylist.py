from app.config import config
from app.utils.merge_denylist import add_denied_pair, load_denylist


def test_load_missing_returns_empty_set():
    assert load_denylist("no_such_project") == set()


def test_add_then_load_roundtrip():
    add_denied_pair("p1", "Skill:A", "Skill:B")

    dl = load_denylist("p1")

    assert dl == {frozenset({"Skill:A", "Skill:B"})}


def test_add_is_order_independent():
    add_denied_pair("p2", "Skill:B", "Skill:A")

    dl = load_denylist("p2")

    assert frozenset({"Skill:A", "Skill:B"}) in dl


def test_add_duplicate_pair_is_idempotent():
    add_denied_pair("p3", "Skill:A", "Skill:B")
    add_denied_pair("p3", "Skill:B", "Skill:A")

    assert load_denylist("p3") == {frozenset({"Skill:A", "Skill:B"})}


def test_add_multiple_distinct_pairs():
    add_denied_pair("p4", "Skill:A", "Skill:B")
    add_denied_pair("p4", "Skill:C", "Skill:D")

    dl = load_denylist("p4")

    assert dl == {
        frozenset({"Skill:A", "Skill:B"}),
        frozenset({"Skill:C", "Skill:D"}),
    }
