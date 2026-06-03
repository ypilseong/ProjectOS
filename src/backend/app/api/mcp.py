from fastapi import APIRouter
from fastapi.responses import Response

from app.mcp_tools import call_mcp_tool, list_mcp_tools

router = APIRouter()

PROTOCOL_VERSION = "2025-11-25"


def _response(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


@router.get("/tools")
async def list_tools_http():
    return {"tools": list_mcp_tools()}


@router.post("")
async def mcp_json_rpc(message: dict):
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if request_id is None:
        return Response(status_code=202)

    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "projectos", "version": "0.1.0"},
            },
        )

    if method == "tools/list":
        return _response(request_id, {"tools": list_mcp_tools()})

    if method == "tools/call":
        name = params.get("name")
        if not name:
            return _error(request_id, -32602, "params.name is required")
        result = await call_mcp_tool(name, params.get("arguments") or {})
        return _response(request_id, result)

    return _error(request_id, -32601, f"Method not found: {method}")
