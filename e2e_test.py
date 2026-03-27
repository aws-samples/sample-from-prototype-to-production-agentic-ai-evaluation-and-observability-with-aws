#!/usr/bin/env python3
"""
E2E Verification Script for Ecommerce Agent Workshop
=====================================================
One-shot script to deploy + verify all notebooks end-to-end.
Requires IAM permissions: iam:PassRole, bedrock-agentcore:*, lambda:*, cognito-idp:*, ecr:*, etc.

Run from repo root:
    pip install boto3 strands-agents strands-agents-tools mcp
    python e2e_test.py

Or with uv:
    uv run --with boto3,strands-agents,strands-agents-tools,mcp python e2e_test.py

Reports results to stdout and writes E2E_REPORT.md
"""

import boto3
import json
import os
import sys
import time
import subprocess
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────
REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
os.environ['AWS_DEFAULT_REGION'] = REGION
os.environ['AWS_REGION'] = REGION

WORKSHOP_PREFIX = 'ecommerce-workshop'
REPO_ROOT = Path(__file__).parent.resolve()

# Derived names (must match notebooks)
ECR_REPO_NAME = f"{WORKSHOP_PREFIX}-product-catalog-agent"
RUNTIME_NAME = f"{WORKSHOP_PREFIX.replace('-','_')}_product_catalog_agent"
GATEWAY_NAME = f"{WORKSHOP_PREFIX}-gateway"
COGNITO_POOL_NAME = f"{WORKSHOP_PREFIX}-user-pool"
EVAL_CONFIG_NAME = f"{WORKSHOP_PREFIX.replace('-','_')}_product_catalog_eval"
LAMBDA_PRODUCT_TOOLS = f"{WORKSHOP_PREFIX}-product-tools"
LAMBDA_RBAC = f"{WORKSHOP_PREFIX}-rbac-interceptor"

# IAM role names
RUNTIME_ROLE = f"{WORKSHOP_PREFIX}-runtime-role"
GATEWAY_ROLE = f"{WORKSHOP_PREFIX}-gateway-role"
LAMBDA_ROLE = f"{WORKSHOP_PREFIX}-lambda-role"
EVAL_ROLE = f"{WORKSHOP_PREFIX}-evaluation-role"

# ── Result tracking ────────────────────────────────────────
results = {}

def check(module, name, passed, detail=""):
    key = f"{module}: {name}"
    status = "✅" if passed else "❌"
    results[key] = {"passed": passed, "detail": detail, "module": module}
    print(f"  {status} [{module}] {name}")
    if detail:
        print(f"       {detail[:300]}")
    return passed

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ── AWS Clients ────────────────────────────────────────────
sts = boto3.client('sts')
ACCOUNT_ID = sts.get_caller_identity()['Account']
print(f"Account: {ACCOUNT_ID} | Region: {REGION} | Time: {datetime.now(timezone.utc).isoformat()}")

agentcore = boto3.client('bedrock-agentcore-control', region_name=REGION)
agentcore_rt = boto3.client('bedrock-agentcore', region_name=REGION)
ecr = boto3.client('ecr', region_name=REGION)
cognito = boto3.client('cognito-idp', region_name=REGION)
lam = boto3.client('lambda', region_name=REGION)
iam = boto3.client('iam')
cw = boto3.client('cloudwatch', region_name=REGION)
logs = boto3.client('logs', region_name=REGION)
ddb = boto3.client('dynamodb', region_name=REGION)

ECR_REGISTRY = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com"
CONTAINER_URI = f"{ECR_REGISTRY}/{ECR_REPO_NAME}:latest"

# ══════════════════════════════════════════════════════════════
section("MODULE 00: Prerequisites")
# ══════════════════════════════════════════════════════════════

# DynamoDB tables
for table in ['products', 'orders', 'accounts']:
    tname = f"{WORKSHOP_PREFIX}-{table}"
    try:
        resp = ddb.describe_table(TableName=tname)
        count = resp['Table']['ItemCount']
        check("00", f"DynamoDB {tname}", True, f"{count} items")
    except:
        check("00", f"DynamoDB {tname}", False, "Table not found — run Module 00 first")

# ══════════════════════════════════════════════════════════════
section("MODULE 01: Single Agent Prototype (local)")
# ══════════════════════════════════════════════════════════════

