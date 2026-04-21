# From Prototype to Production with AWS
## Agentic AI Evaluation and Observability Workshop

Transform your AI agents from promising prototypes into production-ready systems. This hands-on workshop teaches you to build, evaluate, deploy, and continuously monitor AI agents using AWS Bedrock AgentCore — starting with a single agent with RBAC and progressing to production deployment with observability.

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
| **Layer 1** | Deterministic Assertions | Hard checks: expected tool called, RBAC enforced, required fields present. Fast, cheap, no LLM needed. | 02b |
| **Layer 2** | LLM-as-Judge | An LLM scores agent responses on rubrics (helpfulness, goal success, policy compliance). Flexible but requires calibration. | 02a, 02b, 04 |
| **Layer 3** | Meta-Evaluation & Human Review | Evaluate the evaluators: compare LLM judge scores against expert-labeled ground truth. Detects evaluator drift. | 02b |

**Principle:** Start at Layer 1 — deterministic checks catch the most critical failures at near-zero cost. Only escalate to Layer 2/3 for nuanced quality judgments that rules can't capture.

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

### Module 2: Evaluation & Baseline [Pyramid: Layer 1, 2, 3]
**Directory**: `02-evaluation-baseline/`

> **If short on time, run only the first 10 test cases** in notebook 02b to get a meaningful baseline in ~15 min.

Establish quality baselines before deployment:
- Define custom evaluators for your use case:
  - **Goal Success** - Did the agent address the request?
  - **Tool Accuracy** - Did the agent use the correct tool?
  - **Access Control Compliance** - Did RBAC correctly restrict operations?
  - **Policy Compliance** - Does the response follow business rules?
  - **Response Quality** - Is the output helpful and accurate?
- Run evaluation with synthetic test cases
- Analyze results and identify improvement areas

> **Module 02a (DeepEval) is optional** — it demonstrates an alternative evaluation framework. The core workshop path uses strands-evals (Module 02b) which integrates with AgentCore in later modules.

### Module 3: Production Deployment [Pyramid: —]
**Directory**: `03-production-deployment/`

Deploy agents to AWS with full observability:
- Package agents for AgentCore Runtime
- Configure AgentCore Gateway for MCP tools
- Deploy with auto-instrumented OTEL tracing
- Verify deployment with test invocations

### Module 4: Online Evaluation & Observability [Pyramid: Layer 2]
**Directory**: `04-online-eval-observability/`

Monitor and evaluate agents in production (8 steps):
- Configure online evaluation with built-in and custom evaluators
- Generate test data and validate tool connectivity
- Explore OTEL traces in CloudWatch (span flow, tool calls, latency)
- Extract and analyze tool call patterns from trace spans
- Build a CloudWatch custom dashboard as a "single pane of glass"

> **Note:** On-demand evaluation via the Evaluate API requires broader scope configuration. This module uses online evaluation which runs automatically on every agent invocation.

### Module 5: Production Batch Evaluation [Pyramid: Layer 1, 2]
**Directory**: `05-production-batch-evaluation/`

Evaluate production traffic at scale:
- Export OTEL traces from agent runtime logs
- Classify tool calls by category (READ vs WRITE)
- Run batch evaluation with the same evaluators from Module 2
- Detect drift by comparing production scores against Module 2 baselines
- Close the feedback loop: production failures become new offline test cases

---

## Evaluation & Observability Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Production Evaluation Pipeline                             │
│                                                                              │
│  ┌──────────────────┐                                                       │
│  │ Agent Runtime    │                                                       │
│  │  Log Groups      │  OTEL traces automatically captured                   │
│  │ (OTEL Events)    │                                                       │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           │  CloudWatch Logs Subscription                                   │
│           ▼                                                                  │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │ Kinesis Firehose │────▶│   S3 Bucket      │────▶│   Batch Eval     │    │
│  │ (Real-time)      │     │ (Historical)     │     │  (Strands Eval)  │    │
│  └──────────────────┘     └──────────────────┘     └────────┬─────────┘    │
│                                                              │              │
│                              ┌───────────────────────────────┼──────────┐   │
│                              │                               │          │   │
│                              ▼                               ▼          ▼   │
│                       ┌──────────┐              ┌──────────────┐  ┌────────┐│
│                       │   S3     │              │  CloudWatch  │  │ Alerts ││
│                       │ Results  │              │   Metrics    │  │        ││
│                       └──────────┘              └──────────────┘  └────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Custom Evaluators

The workshop teaches you to build domain-specific evaluators:

| Evaluator | What It Measures | Example Criteria |
|-----------|------------------|------------------|
| **Goal Success** | Did the agent complete the task? | Request fully addressed, accurate information |
| **Tool Accuracy** | Was the correct tool invoked? | Search query → search_products tool |
| **Access Control** | Does RBAC work correctly? | Customer blocked from admin tools |
| **Policy Compliance** | Does it follow business rules? | 30-day return policy, security guidelines |
| **Response Quality** | Overall quality score | Clear, professional, complete |
| **Customer Satisfaction** | Predicted CSAT | Issue resolved, low effort |

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

1. **Evaluation is not optional** - Systematic testing prevents production failures
2. **Observability enables improvement** - You can't fix what you can't see
3. **AgentCore simplifies operations** - Focus on agent logic, not infrastructure
4. **OTEL traces reveal behavior** - See exactly which tools agents call and why
5. **Batch evaluation closes the loop** - Drift detection and feedback from production back to offline testing


---

## Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)

---

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
