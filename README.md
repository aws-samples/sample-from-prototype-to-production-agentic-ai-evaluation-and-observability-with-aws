# E-Commerce Customer Service Multi-Agent Workshop

## Production-Grade Agentic AI: From Prototype to Production with AWS

This hands-on workshop guides you through building, evaluating, deploying, and continuously improving a production-ready multi-agent customer service system using AWS services.

---

## Workshop Overview

| Item | Details |
|------|---------|
| **Duration** | 4 hours |
| **Level** | Intermediate |
| **Use Case** | E-Commerce Customer Service |
| **Architecture** | Multi-Agent with Cost-Optimized LLM Strategy |

### What You'll Build

A multi-agent customer service system that handles:
- **Order inquiries**: Status, tracking, returns, modifications
- **Product questions**: Search, recommendations, comparisons
- **Account management**: Profile updates, payment methods, preferences

### Key Learning Outcomes

1. Build multi-agent systems with Strands SDK using mixed LLM strategy (cost optimization)
2. Evaluate agents with synthetic datasets and custom evaluators
3. Deploy to production with AgentCore Runtime, Gateway, and Memory
4. Configure online evaluation for continuous monitoring
5. Detect and respond to agent drift/degradation
6. Implement safe deployment practices (shadow testing, canary)

---

## Architecture

```
                              ┌─────────────────────────────────┐
                              │     Customer Request            │
                              └─────────────┬───────────────────┘
                                            │
                              ┌─────────────▼───────────────────┐
                              │   ORCHESTRATOR AGENT            │
                              │   (Claude Sonnet 4.5)           │
                              │   • Intent classification       │
                              │   • Complex query handling      │
                              │   • Agent coordination          │
                              └─────────────┬───────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │                             │                             │
    ┌─────────▼─────────┐       ┌──────────▼──────────┐       ┌─────────▼─────────┐
    │   ORDER AGENT     │       │   PRODUCT AGENT     │       │   ACCOUNT AGENT   │
    │ (Claude Haiku 4.5)│       │ (Claude Haiku 4.5)  │       │ (Claude Haiku 4.5)│
    │                   │       │                     │       │                   │
    │ • Order status    │       │ • Product search    │       │ • Profile update  │
    │ • Tracking        │       │ • Recommendations   │       │ • Password reset  │
    │ • Returns/Refunds │       │ • Inventory check   │       │ • Payment methods │
    └─────────┬─────────┘       └──────────┬──────────┘       └─────────┬─────────┘
              │                            │                            │
              ▼                            ▼                            ▼
    ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
    │   Orders DB     │         │   Products KB   │         │   Accounts DB   │
    │   (DynamoDB)    │         │   (Bedrock KB)  │         │   (DynamoDB)    │
    └─────────────────┘         └─────────────────┘         └─────────────────┘
```

---

## Workshop Modules

### Module 1: Multi-Agent Prototype (60 min)
**Notebook**: `01-multi-agent-prototype/01-multi-agent-prototype.ipynb`

- Build specialized sub-agents with Claude Haiku 4.5 (cost-efficient)
- Create orchestrator agent with Claude Sonnet 4.5 (reasoning)
- Implement real tools connecting to DynamoDB and Bedrock KB
- Compare cost: All-Sonnet vs Mixed architecture

### Module 2: Evaluation & Baseline Testing (60 min)
**Notebook**: `02-evaluation-baseline/02-evaluation-baseline.ipynb`

- Run evaluation with synthetic dataset (200+ test cases)
- Use built-in evaluators: GoalSuccess, ToolSelection, Correctness
- Create custom evaluators for policy compliance and routing accuracy
- Establish baseline metrics for production comparison

### Module 3: Production Deployment with AgentCore (60 min)
**Notebook**: `03-production-deployment/03-production-deployment.ipynb`

- Deploy to AgentCore Runtime
- Configure AgentCore Gateway for MCP tool integration
- Set up AgentCore Memory for conversation persistence
- Configure observability with CloudWatch

### Module 4: Online Evaluation & Continuous Improvement (60 min)
**Notebook**: `04-online-eval-improvement/04-online-eval-improvement.ipynb`

- Configure online evaluation with sampling
- Simulate drift scenarios (new products, policy changes)
- Collect and analyze failed samples from traces
- Improve agent and validate with safe deployment practices

---

## Pre-built Resources (Provided by Workshop)

| Resource | Type | Description |
|----------|------|-------------|
| **Orders Database** | DynamoDB | 10,000 synthetic orders |
| **Products Knowledge Base** | Bedrock KB | 500+ products with specs |
| **Accounts Database** | DynamoDB | 1,000 customer profiles |
| **Evaluation Dataset** | JSON | 200+ test cases |
| **Drift Scenarios** | JSON | Pre-defined degradation tests |

---

## Prerequisites

### AWS Services Required
- Amazon Bedrock (Claude Sonnet 4.5, Claude Haiku 4.5)
- Amazon Bedrock Knowledge Bases
- Amazon DynamoDB
- Amazon Bedrock AgentCore (Runtime, Gateway, Memory, Evaluation)
- Amazon CloudWatch
- AWS IAM

### Model Access
Enable the following models in Amazon Bedrock (using global cross-region inference):
- `global.anthropic.claude-sonnet-4-5-20250929-v1:0` (Orchestrator)
- `global.anthropic.claude-haiku-4-5-20251001-v1:0` (Sub-agents)

### Python Dependencies
```bash
pip install -r 00-prerequisites/requirements.txt
```

---

## Quick Start

1. **Verify Infrastructure** (pre-deployed by Workshop Studio)
   ```bash
   cd 00-prerequisites
   python verify_infrastructure.py
   ```

2. **Run Module 1**: Build the multi-agent prototype
3. **Run Module 2**: Evaluate and establish baseline
4. **Run Module 3**: Deploy to production
5. **Run Module 4**: Monitor, detect drift, and improve

---

## Cost Optimization Results

Using Claude Sonnet 4.5 and Haiku 4.5 with global cross-region inference:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude Sonnet 4.5 | $3.00 | $15.00 |
| Claude Haiku 4.5 | $0.80 | $4.00 |

| Architecture | Avg Tokens/Request | Cost/1000 Requests | Savings |
|--------------|-------------------|-------------------|---------|
| All Sonnet 4.5 | ~4,500 | ~$0.081 | - |
| Sonnet 4.5 + Haiku 4.5 (this workshop) | ~3,700 mixed | ~$0.040 | **~50%** |

*Pricing from [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) - verify for latest rates*

---

## Cleanup

After completing the workshop:
```bash
cd cleanup
./cleanup.sh
```

---

## Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [AWS Workshop Studio](https://workshops.aws/)
