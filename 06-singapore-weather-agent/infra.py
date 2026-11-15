#!/usr/bin/env python3
"""
Deploy / inspect / tear down the Weather Agent's AWS resources.

    python infra.py deploy     # Lambda + IAM roles + AgentCore Gateway + target + Bedrock Guardrail (idempotent)
    python infra.py status
    python infra.py smoke      # list tools and call one through the Gateway
    python infra.py destroy

Resource ids are written to infra_state.json (git-ignored). Re-running deploy after
editing config/guardrail.json updates the guardrail and publishes a new version.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "infra_state.json"
GUARDRAIL_FILE = HERE / "config" / "guardrail.json"

PREFIX = "sg-weather"
LAMBDA_NAME = f"{PREFIX}-tools"
LAMBDA_ROLE = f"{PREFIX}-tools-lambda-role"
GATEWAY_ROLE = f"{PREFIX}-gateway-role"
GATEWAY_NAME = f"{PREFIX}-gateway"
TARGET_NAME = "WeatherTools"

session = boto3.Session()
REGION = session.region_name or "us-east-1"
ACCOUNT = session.client("sts").get_caller_identity()["Account"]
iam = session.client("iam")
lam = session.client("lambda", region_name=REGION)
agentcore = session.client("bedrock-agentcore-control", region_name=REGION)
bedrock = session.client("bedrock", region_name=REGION)


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def wait(desc: str, fn, ok: set[str], bad: set[str] = frozenset({"FAILED"}), timeout: int = 300) -> str:
    t0 = time.time()
    while True:
        status = fn()
        if status in ok:
            return status
        if status in bad or time.time() - t0 > timeout:
            raise RuntimeError(f"{desc}: status {status}")
        time.sleep(5)


# --------------------------------------------------------------------------- #
# IAM
# --------------------------------------------------------------------------- #
def ensure_role(name: str, service: str, managed: list[str], inline: dict | None = None) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}},
        }],
    }
    try:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust),
                              Description="Singapore Weather Agent")["Role"]["Arn"]
        print(f"  created role {name}")
        time.sleep(10)  # IAM propagation
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
    for p in managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=p)
    if inline:
        iam.put_role_policy(RoleName=name, PolicyName=f"{name}-inline", PolicyDocument=json.dumps(inline))
    return arn


# --------------------------------------------------------------------------- #
# Lambda
# --------------------------------------------------------------------------- #
def package() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "lambda_tools" / "weather_tools_lambda.py", "weather_tools_lambda.py")
        z.write(HERE / "nea_data.py", "nea_data.py")
    return buf.getvalue()


def ensure_lambda(role_arn: str) -> str:
    code = package()
    cfg = dict(FunctionName=LAMBDA_NAME, Runtime="python3.12", Role=role_arn,
               Handler="weather_tools_lambda.lambda_handler", Timeout=60, MemorySize=256,
               Description="NEA weather + haze tools for the Singapore Weather Agent (AgentCore Gateway target)")
    for attempt in range(6):
        try:
            arn = lam.create_function(Code={"ZipFile": code}, **cfg)["FunctionArn"]
            print(f"  created Lambda {LAMBDA_NAME}")
            break
        except lam.exceptions.ResourceConflictException:
            lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=code)
            lam.get_waiter("function_updated_v2").wait(FunctionName=LAMBDA_NAME)
            cfg.pop("FunctionName")
            lam.update_function_configuration(FunctionName=LAMBDA_NAME, **cfg)
            arn = lam.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"]
            print(f"  updated Lambda {LAMBDA_NAME}")
            break
        except lam.exceptions.InvalidParameterValueException as e:
            if "cannot be assumed" not in str(e) or attempt == 5:
                raise
            time.sleep(10)  # role not yet assumable
    lam.get_waiter("function_updated_v2").wait(FunctionName=LAMBDA_NAME)
    return arn


# --------------------------------------------------------------------------- #
# AgentCore Gateway
# --------------------------------------------------------------------------- #
def ensure_gateway(role_arn: str) -> dict:
    existing = next((g for g in agentcore.list_gateways(maxResults=100)["items"] if g["name"] == GATEWAY_NAME), None)
    if existing:
        gw_id = existing["gatewayId"]
    else:
        gw_id = agentcore.create_gateway(
            name=GATEWAY_NAME, roleArn=role_arn, protocolType="MCP", authorizerType="AWS_IAM",
            description="MCP gateway exposing NEA weather and haze tools", exceptionLevel="DEBUG",
        )["gatewayId"]
        print(f"  created Gateway {gw_id}")
    wait("gateway", lambda: agentcore.get_gateway(gatewayIdentifier=gw_id)["status"], {"READY"})
    gw = agentcore.get_gateway(gatewayIdentifier=gw_id)
    return {"gateway_id": gw_id, "gateway_url": gw["gatewayUrl"], "gateway_arn": gw["gatewayArn"]}


def ensure_target(gw_id: str, lambda_arn: str) -> str:
    from nea_data import TOOL_SCHEMAS

    target_cfg = {"mcp": {"lambda": {"lambdaArn": lambda_arn, "toolSchema": {"inlinePayload": TOOL_SCHEMAS}}}}
    creds = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    existing = next((t for t in agentcore.list_gateway_targets(gatewayIdentifier=gw_id, maxResults=100)["items"]
                     if t["name"] == TARGET_NAME), None)
    if existing:
        tid = existing["targetId"]
        agentcore.update_gateway_target(gatewayIdentifier=gw_id, targetId=tid, name=TARGET_NAME,
                                        targetConfiguration=target_cfg, credentialProviderConfigurations=creds)
        print(f"  updated target {TARGET_NAME}")
    else:
        for attempt in range(12):
            try:
                tid = agentcore.create_gateway_target(gatewayIdentifier=gw_id, name=TARGET_NAME,
                                                      description="NEA weather + haze tools",
                                                      targetConfiguration=target_cfg,
                                                      credentialProviderConfigurations=creds)["targetId"]
                break
            except agentcore.exceptions.ValidationException as e:
                if "lacks permission" not in str(e) or attempt == 11:
                    raise
                print("  waiting for Gateway role permissions to propagate...")
                time.sleep(10)
        print(f"  created target {TARGET_NAME}")
    wait("target", lambda: agentcore.get_gateway_target(gatewayIdentifier=gw_id, targetId=tid)["status"],
         {"READY"}, {"FAILED", "UPDATE_UNSUCCESSFUL"})
    return tid


# --------------------------------------------------------------------------- #
# Bedrock Guardrail
# --------------------------------------------------------------------------- #
def ensure_guardrail(state: dict) -> dict:
    cfg = json.loads(GUARDRAIL_FILE.read_text())
    cfg_version = cfg.pop("guardrail_config_version")
    digest = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]

    existing = next((g for g in bedrock.list_guardrails(maxResults=100)["guardrails"] if g["name"] == cfg["name"]), None)
    if existing:
        gid = existing["id"]
        if state.get("guardrail_digest") == digest and state.get("guardrail_version"):
            return {k: state[k] for k in ["guardrail_id", "guardrail_version", "guardrail_config_version", "guardrail_digest"]}
        bedrock.update_guardrail(guardrailIdentifier=gid, **cfg)
        print(f"  updated guardrail {gid}")
    else:
        gid = bedrock.create_guardrail(**cfg)["guardrailId"]
        print(f"  created guardrail {gid}")
    wait("guardrail", lambda: bedrock.get_guardrail(guardrailIdentifier=gid)["status"], {"READY"})
    version = bedrock.create_guardrail_version(guardrailIdentifier=gid, description=f"{cfg_version} ({digest})")["version"]
    wait("guardrail version", lambda: bedrock.get_guardrail(guardrailIdentifier=gid, guardrailVersion=version)["status"], {"READY"})
    print(f"  published guardrail version {version} ({cfg_version})")
    return {"guardrail_id": gid, "guardrail_version": version, "guardrail_config_version": cfg_version, "guardrail_digest": digest}


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def deploy() -> None:
    state = load_state()
    print(f"Deploying to {ACCOUNT} / {REGION}")
    print("IAM roles...")
    lambda_role = ensure_role(LAMBDA_ROLE, "lambda.amazonaws.com",
                              ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"])
    print("Lambda...")
    lambda_arn = ensure_lambda(lambda_role)
    gw_role = ensure_role(GATEWAY_ROLE, "bedrock-agentcore.amazonaws.com", [], {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": lambda_arn}],
    })
    print("AgentCore Gateway...")
    gw = ensure_gateway(gw_role)
    target_id = ensure_target(gw["gateway_id"], lambda_arn)
    print("Bedrock Guardrail...")
    gr = ensure_guardrail(state)
    state.update(region=REGION, lambda_arn=lambda_arn, target_id=target_id, **gw, **gr)
    save_state(state)
    print(f"\nDone. State written to {STATE_FILE.name}:\n{json.dumps(state, indent=2)}")


def smoke() -> None:
    from weather_agent import gateway_mcp_client

    state = load_state()
    client = gateway_mcp_client(state["gateway_url"], state["region"])
    with client:
        tools = client.list_tools_sync()
        print("Gateway tools:", [t.tool_name for t in tools])
        haze = next(t.tool_name for t in tools if t.tool_name.endswith("get_haze_conditions"))
        r = client.call_tool_sync(tool_use_id="smoke-1", name=haze, arguments={"region": "west"})
        print("call", haze, "->", r["status"], r["content"][0].get("text", "")[:400])


def status() -> None:
    state = load_state()
    if not state:
        print("Nothing deployed (no infra_state.json).")
        return
    print(json.dumps(state, indent=2))
    try:
        print("gateway:", agentcore.get_gateway(gatewayIdentifier=state["gateway_id"])["status"])
        print("target:", agentcore.get_gateway_target(gatewayIdentifier=state["gateway_id"], targetId=state["target_id"])["status"])
        print("guardrail:", bedrock.get_guardrail(guardrailIdentifier=state["guardrail_id"], guardrailVersion=state["guardrail_version"])["status"])
    except ClientError as e:
        print("error:", e)


def destroy() -> None:
    state = load_state()

    def attempt(desc, fn):
        try:
            fn()
            print(f"  deleted {desc}")
        except ClientError as e:
            print(f"  skip {desc}: {e.response['Error']['Code']}")

    if gw_id := state.get("gateway_id"):
        for t in agentcore.list_gateway_targets(gatewayIdentifier=gw_id, maxResults=100).get("items", []):
            attempt(f"target {t['name']}", lambda t=t: agentcore.delete_gateway_target(gatewayIdentifier=gw_id, targetId=t["targetId"]))
        time.sleep(5)
        attempt(f"gateway {gw_id}", lambda: agentcore.delete_gateway(gatewayIdentifier=gw_id))
    attempt(f"Lambda {LAMBDA_NAME}", lambda: lam.delete_function(FunctionName=LAMBDA_NAME))
    if gid := state.get("guardrail_id"):
        attempt(f"guardrail {gid}", lambda: bedrock.delete_guardrail(guardrailIdentifier=gid))
    attempt(f"role {GATEWAY_ROLE}", lambda: (iam.delete_role_policy(RoleName=GATEWAY_ROLE, PolicyName=f"{GATEWAY_ROLE}-inline"),
                                            iam.delete_role(RoleName=GATEWAY_ROLE)))
    attempt(f"role {LAMBDA_ROLE}", lambda: (iam.detach_role_policy(RoleName=LAMBDA_ROLE,
                                            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"),
                                            iam.delete_role(RoleName=LAMBDA_ROLE)))
    STATE_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"deploy": deploy, "status": status, "smoke": smoke, "destroy": destroy}.get(cmd, lambda: sys.exit(__doc__))()