os.chdir(REPO_ROOT / "01-single-agent-prototype")
sys.path.insert(0, str(REPO_ROOT / "01-single-agent-prototype" / "agents"))
sys.path.insert(0, str(REPO_ROOT / "01-single-agent-prototype"))

try:
    from strands import Agent
    from strands.models import BedrockModel
    from strands.tools.mcp import MCPClient
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    check("01", "SDK imports", True)
except Exception as e:
    check("01", "SDK imports", False, str(e))

try:
    mcp_server_path = REPO_ROOT / "01-single-agent-prototype" / "mcp_servers" / "product_mcp_server.py"
    check("01", "MCP server file exists", mcp_server_path.exists())
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(mcp_server_path)],
        env={**os.environ, "WORKSHOP_PREFIX": WORKSHOP_PREFIX}
    )
    
    mcp_client = MCPClient(lambda: stdio_client(server_params))
    mcp_client.start()
    tools = mcp_client.list_tools_sync()
    tool_names = [t.tool_name for t in tools]
    check("01", "MCP tools loaded", len(tools) >= 6, f"{len(tools)} tools: {tool_names}")
    
    model = BedrockModel(
        model_id="global.anthropic.claude-sonnet-4-6",
        region_name=REGION,
        temperature=0.3,
        max_tokens=1500
    )
    
    basic_agent = Agent(
        name="ProductCatalogAgent", model=model, tools=tools,
        system_prompt="You are a Product Catalog Assistant. Be concise.",
        callback_handler=None
    )
    
    response = basic_agent("Search for wireless headphones. Just list product IDs briefly.")
    resp_text = str(response)
    check("01", "Basic agent query", len(resp_text) > 20, f"Response: {resp_text[:150]}")
    
    mcp_client.stop()
    
    # RBAC agent test
    from product_catalog_agent import create_product_catalog_agent, UserSession
    
    customer = UserSession(user_id="TEST-001", role="customer", email="test@test.com", name="Tester")
    cust_agent = create_product_catalog_agent(region=REGION, user_session=customer)
    resp = cust_agent("Search for headphones. Be brief.")
    check("01", "RBAC customer agent", len(str(resp)) > 20)
    cust_agent.cleanup()
    
except Exception as e:
    check("01", "Local agent test", False, traceback.format_exc()[-400:])

# ══════════════════════════════════════════════════════════════
section("MODULE 03: Production Deployment")
# ══════════════════════════════════════════════════════════════

os.chdir(REPO_ROOT / "03-production-deployment")
sys.path.insert(0, str(REPO_ROOT / "03-production-deployment"))

MODULE_DIR = REPO_ROOT / "03-production-deployment"
AGENT_DIR = MODULE_DIR / "agents"
LAMBDA_DIR = MODULE_DIR / "lambda_tools"

# Nicholas Issue #1: MODULE_DIR
check("03", "MODULE_DIR resolves", MODULE_DIR.is_dir())
check("03", "agents/ dir", AGENT_DIR.is_dir())
check("03", "lambda_tools/ dir", LAMBDA_DIR.is_dir())
check("03", "Dockerfile exists", (AGENT_DIR / "Dockerfile").is_file())

# Nicholas Issue #3: %store / JSON fallback
with open(MODULE_DIR / "03-production-deployment.ipynb") as f:
    nb03 = json.load(f)
src03 = '\n'.join(''.join(c['source']) for c in nb03['cells'])
check("03", "%store persistence", "%store" in src03)
check("03", "save_config fallback", "save_config" in src03 or "deployment_config.json" in src03)

# IAM roles
for role_name in [RUNTIME_ROLE, GATEWAY_ROLE, LAMBDA_ROLE]:
    try:
        r = iam.get_role(RoleName=role_name)
        check("03", f"IAM role {role_name}", True, r['Role']['Arn'])
    except:
        check("03", f"IAM role {role_name}", False, "Not found — create in Module 03 Step 2")

# Cognito
pools = cognito.list_user_pools(MaxResults=20)
ws_pool = [p for p in pools['UserPools'] if COGNITO_POOL_NAME in p['Name']]
USER_POOL_ID = ws_pool[0]['Id'] if ws_pool else None
check("03", "Cognito user pool", USER_POOL_ID is not None, USER_POOL_ID or "Not found")

if USER_POOL_ID:
    clients = cognito.list_user_pool_clients(UserPoolId=USER_POOL_ID, MaxResults=20)
    check("03", "Cognito clients", len(clients.get('UserPoolClients', [])) > 0)

