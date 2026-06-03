from datetime import date, datetime

from app.config import config
from app.services.digest import should_run


def test_config_digest_defaults():
    assert config.DIGEST_ENABLED is False
    assert config.DIGEST_HOUR == 7
    assert config.DIGEST_POLL_SECONDS == 300


def test_should_run_false_when_already_ran_today():
    now = datetime(2026, 6, 3, 9, 0)
    assert should_run(now, date(2026, 6, 3), hour=7) is False


def test_should_run_true_when_new_day_and_hour_passed():
    now = datetime(2026, 6, 3, 9, 0)
    assert should_run(now, date(2026, 6, 2), hour=7) is True


def test_should_run_true_when_never_ran_and_hour_passed():
    now = datetime(2026, 6, 3, 7, 0)
    assert should_run(now, None, hour=7) is True


def test_should_run_false_before_hour():
    now = datetime(2026, 6, 3, 6, 59)
    assert should_run(now, None, hour=7) is False


from app.services.digest import _reinforcement_suggestions


def _health(isolated=None, missing_source=None, without_pages=None):
    return {
        "isolated_nodes": isolated or [],
        "wiki_graph_lint": {
            "missing_source_nodes": missing_source or [],
            "graph_nodes_without_pages": without_pages or [],
        },
    }


def test_suggestions_empty_when_clean():
    assert _reinforcement_suggestions(_health(), {}) == []


def test_suggestions_flag_isolated_nodes():
    health = _health(isolated=[{"name": "Foo", "type": "Concept"}])
    out = _reinforcement_suggestions(health, {})
    assert any("고립 노드 1개" in s and "Foo" in s for s in out)


def test_suggestions_flag_missing_source_and_pages():
    health = _health(
        missing_source=[{"name": "Bar"}],
        without_pages=[{"name": "Baz"}],
    )
    out = _reinforcement_suggestions(health, {})
    assert any("provenance" in s for s in out)
    assert any("vault 노트" in s for s in out)


def test_suggestions_include_analysis_suggestions():
    analysis = {"issues": [{"suggestion": "정량적 성과를 추가하세요."}]}
    out = _reinforcement_suggestions(_health(), analysis)
    assert "정량적 성과를 추가하세요." in out
