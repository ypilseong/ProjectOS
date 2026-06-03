import inspect

from app.api.graph import _run_graph


def test_run_graph_accepts_trigger_param():
    sig = inspect.signature(_run_graph)
    assert "trigger" in sig.parameters
    assert sig.parameters["trigger"].default == "manual"


def test_run_graph_source_records_trigger_in_trace():
    src = inspect.getsource(_run_graph)
    assert "trigger=trigger" in src