# Lambda functions
for func_name in [LAMBDA_PRODUCT_TOOLS, LAMBDA_RBAC]:
    try:
        f = lam.get_function(FunctionName=func_name)
        check("03", f"Lambda {func_name}", True, f"Runtime: {f['Configuration']['Runtime']}")
    except:
        check("03", f"Lambda {func_name}", False, "Not deployed")

# ECR
try:
    imgs = ecr.list_images(repositoryName=ECR_REPO_NAME)
    check("03", "ECR images", len(imgs.get('imageIds', [])) > 0, f"{len(imgs['imageIds'])} images")
except:
    check("03", "ECR repository", False, "Not found")

# Docker build (ARM64)
print("\n  Building Docker image (ARM64)...")
login_result = subprocess.run(
    f"aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin {ECR_REGISTRY}",
    shell=True, capture_output=True, text=True, timeout=30
)
check("03", "ECR login", login_result.returncode == 0)

build_result = subprocess.run(
    f"docker buildx build --platform linux/arm64 -t {ECR_REPO_NAME}:latest --load {AGENT_DIR}/",
    shell=True, capture_output=True, text=True, timeout=600  # 10 min for ARM64 cross-compile
)
if build_result.returncode != 0:
    # Fallback to regular build
    build_result = subprocess.run(
        f"docker build -t {ECR_REPO_NAME}:latest {AGENT_DIR}/",
        shell=True, capture_output=True, text=True, timeout=600
    )
check("03", "Docker build", build_result.returncode == 0,
      build_result.stderr[-200:] if build_result.returncode != 0 else "Built successfully")

if build_result.returncode == 0:
    push_result = subprocess.run(
        f"docker tag {ECR_REPO_NAME}:latest {CONTAINER_URI} && docker push {CONTAINER_URI}",
        shell=True, capture_output=True, text=True, timeout=300
    )
    check("03", "Docker push to ECR", push_result.returncode == 0)

# Gateway
gateways = agentcore.list_gateways()
ws_gw = [g for g in gateways.get('gatewaySummaries', []) if g.get('gatewayName') == GATEWAY_NAME]
GATEWAY_ID = None
GATEWAY_URL = None

if ws_gw and ws_gw[0]['status'] in ('ACTIVE', 'READY'):
    GATEWAY_ID = ws_gw[0]['gatewayId']
    gw_detail = agentcore.get_gateway(gatewayId=GATEWAY_ID)
    GATEWAY_URL = gw_detail.get('gatewayUrl')
    check("03", "Gateway active", True, f"ID: {GATEWAY_ID}, URL: {GATEWAY_URL}")
else:
    print("  Creating gateway...")
    try:
        from utils import create_gateway
        
        # Find M2M client
        m2m_client_id = None
        if USER_POOL_ID:
            for c in cognito.list_user_pool_clients(UserPoolId=USER_POOL_ID, MaxResults=20).get('UserPoolClients', []):
                detail = cognito.describe_user_pool_client(UserPoolId=USER_POOL_ID, ClientId=c['ClientId'])
                if 'client_credentials' in detail.get('UserPoolClient', {}).get('AllowedOAuthFlows', []):
                    m2m_client_id = c['ClientId']
                    break
        
        # Get RBAC interceptor
        rbac_arn = None
        try:
            rbac_arn = lam.get_function(FunctionName=LAMBDA_RBAC)['Configuration']['FunctionArn']
        except:
            pass
        
        auth_config = {
            "customJWTAuthorizer": {
                "discoveryUrl": f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/openid-configuration",
                "allowedAudience": [m2m_client_id],
                "allowedClients": [m2m_client_id],
            }
        }
        
        gw_resp = create_gateway(
            gateway_client=agentcore,
            name=GATEWAY_NAME,
            role_arn=f"arn:aws:iam::{ACCOUNT_ID}:role/{GATEWAY_ROLE}",
            auth_config=auth_config,
            description="E-Commerce Workshop Gateway with RBAC",
            interceptor_lambda_arn=rbac_arn,
        )
        GATEWAY_ID = gw_resp.get('gatewayId')
        
        # Wait for active
        for i in range(30):
            time.sleep(10)
            status = agentcore.get_gateway(gatewayId=GATEWAY_ID)
            state = status['status']
            print(f"    [{i+1}/30] Gateway: {state}")
            if state in ('ACTIVE', 'READY'):
                GATEWAY_URL = status.get('gatewayUrl')
                break
            if state in ('FAILED', 'DELETE_FAILED'):
                break
        check("03", "Gateway created", state in ('ACTIVE', 'READY'), f"URL: {GATEWAY_URL}")
    except Exception as e:
        check("03", "Gateway creation", False, traceback.format_exc()[-300:])

