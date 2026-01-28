# From Prototype to Production with AWS
## Agentic AI Evaluation and Observability Workshop

Transform your AI agents from promising prototypes into production-ready systems. This hands-on workshop teaches you to build, evaluate, deploy, and continuously monitor multi-agent systems using AWS Bedrock AgentCore.

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
| **Duration** | 2 hours |
| **Level** | Intermediate |
| **Use Case** | E-Commerce Customer Service |
| **Focus** | Evaluation, Observability & Production Readiness |

### What You'll Build

A production-ready multi-agent customer service system with:
- **Multi-agent orchestration** - Specialized agents for orders, products, and accounts
- **Comprehensive evaluation** - Custom evaluators for quality, routing, and compliance
- **Full observability** - OTEL tracing, CloudWatch metrics, and batch evaluation
- **Production deployment** - AWS Bedrock AgentCore with gateway and runtime

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

1. **Build** multi-agent systems with Strands SDK using cost-optimized LLM routing
2. **Evaluate** agents systematically with custom evaluators (routing, compliance, quality)
3. **Deploy** to production with AgentCore Runtime and Gateway
4. **Observe** agent behavior through OTEL traces and CloudWatch metrics
5. **Analyze** production traffic with batch evaluation pipelines

---

## Multi-Agent Architecture

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
    └───────────────────┘       └─────────────────────┘       └───────────────────┘
```

---

## Workshop Modules

### Module 1: Multi-Agent Prototype (20 min)
**Directory**: `01-multi-agent-prototype/`

Build a working multi-agent system locally:
- Create specialized sub-agents with Claude Haiku 4.5 (cost-efficient)
- Build orchestrator agent with Claude Sonnet 4.5 (reasoning)
- Implement tools connecting to mock data stores
- Test the complete agent flow

### Module 2: Evaluation & Baseline (25 min)
**Directory**: `02-evaluation-baseline/`

Establish quality baselines before deployment:
- Define custom evaluators for your use case:
  - **Goal Success** - Did the agent address the request?
  - **Routing Accuracy** - Was the correct sub-agent invoked?
  - **Policy Compliance** - Does the response follow business rules?
  - **Response Quality** - Is the output helpful and accurate?
- Run evaluation with synthetic test cases
- Analyze results and identify improvement areas

### Module 3: Production Deployment (20 min)
**Directory**: `03-production-deployment/`

Deploy agents to AWS with full observability:
- Package agents for AgentCore Runtime
- Configure AgentCore Gateway for MCP tools
- Deploy with auto-instrumented OTEL tracing
- Verify deployment with test invocations

### Module 4: Online Observability (25 min)
**Directory**: `04-online-eval-observability/`

Monitor agents in production:
- View OTEL traces in CloudWatch
- Analyze agent behavior patterns
- Build a Streamlit dashboard for real-time monitoring
- Understand trace structure and tool call visibility

### Module 5: Production Batch Evaluation (30 min)
**Directory**: `05-production-batch-evaluation/`

Evaluate production traffic at scale:
- Export OTEL traces from agent runtime logs
- Extract actual tool calls from trace events
- Run batch evaluation with the same evaluators from Module 2
- Store results to S3 and CloudWatch metrics
- Identify trends and regression patterns

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
| **Helpfulness** | How useful was the response? | Actionable, anticipates follow-ups |
| **Routing Accuracy** | Was the right agent invoked? | Order questions → Order Agent |
| **Policy Compliance** | Does it follow business rules? | 30-day return policy, security guidelines |
| **Response Quality** | Overall quality score | Clear, professional, complete |
| **Customer Satisfaction** | Predicted CSAT | Issue resolved, low effort |

---

## Prerequisites

### AWS Services Required
- Amazon Bedrock (Claude Sonnet 4.5, Claude Haiku 4.5)
- Amazon Bedrock AgentCore (Runtime, Gateway)
- Amazon CloudWatch
- Amazon S3
- Amazon Kinesis Firehose
- AWS IAM

### Model Access
Enable in Amazon Bedrock console (using global cross-region inference):
- `global.anthropic.claude-sonnet-4-5-20250929-v1:0`
- `global.anthropic.claude-haiku-4-5-20251001-v1:0`

### Python Dependencies
```bash
pip install strands-agents strands-agents-evals boto3 pandas streamlit
```

---

## Quick Start

```bash
# 1. Clone and setup
cd ecommerce-agent-workshop
pip install -r requirements.txt

# 2. Verify AWS access
aws sts get-caller-identity

# 3. Run modules in order
# Module 1 → Module 2 → Module 3 → Module 4 → Module 5
```

---

## Key Takeaways

After completing this workshop, you'll understand:

1. **Evaluation is not optional** - Systematic testing prevents production failures
2. **Observability enables improvement** - You can't fix what you can't see
3. **AgentCore simplifies operations** - Focus on agent logic, not infrastructure
4. **Tool calls reveal routing** - OTEL traces show exactly what agents do
5. **Batch evaluation scales** - Evaluate thousands of traces efficiently


---

## Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)

---

## License

This workshop is provided for educational purposes. See LICENSE file for details.
