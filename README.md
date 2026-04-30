# From Prototype to Production with AWS
## Agentic AI Evaluation and Observability Workshop

Transform your AI agents from promising prototypes into production-ready systems. This hands-on workshop teaches you to build, evaluate, deploy, and continuously monitor AI agents using AWS Bedrock AgentCore — starting with a single agent with RBAC and progressing to production deployment with observability. Workshop instruciton is [here](https://catalog.us-east-1.prod.workshops.aws/workshops/927fb19e-6733-4986-904c-3e63b28c21e7/en-US). 

---

## Why This Workshop?

**The Challenge**: Most AI agent projects fail in production—not because the agents don't work, but because teams lack the tools and practices to evaluate, monitor, and improve them at scale.

**The Solution**: This workshop provides a complete framework for:
- **Systematic Evaluation** - Test agents before deployment with custom evaluators
- **Production Observability** - Monitor agent behavior with OTEL tracing
- **Continuous Improvement** - Detect drift and iterate based on real data

---

## Workshop Overview

| Item | Details |
|------|---------|
| **Duration** | 2.5 hours |
| **Level** | Intermediate |
| **Use Case** | E-Commerce Customer Service |
| **Focus** | Evaluation, Observability & Production Readiness |

### What You'll Build

A production-ready AI agent system for e-commerce, progressing from simple to complex:
- **Single agent with RBAC** - Product catalog agent with customer/admin role-based access control
- **Comprehensive evaluation** - Custom evaluators for quality, tool accuracy, and access control compliance
- **Full observability** - OTEL tracing, CloudWatch metrics, and batch evaluation
- **Production deployment** - AWS Bedrock AgentCore with gateway, runtime, and Identity (JWT auth)

---

## Why AWS Bedrock AgentCore?

AgentCore is AWS's fully managed service for deploying and operating AI agents at scale. Key benefits:

| Benefit | Description |
|---------|-------------|
| **Managed Runtime** | Deploy agents without infrastructure management—auto-scaling, high availability, and security built-in |
| **Built-in Observability** | OTEL-compliant tracing automatically captures agent interactions, tool calls, and LLM invocations |
| **Gateway Integration** | Secure MCP tool connectivity with authentication and rate limiting |
| **Cost Optimization** | Pay-per-invocation pricing with no idle costs |
| **Enterprise Security** | VPC integration, IAM policies, and encryption at rest/in-transit |

### AgentCore Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS Bedrock AgentCore                            │
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    │
│  │  AgentCore      │    │  AgentCore      │    │  CloudWatch     │    │
│  │  Runtime        │◄──►│  Gateway        │    │  (OTEL Traces)  │    │
│  │  (Your Agents)  │    │  (MCP Tools)    │    │                 │    │
│  └────────┬────────┘    └─────────────────┘    └────────▲────────┘    │
│           │                                             │              │
│           │              Auto-instrumented              │              │
│           └─────────────────────────────────────────────┘              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

The runtime emits OTEL spans to two CloudWatch log groups used throughout the workshop:
- `/aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT` — agent-level invocation logs
- `aws/spans` — fine-grained span data (tool calls, LLM inputs/outputs, latency)

---

## Key Learning Outcomes

By the end of this workshop, you will:

1. **Build** a single agent with MCP tools and role-based access control
2. **Evaluate** the agent systematically with custom evaluators (tool accuracy, compliance, quality)
3. **Deploy** to production with AgentCore Runtime, Gateway, and Identity
4. **Observe** agent behavior through OTEL traces and CloudWatch metrics
5. **Analyze** production traffic with batch evaluation pipelines

---

## Evaluation Framework: The Evaluation Pyramid

The workshop teaches a layered evaluation approach — the **Evaluation Pyramid** — where each layer builds on the one below:

| Layer | Name | Description | Modules |
|-------|------|-------------|---------|
| **Layer 1** | Deterministic Assertions | Hard checks: expected tool called, RBAC enforced, required fields present. Fast, cheap, no LLM needed. | 02a (Step 3b) |
| **Layer 2** | LLM-as-Judge | An LLM scores agent responses on rubrics (helpfulness, goal success, policy compliance). Flexible but requires calibration. Covers both custom rubrics (02a, 05) and AWS-managed built-in evaluators (02a Step 10, 04). | 02a, 02b, 04, 05 |
| **Layer 3** | Meta-Evaluation & Human Review | Evaluate the evaluators: compare LLM judge scores against expert-labeled ground truth. Detects evaluator drift. | 02a (Meta-Evaluation section) |

**Principle:** Start at Layer 1 — deterministic checks catch the most critical failures at near-zero cost. Only escalate to Layer 2/3 for nuanced quality judgments that rules can't capture.

**Two classes of Layer 2 evaluators used in this workshop:**
- **Custom LLM-as-Judge** (`02-evaluation-baseline/custom_evaluators.py`) — 7 domain-specific evaluators defined and run locally (Module 02a), then reused for batch evaluation in Module 05.
- **AgentCore built-in evaluators** — AWS-managed LLM-as-Judge running in the cloud. Module 04 configures these on live traffic (Helpfulness, GoalSuccessRate, ToolSelectionAccuracy, Coherence). Module 02a Step 10 demonstrates calling them on-demand via the Evaluate API.

---

## Module 1 Architecture — Single Agent with RBAC

```
                    ┌──────────────────────────────┐
                    │      User Request            │
                    │  (with role: customer/admin)  │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   PRODUCT CATALOG AGENT       │
                    │   (Claude Sonnet 4.6)         │
                    │   • Role-aware system prompt  │
                    │   • Tool filtering by role    │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   Product MCP Server          │
                    │   (FastMCP - single server)   │
                    │                               │
                    │  READ tools (customer+admin): │
                    │  • search_products            │
                    │  • get_product_details        │
                    │  • check_inventory            │
                    │  • get_product_recommendations│
                    │  • compare_products           │
                    │  • get_return_policy          │
                    │                               │
                    │  WRITE tools (admin only):    │
                    │  • create_product             │
                    │  • update_product             │
                    │  • delete_product             │
                    │  • update_inventory           │
                    │  • update_pricing             │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │       DynamoDB               │
                    │    Products Table            │
                    └──────────────────────────────┘
```

---

## Workshop Modules

### Module 0: Environment Setup
**Directory**: `00-prerequisites/`

Set up the workshop environment:
- Install Python dependencies with `uv sync`
- Provision DynamoDB tables and load sample data
- Verify AWS credentials, Bedrock model access, and infrastructure

### Module 1: Single Agent Prototype with RBAC [Pyramid: —]
**Directory**: `01-single-agent-prototype/`

Build a single product catalog agent with role-based access control:
- Connect to an MCP server with 11 tools (6 read + 5 admin write)
- Implement RBAC via tool filtering — customers get read tools, admins get all tools
- Test customer persona (search, browse, compare) and admin persona (create, update, delete)
- Validate access control boundaries — customers cannot perform admin operations
- Preview how local RBAC maps to AgentCore Identity JWT auth in production

> **DynamoDB schema note:** the `specifications` field is stored as a **JSON string** (matching the seed schema produced by the CDK data loader). `create_product` and `update_product` validate incoming JSON but persist it as a string so readers never see a mixed `str`/`Map` column.

### Module 2: Evaluation & Baseline [Pyramid: Layer 1, 2, 3]
**Directory**: `02-evaluation-baseline/`

> **If short on time, run only the first 10 test cases** in notebook 02a to get a meaningful baseline in ~15 min.

Establish quality baselines before deployment using the seven custom evaluators defined in `02-evaluation-baseline/custom_evaluators.py`:
- **Goal Success** — Did the agent complete the task?
- **Helpfulness** — Is the response useful and actionable?
- **RBAC Compliance** — Did the agent correctly enforce role-based permissions?
- **Tool Parameter Accuracy** — Was the right tool called with the right parameters?
- **Policy Compliance** — Does the response follow business rules (return policy, scope, privacy)?
- **Response Quality** — Is the output accurate, complete, and professional?
- **Customer Satisfaction** — Predicted CSAT for the interaction

The notebook also demonstrates Layer 1 deterministic assertions (Step 3b), Layer 2 LLM-as-Judge evaluation (Steps 4–6), and Layer 3 meta-evaluation against expert-labeled known-answer pairs. Step 10 additionally calls the AgentCore Evaluate API with three built-in evaluators for a side-by-side comparison.

> **Module 02b (DeepEval) is optional** — it demonstrates an alternative evaluation framework. The core workshop path uses strands-evals (Module 02a), whose evaluators are reused in Module 05 for production batch evaluation.

### Module 3: Production Deployment [Pyramid: —]
**Directory**: `03-production-deployment/`

Deploy agents to AWS with full observability:
- Package agents for AgentCore Runtime
- Configure AgentCore Gateway for MCP tools
- Deploy with auto-instrumented OTEL tracing
- Verify deployment with test invocations

### Module 4: Online Evaluation & Observability [Pyramid: Layer 2 — built-in]
**Directory**: `04-online-eval-observability/`

Monitor and evaluate agents in production (8 steps):
- Configure online evaluation with four AWS-managed **built-in** evaluators (Helpfulness, GoalSuccessRate, ToolSelectionAccuracy, Coherence) at 100% sampling for demo — reduce to 10–20% in production.
- Generate test data and validate tool connectivity
- Explore OTEL traces in CloudWatch (span flow, tool calls, latency)
- Extract and analyze tool call patterns from trace spans (`aws/spans` log group)
- Build a CloudWatch custom dashboard as a "single pane of glass" — operations metrics + evaluation scores + tool calls + token usage + cost

> **Note:** This module uses *built-in* evaluators only, for simplicity and to highlight AWS-managed operations. AgentCore also supports custom LLM-as-Judge and Lambda-backed evaluators via `CreateEvaluator` — see [AgentCore Evaluators docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluators.html). Module 02a Step 10 demonstrates calling built-in evaluators on-demand; Module 05 combines built-in on-demand calls with custom batch evaluation.

### Module 5: Production Batch Evaluation [Pyramid: Layer 2 — custom]
**Directory**: `05-production-batch-evaluation/`

Evaluate production traffic at scale:
- Export OTEL traces from agent runtime logs (primary path: CloudWatch Logs Insights query; alternative path: Firehose → S3 for scheduled batches)
- Classify tool calls by category (READ vs WRITE)
- Run batch evaluation with the same seven custom evaluators from Module 2
- Detect drift by comparing production scores against Module 2 baselines
- Close the feedback loop: production failures are appended in-place to `02-evaluation-baseline/evaluation_dataset.json` with `source="production_feedback"`, so the next Module 2 run treats them as regression tests
- Replace the Module 4 placeholder dashboard with a unified view combining operational metrics, online eval scores, and batch eval scores

---

## Evaluation & Observability Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Production Evaluation Pipeline                             │
│                                                                              │
│  Agent Runtime  ──OTEL──▶  CloudWatch Log Groups                            │
│                           (/aws/bedrock-agentcore/runtimes/*, aws/spans)    │
│                                   │                                          │
│           ┌───────────────────────┼───────────────────────────┐              │
│           │                       │                           │              │
│           ▼ PRIMARY PATH          ▼ ALTERNATIVE PATH          ▼              │
│  ┌──────────────────┐   ┌──────────────────────────┐   ┌──────────────┐     │
│  │ Online Eval      │   │ Subscription Filter      │   │ Logs Insights│     │
│  │ (Module 04)      │   │ → Kinesis Firehose       │   │ direct query │     │
│  │ Built-in         │   │ → S3 Bucket              │   │ (Module 05   │     │
│  │ evaluators       │   │ (historical replay)      │   │  Step 5)     │     │
│  │ on live traffic  │   └──────────────────────────┘   └──────┬───────┘     │
│  └────────┬─────────┘                                         │              │
│           │                                                    ▼              │
│           │                                          ┌──────────────────┐    │
│           │                                          │ Batch Evaluation │    │
│           │                                          │ Module 05 — 7    │    │
│           │                                          │ custom evaluators│    │
│           │                                          └────────┬─────────┘    │
│           │                                                    │              │
│           ▼                                                    ▼              │
│  CloudWatch Metrics                               ┌──────────────────────┐   │
│  Bedrock-AgentCore/Evaluations                    │ Drift Detection +    │   │
│      │                                            │ Feedback Loop        │   │
│      └──────────────┐                             │ (enriches Module 2   │   │
│                     ▼                             │  dataset in-place)   │   │
│            Unified Dashboard                      └──────────┬───────────┘   │
│            EcommerceWorkshop-ProductCatalogAgent             │               │
│            (built in Module 4, extended in Module 5) ◄───────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Custom Evaluators

The workshop teaches you to build domain-specific evaluators. All seven live in `02-evaluation-baseline/custom_evaluators.py` and are reused by Module 05 for batch evaluation:

| Evaluator | What It Measures | Example Criteria |
|-----------|------------------|------------------|
| **Goal Success** | Did the agent complete the task? | Request fully addressed; accurate denial for out-of-role requests |
| **Helpfulness** | Is the response useful and actionable? | Explains what the user *can* do, not just what they can't |
| **RBAC Compliance** | Did the agent correctly enforce role-based permissions? | Customer blocked from admin tools; no info leaks via error messages |
| **Tool Parameter Accuracy** | Was the right tool called with the right parameters? | Search query → `search_products` with matching keywords |
| **Policy Compliance** | Does it follow business rules? | 30-day return policy, scope limits, data privacy, hygiene restrictions |
| **Response Quality** | Is the output accurate, complete, and professional? | Clear structure, correct facts, appropriate tone |
| **Customer Satisfaction** | Predicted CSAT | Issue resolved, low effort, graceful denial with alternatives |

The judge model for all seven is `global.anthropic.claude-sonnet-4-6` (cross-region inference profile, available in every AWS region).

---

## Prerequisites

### AWS Services Required
- Amazon Bedrock (Claude Sonnet 4.6)
- Amazon Bedrock AgentCore (Runtime, Gateway)
- Amazon DynamoDB
- Amazon CloudWatch
- Amazon S3
- Amazon Kinesis Firehose
- AWS IAM

### Model Access
Enable in Amazon Bedrock console (using global cross-region inference):
- `global.anthropic.claude-sonnet-4-6` (used for both the agent and the evaluation judge)

---

## Quick Start

1. **Install uv** (if not already installed)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Python dependencies**
   ```bash
   uv sync
   ```

3. **Run modules in order**
  ```
  # Module 0 → Module 1 → Module 2 → Module 3 → Module 4 → Module 5
  ```

---

## Key Takeaways

After completing this workshop, you'll understand:

1. **Evaluation is not optional** — Systematic testing prevents production failures
2. **Observability enables improvement** — You can't fix what you can't see
3. **AgentCore simplifies operations** — Focus on agent logic, not infrastructure
4. **OTEL traces reveal behavior** — See exactly which tools agents call and why
5. **Batch evaluation closes the loop** — Production failures that score below threshold are appended in-place to Module 2's `evaluation_dataset.json` with `source="production_feedback"`, so the next offline run automatically treats them as regression tests
6. **Two classes of Layer 2 evaluators have different roles** — Custom rubrics (Modules 02a, 05) capture domain-specific quality that built-ins can't know; AgentCore built-ins (Module 04) are zero-ops managed infra for continuous monitoring


---

## Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)

---

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
