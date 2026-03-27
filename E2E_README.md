# E2E Verification — Ecommerce Agent Workshop

One-shot script to verify all notebooks work correctly and all of Nicholas Moore's reported issues are fixed.

## Quick Start

```bash
cd ecommerce-agent-workshop

# Install dependencies
pip install boto3 strands-agents strands-agents-tools mcp

# Or with uv (recommended)
uv run --with boto3,strands-agents,strands-agents-tools,mcp python e2e_test.py
```

## Requirements

- **AWS credentials** with permissions for:
  - `iam:PassRole` (to create Gateway/Runtime)
  - `bedrock-agentcore:*` (AgentCore operations)
  - `lambda:*` (check/create Lambda functions)
  - `cognito-idp:*` (user pool operations)
  - `ecr:*` (container registry)
  - `cloudwatch:*` and `logs:*` (metrics and log queries)
  - `dynamodb:*` (table access)
- **Docker** with ARM64 support (buildx)
- **Python 3.11+**

> ⚠️ `PowerUserAccess` is **not sufficient** — it denies `iam:*` which blocks `iam:PassRole` needed by AgentCore.
> Use an admin session or a role with explicit `iam:PassRole` for the `ecommerce-workshop-*` roles.

## What It Tests

### Per Module

| Module | Tests |
|--------|-------|
| 00 | DynamoDB tables + data |
| 01 | MCP server + basic agent + RBAC agent queries |
| 03 | MODULE_DIR, IAM roles, Cognito, Lambda, ECR, Docker build, Gateway, Runtime, invocation, JSON config |
| 03b | Independent failure-case prefix |
| 04 | Evaluator creation, evaluate() API, CW namespace, log groups, Logs Insights queries |

### Nicholas Moore's 5 Issues

| # | Issue | How Verified |
|---|-------|-------------|
| 1 | Hardcoded paths → MODULE_DIR | Code check + directory validation |
| 2 | Failure cases overwrite working agent | Checks `deployment_config.py` for independent prefix |
| 3 | Env vars lost after cleanup | %store in code + JSON file round-trip |
| 4 | `create_evaluation_job` doesn't exist | Code check (removed) + live `evaluate()` call |
| 5 | Dashboard empty metrics | Correct namespace check + CW Logs Insights queries |

## Output

- Stdout: real-time check results with ✅/❌
- `E2E_REPORT.md`: full report with summary, Nicholas issues table, per-module details, and infrastructure state
- Exit code: 0 if all pass, 1 if any fail

## Expected Duration

- ~2-3 min if infrastructure exists (Gateway + Runtime already deployed)
- ~15-20 min if creating from scratch (Gateway + Runtime deployment + Docker build)
