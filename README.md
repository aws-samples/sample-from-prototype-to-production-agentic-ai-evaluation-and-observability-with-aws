# From Prototype to Production with AWS
## Agentic AI Evaluation and Observability Workshop

Transform your AI agents from promising prototypes into production-ready systems. This hands-on workshop teaches you to build, evaluate, deploy, observe, and optimize AI agents using AWS Bedrock AgentCore — starting with a single agent with RBAC and progressing to production deployment, managed evaluation, online evidence, and optimization experiments. Workshop instruction is [here](https://catalog.us-east-1.prod.workshops.aws/workshops/927fb19e-6733-4986-904c-3e63b28c21e7/en-US).

---

## Why This Workshop?

**The Challenge**: Most AI agent projects fail in production—not because the agents don't work, but because teams lack the tools and practices to evaluate, monitor, and improve them at scale.

**The Solution**: This workshop provides a complete framework for:
- **Systematic Evaluation** - Test agents before deployment with custom evaluators
- **Production Observability** - Monitor agent behavior with OTEL tracing
- **Continuous Improvement** - Use managed datasets, feedback loops, recommendations, and A/B tests to improve safely

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
- **Full observability** - OTEL tracing, CloudWatch metrics, AgentCore evaluations, and batch release gates
- **Production deployment** - AWS Bedrock AgentCore with gateway, runtime, and Identity (JWT auth)
- **Optimization loop** - AgentCore recommendations, config bundles, A/B testing, and release decisions

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
5. **Update** evaluation datasets from reviewed production evidence
6. **Optimize** the agent with AgentCore recommendations, config-bundle experiments, A/B metrics, and release decisions

---

## Evaluation Framework: The Evaluation Pyramid

The workshop teaches a layered evaluation approach — the **Evaluation Pyramid** — where each layer builds on the one below:

| Layer | Name | Description | Modules |
|-------|------|-------------|---------|
| **Layer 1** | Deterministic Assertions | Hard checks: expected tool called, RBAC enforced, required fields present. Fast, cheap, no LLM needed. | 02a (Step 3b) |
| **Layer 2** | LLM-as-Judge | An LLM scores agent responses on rubrics (helpfulness, goal success, policy compliance). Flexible but requires calibration. Covers local custom rubrics and AWS-managed built-in evaluators used for on-demand, batch, online, and A/B evaluation. | 02a, 02b, 03, 04, 05 |
| **Layer 3** | Meta-Evaluation & Human Review | Evaluate the evaluators: compare LLM judge scores against expert-labeled ground truth. Detects evaluator drift. | 02a (Meta-Evaluation section) |

**Principle:** Start at Layer 1 — deterministic checks catch the most critical failures at near-zero cost. Only escalate to Layer 2/3 for nuanced quality judgments that rules can't capture.

**Two classes of Layer 2 evaluators used in this workshop:**
- **Custom LLM-as-Judge** (`02-evaluation-baseline/custom_evaluators.py`) — 7 domain-specific evaluators defined and run locally in Module 02a to establish the first quality contract.
- **AgentCore built-in evaluators** — AWS-managed LLM-as-Judge running in the cloud. Module 02a demonstrates on-demand calls, Module 03 uses managed batch evaluation for the release-candidate gate, Module 04 uses online evidence and trace mining, and Module 05 uses managed evaluation metrics for optimization experiments.

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
                    │   (Claude Sonnet 5)          │
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

> **Module 02b (DeepEval) is optional** — it demonstrates an alternative evaluation framework. The core workshop path uses Module 02a to create local quality evidence that Section 03a turns into managed ground-truth datasets and simulation scenarios.

### Module 3: Production Deployment [Pyramid: —]
**Directory**: `03-production-deployment/`

Deploy agents to AWS with full observability:
- Convert Section 02 evaluation evidence into ground-truth datasets and simulation scenarios in `03a-ground-truth-dataset.ipynb`
- Package agents for AgentCore Runtime
- Configure AgentCore Gateway for MCP tools
- Deploy with auto-instrumented OTEL tracing
- Verify deployment with test invocations
- Run an AgentCore batch evaluation as the release-candidate gate and save durable deployment evidence

### Module 4: Online Evaluation, Observability & Feedback Loop [Pyramid: Layer 2 — built-in]
**Directory**: `04-online-eval-observability/`

Monitor production behavior and turn reviewed evidence into better evaluation assets:
- Confirm online evidence from the deployed AgentCore runtime
- Mine OTEL spans from CloudWatch for tool usage, failures, latency, and candidate evaluation examples
- Review mined candidates before promotion so production traces do not automatically become tests
- Update the managed dataset lineage with reviewed examples
- Save an online evidence manifest and dataset update manifest for optimization

> **Note:** This module treats production traces as evidence, not automatic truth. Human or policy review decides which examples become managed dataset updates.

### Module 5: AgentCore Optimization & Release Decision [Pyramid: Layer 2 — managed]
**Directory**: `05-agentcore-optimization/`

Optimize the deployed agent using the evidence prepared by earlier modules:
- Read the Section 03 deployment and batch-evaluation manifests plus the Section 04 feedback artifacts
- Run AgentCore Optimization Insights and recommendation analysis
- Build candidate config bundles for prompt/model/tool-policy changes
- Run a managed A/B experiment against the current runtime endpoint
- Review A/B metric counts, evaluator scores, confidence signals, and errors before deciding
- Save a release decision report and promotion manifest; promotion is explicit and only proceeds when the gate allows it

---

## Evaluation & Observability Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              Agent Evaluation and Optimization Journey on AWS                │
│                                                                              │
│  Module 02              Module 03a              Module 03                    │
│  Local quality      ──▶ Ground truth and   ──▶  Runtime deployment           │
│  contract               simulations             + batch release gate         │
│       │                       │                        │                     │
│       │                       ▼                        ▼                     │
│       │              AgentCore managed          AgentCore Runtime             │
│       │              datasets and versions      + Gateway + OTEL traces      │
│       │                                                │                     │
│       ▼                                                ▼                     │
│  Baseline evidence        Module 04              CloudWatch spans            │
│  and thresholds      ◀──  Online evidence  ◀───  online evaluation           │
│                           + reviewed feedback     and production traces      │
│                                   │                                          │
│                                   ▼                                          │
│                         Dataset update manifest                              │
│                                   │                                          │
│                                   ▼                                          │
│                         Module 05 AgentCore Optimization                     │
│                         Insights + recommendations + config bundles          │
│                         + managed A/B metrics + release decision             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Custom Evaluators

The workshop teaches you to build domain-specific evaluators. All seven live in `02-evaluation-baseline/custom_evaluators.py` and establish the local quality contract in Module 02a:

| Evaluator | What It Measures | Example Criteria |
|-----------|------------------|------------------|
| **Goal Success** | Did the agent complete the task? | Request fully addressed; accurate denial for out-of-role requests |
| **Helpfulness** | Is the response useful and actionable? | Explains what the user *can* do, not just what they can't |
| **RBAC Compliance** | Did the agent correctly enforce role-based permissions? | Customer blocked from admin tools; no info leaks via error messages |
| **Tool Parameter Accuracy** | Was the right tool called with the right parameters? | Search query → `search_products` with matching keywords |
| **Policy Compliance** | Does it follow business rules? | 30-day return policy, scope limits, data privacy, hygiene restrictions |
| **Response Quality** | Is the output accurate, complete, and professional? | Clear structure, correct facts, appropriate tone |
| **Customer Satisfaction** | Predicted CSAT | Issue resolved, low effort, graceful denial with alternatives |

The judge model for all seven is `global.anthropic.claude-sonnet-5` (cross-region inference profile, available in every AWS region).

---

## Prerequisites

### AWS Services Required
- Amazon Bedrock (Claude Sonnet 5)
- Amazon Bedrock AgentCore (Runtime, Gateway)
- Amazon DynamoDB
- Amazon CloudWatch
- Amazon S3
- Amazon Kinesis Firehose
- AWS IAM

### Model Access
Enable in Amazon Bedrock console (using global cross-region inference):
- `global.anthropic.claude-sonnet-5` (used for both the agent and the evaluation judge)

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
  # Module 0 → Module 1 → Module 2 → Module 3a → Module 3 → Module 4 → Module 5
  ```

---

## Key Takeaways

After completing this workshop, you'll understand:

1. **Evaluation is not optional** — Systematic testing prevents production failures
2. **Observability enables improvement** — You can't fix what you can't see
3. **AgentCore simplifies operations** — Focus on agent logic, not infrastructure
4. **OTEL traces reveal behavior** — See exactly which tools agents call and why
5. **Managed evaluation creates durable gates** — Section 03 batch evaluation records the release-candidate baseline before production feedback and optimization begin
6. **Feedback should be reviewed before it becomes truth** — Section 04 mines production traces, but only reviewed examples update the managed datasets
7. **Optimization needs evidence, not guesses** — Section 05 uses AgentCore recommendations, config bundles, A/B metrics, and an explicit release decision before promotion


---

## Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)

---

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
