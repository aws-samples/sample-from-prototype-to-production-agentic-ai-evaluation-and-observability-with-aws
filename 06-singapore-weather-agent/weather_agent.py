#!/usr/bin/env python3
"""
Singapore Weather Agent (Strands Agents + Amazon Bedrock).

Answers questions about weather forecasts and haze/air quality across Singapore using
NEA's official real-time data. The tools run in-process (local) or behind an AgentCore
Gateway (MCP over SigV4 -> Lambda), and a Bedrock Guardrail can be attached to the model.

Usage:
    python weather_agent.py "What's the weather and haze like across Singapore?"
    python weather_agent.py --gateway --guardrail "Is it hazy in the west?"
    python weather_agent.py                 # interactive
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from strands import Agent, tool
from strands.models import BedrockModel

import nea_data

HERE = Path(__file__).resolve().parent
MODEL_ID = os.environ.get("WEATHER_AGENT_MODEL_ID", "global.anthropic.claude-sonnet-5")
DEFAULT_PROMPT = "system_v3"
DEFAULT_VARIANT = {"prompt": DEFAULT_PROMPT, "tools": "local", "guardrail": False}
TOOL_DELIMITER = "___"  # Gateway prefixes tool names with "<target>___"


def load_prompt(name: str = DEFAULT_PROMPT) -> str:
    return (HERE / "config" / "prompts" / f"{name}.md").read_text().strip()


def load_infra_state() -> dict[str, Any]:
    path = HERE / "infra_state.json"
    if not path.exists():
        raise RuntimeError("infra_state.json not found. Run `python infra.py deploy` first.")
    return json.loads(path.read_text())


def base_tool_name(name: str) -> str:
    return name.split(TOOL_DELIMITER, 1)[-1]


# --------------------------------------------------------------------------- #
# Local tools (same implementations the Gateway Lambda runs)
# --------------------------------------------------------------------------- #
def _run(name: str, **kwargs) -> str:
    try:
        return json.dumps(nea_data.TOOL_IMPLS[name](**kwargs), ensure_ascii=False)
    except Exception as e:  # surface failures to the model instead of crashing
        return json.dumps({"error": f"NEA data unavailable: {e}"})


@tool
def get_two_hour_forecast(area: str = "") -> str:
    """Get NEA's 2-hour weather nowcast for Singapore's ~47 towns/areas.

    Args:
        area: Optional town/area name (e.g. "Tampines", "Jurong West", "Changi").
              Leave empty to get all areas grouped by forecast condition.
    """
    return _run("get_two_hour_forecast", area=area)


@tool
def get_24_hour_forecast() -> str:
    """Get NEA's 24-hour forecast for Singapore: overall conditions, temperature range,
    relative humidity, wind, and per-region (north/south/east/west/central) forecasts
    for each time period (e.g. afternoon, night, morning)."""
    return _run("get_24_hour_forecast")


@tool
def get_four_day_outlook() -> str:
    """Get NEA's 4-day weather outlook for Singapore: daily forecast, temperature,
    humidity and wind for each of the next four days."""
    return _run("get_four_day_outlook")


@tool
def get_haze_conditions(region: str = "") -> str:
    """Get current haze / air quality across Singapore: 24-hr PSI with NEA descriptor,
    1-hr PM2.5 with NEA band per region, and NEA's health advisory.

    Args:
        region: Optional region: north, south, east, west or central. Empty = all regions.
    """
    return _run("get_haze_conditions", region=region)


LOCAL_TOOLS = [get_two_hour_forecast, get_24_hour_forecast, get_four_day_outlook, get_haze_conditions]


# --------------------------------------------------------------------------- #
# AgentCore Gateway (AWS_IAM authorizer -> SigV4-signed MCP over streamable HTTP)
# --------------------------------------------------------------------------- #
def gateway_mcp_client(gateway_url: str, region: str):
    import boto3
    import httpx
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    credentials = boto3.Session(region_name=region).get_credentials()

    class SigV4HTTPXAuth(httpx.Auth):
        requires_request_body = True

        def auth_flow(self, request: httpx.Request):
            headers = {k: v for k, v in request.headers.items() if k.lower() != "connection"}
            aws_req = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=headers)
            SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", region).add_auth(aws_req)
            request.headers.update(dict(aws_req.headers))
            yield request

    return MCPClient(lambda: streamablehttp_client(url=gateway_url, auth=SigV4HTTPXAuth()))


# --------------------------------------------------------------------------- #
# Agent factory
# --------------------------------------------------------------------------- #
def build_model(guardrail: bool, *, model_id: str = MODEL_ID, max_tokens: int = 2000) -> BedrockModel:
    kwargs: dict[str, Any] = {"model_id": model_id, "max_tokens": max_tokens}
    if guardrail:
        state = load_infra_state()
        cfg = json.loads((HERE / "config" / "guardrail.json").read_text())
        kwargs.update(
            guardrail_id=state["guardrail_id"],
            guardrail_version=state["guardrail_version"],
            guardrail_trace="enabled",
            guardrail_redact_output=True,
            guardrail_redact_output_message=cfg["blockedOutputsMessaging"],
        )
    return BedrockModel(**kwargs)


@contextmanager
def open_agent(variant: dict[str, Any] | None = None, *, callback_handler=None) -> Iterator[Agent]:
    """Yield an agent configured by `variant` ({prompt, tools: local|gateway, guardrail})."""
    v = {**DEFAULT_VARIANT, **(variant or {})}
    common = dict(
        name="SingaporeWeatherAgent",
        model=build_model(v["guardrail"]),
        system_prompt=load_prompt(v["prompt"]),
        callback_handler=callback_handler,
    )
    if v["tools"] == "gateway":
        state = load_infra_state()
        client = gateway_mcp_client(state["gateway_url"], state["region"])
        with client:
            yield Agent(tools=client.list_tools_sync(), **common)
    else:
        yield Agent(tools=LOCAL_TOOLS, **common)


def main() -> None:
    from strands.handlers.callback_handler import PrintingCallbackHandler

    ap = argparse.ArgumentParser(description="Singapore Weather Agent")
    ap.add_argument("question", nargs="*")
    ap.add_argument("--gateway", action="store_true", help="Use tools via AgentCore Gateway (needs infra.py deploy)")
    ap.add_argument("--guardrail", action="store_true", help="Attach the Bedrock Guardrail (needs infra.py deploy)")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt version in config/prompts/")
    args = ap.parse_args()

    variant = {"prompt": args.prompt, "tools": "gateway" if args.gateway else "local", "guardrail": args.guardrail}
    with open_agent(variant, callback_handler=PrintingCallbackHandler()) as agent:
        if args.question:
            agent(" ".join(args.question))
            print()
            return
        print("Singapore Weather Agent. Type 'exit' to quit.")
        while (q := input("\n> ").strip()).lower() not in {"exit", "quit"}:
            if q:
                agent(q)
                print()


if __name__ == "__main__":
    main()