# Agent Runtime
runtimes = agentcore.list_agent_runtimes()
ws_rt = [r for r in runtimes.get('agentRuntimeSummaries', []) if r.get('agentRuntimeName') == RUNTIME_NAME]
RUNTIME_ID = None

if ws_rt and ws_rt[0]['status'] in ('ACTIVE', 'READY'):
    RUNTIME_ID = ws_rt[0]['agentRuntimeId']
    check("03", "Runtime active", True, f"ID: {RUNTIME_ID}")
else:
    print("  Creating agent runtime...")
    try:
        from utils import create_agent_runtime
        
        OTEL_SERVICE_NAME = RUNTIME_NAME.replace('_', '-')
        env_vars = {
            'AGENT_REGION': REGION,
            'GATEWAY_URL': GATEWAY_URL or '',
            'MODEL_ID': 'global.anthropic.claude-sonnet-4-6',
            'AGENT_OBSERVABILITY_ENABLED': 'true',
            'OTEL_PYTHON_DISTRO': 'aws_distro',
            'OTEL_PYTHON_CONFIGURATOR': 'aws_configurator',
            'OTEL_TRACES_EXPORTER': 'otlp',
            'OTEL_LOGS_EXPORTER': 'otlp',
            'OTEL_METRICS_EXPORTER': 'none',
            'OTEL_SERVICE_NAME': OTEL_SERVICE_NAME,
        }
        
        rt_resp = create_agent_runtime(
            agentcore_client=agentcore,
            runtime_name=RUNTIME_NAME,
            role_arn=f"arn:aws:iam::{ACCOUNT_ID}:role/{RUNTIME_ROLE}",
            container_uri=CONTAINER_URI,
            environment_vars=env_vars,
            description="E-Commerce Workshop Product Catalog Agent",
        )
        if rt_resp:
            RUNTIME_ID = rt_resp['agentRuntimeId']
            check("03", "Runtime created", True, f"ID: {RUNTIME_ID}")
        else:
            check("03", "Runtime created", False, "create_agent_runtime returned None")
    except Exception as e:
        check("03", "Runtime creation", False, traceback.format_exc()[-300:])

# Agent invocation test
if RUNTIME_ID:
    print("\n  Testing agent invocation...")
    try:
        resp = agentcore_rt.invoke_agent_runtime(
            agentRuntimeId=RUNTIME_ID,
            agentRuntimeArtifactName="DEFAULT",
            payload=json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "search_products", "arguments": {"query": "laptop"}},
                "id": "e2e-test-1"
            }).encode()
        )
        body = json.loads(resp['body'].read())
        check("03", "Agent invocation", 'result' in body, f"Keys: {list(body.keys())}")
    except Exception as e:
        check("03", "Agent invocation", False, str(e))

# JSON config save/load (Nicholas Issue #3 live test)
try:
    config = {"REGION": REGION, "RUNTIME_ID": RUNTIME_ID, "GATEWAY_ID": GATEWAY_ID, "GATEWAY_URL": GATEWAY_URL}
    cfg_file = MODULE_DIR / "deployment_config.json"
    with open(cfg_file, 'w') as f:
        json.dump(config, f, indent=2)
    with open(cfg_file) as f:
        loaded = json.load(f)
    check("03", "Config JSON round-trip", loaded.get('RUNTIME_ID') == RUNTIME_ID)
except Exception as e:
    check("03", "Config JSON round-trip", False, str(e))

# ══════════════════════════════════════════════════════════════
section("MODULE 03b: Failure Cases (Nicholas Issue #2)")
# ══════════════════════════════════════════════════════════════

fc_dir = REPO_ROOT / "03-production-deployment-with-failure-cases"
try:
    with open(fc_dir / "deployment_config.py") as f:
        fc_content = f.read()
    has_broken = 'ecommerce-workshop-broken' in fc_content or 'ecommerce_workshop_broken' in fc_content
    check("03b", "Independent prefix", has_broken, "Uses 'ecommerce-workshop-broken'")
    check("03b", "Won't overwrite working agent", has_broken)
