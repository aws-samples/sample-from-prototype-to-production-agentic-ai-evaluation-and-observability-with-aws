"""
AgentCore Gateway Lambda target for the Singapore Weather Agent.

The Gateway exposes the four NEA tools over MCP. On each call it puts the tool name in
context.client_context.custom["bedrockAgentCoreToolName"] (prefixed "<target>___") and the
tool arguments in the event. nea_data.py is packaged alongside this file.
"""

from __future__ import annotations

import json
from typing import Any

import nea_data

DELIMITER = "___"


def _tool_name(event: dict[str, Any], context: Any) -> str | None:
    name = None
    cc = getattr(context, "client_context", None)
    if cc is not None:
        name = (getattr(cc, "custom", None) or {}).get("bedrockAgentCoreToolName")
    name = name or event.get("tool_name")  # local testing
    if name and DELIMITER in name:
        name = name.split(DELIMITER, 1)[1]
    return name


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    name = _tool_name(event, context)
    fn = nea_data.TOOL_IMPLS.get(name or "")
    if fn is None:
        return {"error": f"Unknown tool: {name}", "available_tools": sorted(nea_data.TOOL_IMPLS)}

    args = {k: v for k, v in (event or {}).items() if not k.startswith("__") and k != "tool_name"}
    allowed = {p for s in nea_data.TOOL_SCHEMAS if s["name"] == name for p in s["inputSchema"]["properties"]}
    args = {k: str(v) for k, v in args.items() if k in allowed}  # drop unexpected args

    try:
        return fn(**args)
    except Exception as e:
        print(json.dumps({"tool": name, "error": f"{type(e).__name__}: {e}"}))
        return {"error": f"NEA data unavailable: {type(e).__name__}"}
