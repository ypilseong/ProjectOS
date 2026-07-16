#!/usr/bin/env python3
"""Stdio MCP bridge for Claude Desktop.

Claude Desktop launches local MCP servers as subprocesses that exchange one
newline-delimited JSON-RPC message per stdin/stdout line. This bridge forwards
those messages to the ProjectOS HTTP MCP endpoint.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
import sys
import urllib.error
import urllib.request
from typing import Any, Callable


DEFAULT_MCP_URL = "http://127.0.0.1:14006/mcp"
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_TEXT_LIMIT = 1200
_LARGE_PAYLOAD_KEYS = {"content_base64", "content_text", "body", "raw", "bytes"}


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _full_payloads_enabled() -> bool:
    return os.environ.get("PROJECTOS_MCP_LOG_FULL_PAYLOADS", "").lower() in {"1", "true", "yes", "on"}


def _compact(value: Any, *, depth: int = 0) -> Any:
    if _full_payloads_enabled():
        return value
    if depth > 6:
        return "<max depth reached>"
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in _LARGE_PAYLOAD_KEYS and isinstance(item, str):
                compacted[key] = {"omitted": True, "chars": len(item), "preview": item[:160]}
            else:
                compacted[key] = _compact(item, depth=depth + 1)
        return compacted
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str) and len(value) > _TEXT_LIMIT:
        return {"truncated": True, "chars": len(value), "preview": value[:_TEXT_LIMIT]}
    return value


def _extract_project_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    params = payload.get("params")
    if isinstance(params, dict):
        args = params.get("arguments")
        if isinstance(args, dict) and args.get("project_id"):
            return str(args["project_id"])
    result = payload.get("result")
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("project_id"):
            return str(structured["project_id"])
    return None


def _record_stdio_exchange(direction: str, payload: dict[str, Any] | None, *, log_dir: Path | None) -> None:
    if log_dir is None:
        return
    try:
        params = payload.get("params") if isinstance(payload, dict) else None
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "stdio",
            "direction": direction,
            "project_id": _extract_project_id(payload),
            "request_id": payload.get("id") if isinstance(payload, dict) else None,
            "method": payload.get("method") if isinstance(payload, dict) else None,
            "tool": params.get("name") if isinstance(params, dict) else None,
            "payload": _compact(payload),
        }
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "mcp-stdio.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        return


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
    log_dir: Path | None = None,
    sender: Callable[[str, dict[str, Any], float], dict[str, Any] | None] = post_json,
) -> dict[str, Any] | None:
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        response = error_response(None, -32700, f"Parse error: {exc.msg}")
        _record_stdio_exchange("response", response, log_dir=log_dir)
        return response

    request_id = message.get("id")
    _record_stdio_exchange("request", message, log_dir=log_dir)
    try:
        response = sender(url, message, timeout)
        _record_stdio_exchange("response", response, log_dir=log_dir)
        return response
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        response = error_response(
            request_id,
            -32000,
            f"ProjectOS MCP backend is not reachable at {url}: {reason}",
        )
        _record_stdio_exchange("response", response, log_dir=log_dir)
        return response
    except Exception as exc:
        response = error_response(request_id, -32000, str(exc))
        _record_stdio_exchange("response", response, log_dir=log_dir)
        return response


def main() -> int:
    url = os.environ.get("PROJECTOS_MCP_URL", DEFAULT_MCP_URL)
    timeout = float(os.environ.get("PROJECTOS_MCP_TIMEOUT", "120"))
    log_dir = Path(os.environ.get("PROJECTOS_MCP_LOG_DIR", str(DEFAULT_LOG_DIR)))
    _log(f"ProjectOS MCP stdio bridge forwarding to {url}")
    _log(f"ProjectOS MCP stdio logs: {log_dir / 'mcp-stdio.jsonl'}")

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        response = handle_line(line, url=url, timeout=timeout, log_dir=log_dir)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
