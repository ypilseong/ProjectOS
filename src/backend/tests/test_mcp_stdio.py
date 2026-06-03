import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "projectos_mcp_stdio.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("projectos_mcp_stdio", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_handle_line_forwards_message():
    bridge = _load_bridge()
    seen = {}

    def sender(url, message, timeout):
        seen["url"] = url
        seen["message"] = message
        seen["timeout"] = timeout
        return {"jsonrpc": "2.0", "id": message["id"], "result": {"ok": True}}

    response = bridge.handle_line(
        '{"jsonrpc":"2.0","id":1,"method":"ping"}',
        url="http://backend/mcp",
        timeout=5,
        sender=sender,
    )

    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    assert seen["url"] == "http://backend/mcp"
    assert seen["message"]["method"] == "ping"
    assert seen["timeout"] == 5


def test_handle_line_returns_parse_error():
    bridge = _load_bridge()
    response = bridge.handle_line(
        "{bad",
        url="http://backend/mcp",
        timeout=5,
        sender=lambda _url, _message, _timeout: None,
    )

    assert response["id"] is None
    assert response["error"]["code"] == -32700


def test_stdio_bridge_reports_unreachable_backend():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input='{"jsonrpc":"2.0","id":7,"method":"ping"}\n',
        text=True,
        capture_output=True,
        env={"PROJECTOS_MCP_URL": "http://127.0.0.1:9/mcp"},
        timeout=5,
    )

    assert proc.returncode == 0
    response = json.loads(proc.stdout.strip())
    assert response["id"] == 7
    assert response["error"]["code"] == -32000
    assert "not reachable" in response["error"]["message"]
    assert "ProjectOS MCP stdio bridge" in proc.stderr