except Exception as e:
    check("03b", "Config check", False, str(e))

# ══════════════════════════════════════════════════════════════
section("MODULE 04: Online Eval + Observability")
# ══════════════════════════════════════════════════════════════

os.chdir(REPO_ROOT / "04-online-eval-observability")

# Eval role
try:
    eval_role = iam.get_role(RoleName=EVAL_ROLE)
    EVAL_ROLE_ARN = eval_role['Role']['Arn']
    check("04", "Eval IAM role", True, EVAL_ROLE_ARN)
except:
    check("04", "Eval IAM role", False, "Not found — create in Module 04")
    EVAL_ROLE_ARN = None

# Code-level verification (Nicholas Issues #4 and #5)
with open(REPO_ROOT / "04-online-eval-observability" / "04-agentcore-evaluations.ipynb") as f:
    nb04 = json.load(f)
src04 = '\n'.join(''.join(c['source']) for c in nb04['cells'])

check("04", "No create_evaluation_job (Issue #4)", "create_evaluation_job" not in src04,
      "Removed non-existent API")
check("04", "Has evaluate() API (Issue #4)", "evaluate(" in src04 and "evaluationTarget" in src04)
check("04", "Correct namespace AWS/Bedrock-AgentCore (Issue #5)", "AWS/Bedrock-AgentCore" in src04)
check("04", "Has Logs Insights queries (Issue #5)", "SOURCE" in src04)
check("04", "Has pre-flight check", "pre-flight" in src04.lower() or "PRE-FLIGHT" in src04)
check("04", "Has runtime log group query", "runtimes/" in src04 and "DEFAULT" in src04)

# Live: CW namespace
try:
    metrics = cw.list_metrics(Namespace='AWS/Bedrock-AgentCore')
    check("04", "CW metrics exist", len(metrics.get('Metrics', [])) > 0,
          f"{len(metrics['Metrics'])} metrics in AWS/Bedrock-AgentCore")
except Exception as e:
    check("04", "CW metrics", False, str(e))

# Wrong namespaces should be empty
for ns in ['Bedrock-AgentCore/AgentRuntime', 'Bedrock-AgentCore/Evaluations']:
    m = cw.list_metrics(Namespace=ns)
    check("04", f"{ns} empty (expected)", len(m.get('Metrics', [])) == 0)

# Log groups
eval_lgs = logs.describe_log_groups(logGroupNamePrefix='/aws/bedrock-agentcore/evaluations')
check("04", "Eval log group exists", len(eval_lgs.get('logGroups', [])) > 0)

spans_lgs = logs.describe_log_groups(logGroupNamePrefix='aws/spans')
check("04", "aws/spans log group", len(spans_lgs.get('logGroups', [])) > 0)

# Live: evaluate() API test (Nicholas Issue #4)
if RUNTIME_ID:
    try:
        print("\n  Testing evaluate() API...")
        # Invoke agent first to generate a trace
        invoke_resp = agentcore_rt.invoke_agent_runtime(
            agentRuntimeId=RUNTIME_ID,
            agentRuntimeArtifactName="DEFAULT",
            payload=json.dumps({
                "jsonrpc": "2.0", "method": "tools/call",
                "params": {"name": "search_products", "arguments": {"query": "headphones"}},
                "id": "eval-test"
            }).encode()
        )
        body = json.loads(invoke_resp['body'].read())
        print(f"    Invocation result: {list(body.keys())}")
        
        # Wait for traces to propagate
        print("    Waiting 30s for trace propagation...")
        time.sleep(30)
        
        # Try evaluate with builtin evaluator
        eval_resp = agentcore_rt.evaluate(
            evaluatorId="Builtin.Helpfulness",
            evaluationInput={"conversation": {
                "messages": [
                    {"role": "user", "content": [{"text": "Search for wireless headphones under $100"}]},
                    {"role": "assistant", "content": [{"text": str(body.get('result', 'Found products'))}]}
                ]
            }},
        )
        eval_results = eval_resp.get('evaluationResults', [])
        check("04", "evaluate() API live test", len(eval_results) > 0,
              f"Got {len(eval_results)} results: {eval_results[0] if eval_results else 'none'}")
    except Exception as e:
        check("04", "evaluate() API live test", False, f"{type(e).__name__}: {e}")
else:
    check("04", "evaluate() API live test", False, "No runtime — skipped")

