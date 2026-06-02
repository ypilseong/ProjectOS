from app.config import config
from app.utils.trace import record_trace, read_traces


def test_record_and_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    record_trace("proj1", "graph_build", backend="local", nodes=10, edges=12)
    record_trace("proj1", "query", backend="claude_code", cost_usd=0.05)
    traces = read_traces("proj1")
    assert len(traces) == 2
    assert traces[0]["operation"] == "graph_build"
    assert traces[0]["nodes"] == 10
    assert traces[1]["backend"] == "claude_code"
    assert "timestamp" in traces[0]


def test_read_missing_project_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    assert read_traces("nope") == []
