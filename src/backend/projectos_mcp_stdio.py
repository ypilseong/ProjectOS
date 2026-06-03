#!/usr/bin/env python3
"""Stdio MCP bridge for Claude Desktop.

Claude Desktop launches local MCP servers as subprocesses that exchange one
newline-delimited JSON-RPC message per stdin/stdout line. This bridge forwards
those messages to the ProjectOS HTTP MCP endpoint.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable


DEFAULT_MCP_URL = "http://127.0.0.1:8002/mcp"


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def post_json(url: str, message: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status == 202:
            return None
        raw = response.read()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_line(
    line: str,
    *,
    url: str,
    timeout: float,
    sender: Callable[[str, dict[str, Any], float], dict[str, Any] | None] = post_json,
) -> dict[str, Any] | None:
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        return error_response(None, -32700, f"Parse error: {exc.msg}")

    request_id = message.get("id")
    try:
        return sender(url, message, timeout)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return error_response(
            request_id,
            -32000,
            f"ProjectOS MCP backend is not reachable at {url}: {reason}",
        )
    except Exception as exc:
        return error_response(request_id, -32000, str(exc))


def main() -> int:
    url = os.environ.get("PROJECTOS_MCP_URL", DEFAULT_MCP_URL)
    timeout = float(os.environ.get("PROJECTOS_MCP_TIMEOUT", "120"))
    _log(f"ProjectOS MCP stdio bridge forwarding to {url}")

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        response = handle_line(line, url=url, timeout=timeout)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