# ══════════════════════════════════════════════════════════════
section("SUMMARY")
# ══════════════════════════════════════════════════════════════

total = len(results)
passed = sum(1 for r in results.values() if r['passed'])
failed = total - passed

print(f"\n  Total: {total} | Passed: {passed} ✅ | Failed: {failed} ❌ | Rate: {passed/total*100:.0f}%")

# Nicholas issues
nicholas = {
    "#1 MODULE_DIR paths": results.get("03: MODULE_DIR resolves", {}).get("passed", False),
    "#2 Failure cases prefix": results.get("03b: Independent prefix", {}).get("passed", False),
    "#3 %store persistence": results.get("03: %store persistence", {}).get("passed", False),
    "#4 evaluate() API (code)": results.get("04: Has evaluate() API (Issue #4)", {}).get("passed", False),
    "#4 evaluate() API (live)": results.get("04: evaluate() API live test", {}).get("passed", False),
    "#5 Dashboard namespace (code)": results.get("04: Correct namespace AWS/Bedrock-AgentCore (Issue #5)", {}).get("passed", False),
    "#5 CW metrics exist": results.get("04: CW metrics exist", {}).get("passed", False),
}

print(f"\n  NICHOLAS ISSUES:")
for issue, ok in nicholas.items():
    print(f"    {'✅' if ok else '❌'} {issue}")

if failed > 0:
    print(f"\n  FAILURES:")
    for name, r in results.items():
        if not r['passed']:
            print(f"    ❌ {name}: {r['detail'][:200]}")

# Write report
with open(REPO_ROOT / 'E2E_REPORT.md', 'w') as f:
    f.write(f"# E2E Verification Report — Ecommerce Agent Workshop\n\n")
    f.write(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
    f.write(f"**Account:** {ACCOUNT_ID} | **Region:** {REGION}\n\n")
    f.write(f"## Summary: {passed}/{total} passed ({passed/total*100:.0f}%)\n\n")
    
    f.write("## Nicholas Moore's Issues\n\n")
    f.write("| # | Issue | Code ✓ | Live ✓ |\n|---|-------|--------|--------|\n")
    f.write(f"| 1 | MODULE_DIR path variable | {'✅' if nicholas['#1 MODULE_DIR paths'] else '❌'} | {'✅' if results.get('03: agents/ dir', {}).get('passed') else '❌'} |\n")
    f.write(f"| 2 | Failure cases independent prefix | {'✅' if nicholas['#2 Failure cases prefix'] else '❌'} | {'✅' if nicholas['#2 Failure cases prefix'] else '❌'} |\n")
    f.write(f"| 3 | %store persistence + cleanup | {'✅' if nicholas['#3 %store persistence'] else '❌'} | {'✅' if results.get('03: Config JSON round-trip', {}).get('passed') else '❌'} |\n")
    f.write(f"| 4 | evaluate() API fix | {'✅' if nicholas['#4 evaluate() API (code)'] else '❌'} | {'✅' if nicholas['#4 evaluate() API (live)'] else '❌'} |\n")
    f.write(f"| 5 | Dashboard namespace fix | {'✅' if nicholas['#5 Dashboard namespace (code)'] else '❌'} | {'✅' if nicholas['#5 CW metrics exist'] else '❌'} |\n")
    
    f.write(f"\n## All Checks\n\n")
    modules = sorted(set(r['module'] for r in results.values()))
    for mod in modules:
        f.write(f"\n### Module {mod}\n\n")
        for name, r in results.items():
            if r['module'] == mod:
                f.write(f"- {'✅' if r['passed'] else '❌'} **{name}**")
                if r['detail']:
                    f.write(f": {r['detail'][:200]}")
                f.write("\n")
    
    f.write(f"\n## Infrastructure\n\n")
    f.write(f"- Runtime ID: {RUNTIME_ID or 'Not deployed'}\n")
    f.write(f"- Gateway ID: {GATEWAY_ID or 'Not deployed'}\n")
    f.write(f"- Gateway URL: {GATEWAY_URL or 'N/A'}\n")
    f.write(f"- ECR: {CONTAINER_URI}\n")
    f.write(f"- Cognito Pool: {USER_POOL_ID or 'N/A'}\n")

print(f"\n  Report: {REPO_ROOT}/E2E_REPORT.md")
print(f"\nE2E_COMPLETE: {passed}/{total}")
sys.exit(0 if failed == 0 else 1)
