# E-Commerce Agent Workshop

## Project Overview

This is a hands-on 2-hour AWS workshop that teaches developers how to build production-ready AI agents using AWS Bedrock AgentCore. The workshop demonstrates the complete lifecycle: prototype → evaluate → deploy → monitor → improve.

**Core Problem**: Most AI agent projects fail in production not due to technical issues, but because teams lack systematic evaluation, monitoring, and improvement practices.

**Target Audience**: Intermediate developers familiar with Python, AWS, and basic AI concepts.

## Technology Stack

### AI & Agent Frameworks

- **Strands Agents SDK**: Primary framework for building AI agents
- **AWS Bedrock**: LLM service (Claude Haiku 4.5 for agents, Sonnet 4.5 for evaluation)
- **AWS Bedrock AgentCore**: Production runtime, gateway, and identity services
- **Model Context Protocol (MCP)**: Tool integration standard via FastMCP servers

### Observability & Evaluation

- **OpenTelemetry (OTEL)**: Distributed tracing (auto-instrumented)
- **Strands Evaluation SDK**: LLM-based evaluators for quality metrics
- **AWS CloudWatch**: Log aggregation and trace storage

### Infrastructure

- **AWS CDK**: Infrastructure as Code (Python)
- **AWS Lambda**: Serverless tool execution
- **Amazon DynamoDB**: Backend data (Products, Orders, Accounts)
- **AWS Cognito**: JWT-based authentication with RBAC
- **Docker**: ARM64 containers for AgentCore Runtime

### Development Tools

- **Jupyter Notebooks**: Interactive learning environment
- **Streamlit**: Web UI for testing agents

## Project Structure

```
ecommerce-agent-workshop/
├── 00-prerequisites/           # Setup, AWS infrastructure (CDK), sample data
├── 01-single-agent-prototype/  # Module 1: Local agent with RBAC (25 min)
├── 02-evaluation-baseline/     # Module 2: Custom evaluators & baselines
├── 03-production-deployment/   # Module 3: Deploy to AgentCore (20 min)
├── 04-online-eval-observability/ # Module 4: Monitor with OTEL (25 min)
├── 05-production-batch-evaluation/ # Module 5: Scale evaluation (30 min)
└── cleanup/                    # Teardown scripts
```

### Key Files by Module

**Module 1 - Prototype**

- `01-single-agent-prototype/agents/product_catalog_agent.py` - Single agent with tool filtering RBAC
- `01-single-agent-prototype/mcp_servers/product_mcp_server.py` - FastMCP server (11 tools: 6 read + 5 admin)

**Module 2 - Evaluation**

- `02-evaluation-baseline/custom_evaluators.py` - 4 evaluators (routing, policy, quality, satisfaction)
- `02-evaluation-baseline/evaluation_dataset.json` - 100+ test cases with expected outputs

**Module 3 - Production**

- `03-production-deployment/agents/product_catalog_agent.py` - BedrockAgentCoreApp version
- `03-production-deployment/lambda_tools/product_tools_lambda.py` - Lambda MCP tools
- `03-production-deployment/lambda_tools/rbac_interceptor_lambda.py` - Gateway RBAC enforcement
- `03-production-deployment/agents/Dockerfile` - ARM64 container with OTEL

**Module 4 - Observability**

- `04-online-eval-observability/agents/orchestrator_agent.py` - Multi-agent orchestrator

**Module 5 - Batch Evaluation**

- `05-production-batch-evaluation/custom_evaluators.py` - 6 evaluators (extended for multi-agent)

## Architecture Patterns

### Module 1: Single Agent Architecture

```
User (customer/admin role)
  → Product Catalog Agent (Claude Haiku 4.5)
    → MCP Tools (filtered by role)
      → DynamoDB (products, inventory, pricing)
```

### Module 3: Production Architecture

```
Cognito User Pool (JWT)
  ↓
AgentCore Gateway (RBAC interceptor Lambda)
  ↓
AgentCore Runtime (containerized agent)
  ↓
Lambda MCP Tools (product_tools_lambda)
  ↓
DynamoDB
  ↓
[Auto-instrumented OTEL] → CloudWatch Logs/Traces
```

### Module 5: Evaluation Pipeline

```
Agent Runtime (OTEL traces)
  ↓
CloudWatch Logs
  ↓
Kinesis Firehose
  ↓
S3 (historical data)
  ↓
Batch Evaluation (Strands Evals)
  ↓
S3 Results + CloudWatch Metrics
```

## Key Concepts

### RBAC Implementation

**Local (Module 1):**

- `UserSession` dataclass with role field
- Tool filtering at initialization: `get_tools_for_role()`
- Role-aware system prompts

**Production (Module 3):**

- JWT tokens from Cognito with `cognito:groups` claim
- Gateway interceptor validates role on tool calls
- Same tool filtering pattern

### Custom Evaluators

**Module 2 Evaluators:**

1. **RoutingAccuracyEvaluator** - Correct agent routing (0-1 scale)
2. **PolicyComplianceEvaluator** - Business rules (30-day returns, shipping, security)
3. **ResponseQualityEvaluator** - Helpful, accurate, complete, clear, professional
4. **CustomerSatisfactionEvaluator** - Predicts CSAT (resolution + effort)

**Module 5 Evaluators** (extended):

- Added GoalSuccessEvaluator
- Added HelpfulnessEvaluator
- Maintains other evaluators for comprehensive scoring

### Data Models

**Products Table:**

- Fields: product_id, name, category, price, inventory, specifications, return_policy
- Tools: search, get_details, check_inventory, compare, recommend (customer)
- Admin tools: create, update, delete, manage pricing

**Orders Table:**

- Fields: order_id, customer_email, status, items, total, tracking
- GSI: customer-email-index

**Accounts Table:**

- Fields: customer_id, email, addresses, payment_methods, membership_level
- GSI: email-index

## Common Workflows

### Initial Setup

```bash
# Navigate to prerequisites
cd 00-prerequisites

# Deploy AWS infrastructure
python setup_infrastructure.py

# Verify setup
jupyter notebook 0-environment-setup.ipynb
```

### Module Progression

1. **Module 1** (25 min): Build single agent with RBAC
2. **Module 2**: Establish evaluation baseline
3. **Module 3** (20 min): Deploy to AgentCore with observability
4. **Module 4** (25 min): Monitor production traces
5. **Module 5** (30 min): Batch evaluate at scale

### Testing Patterns

**Local Testing:**

```python
from agents.product_catalog_agent import ProductCatalogAgent
from user_session import UserSession

# Test as customer
session = UserSession(user_id="user123", role="customer")
agent = ProductCatalogAgent(session)
response = agent.run("Show me laptops under $1000")

# Test as admin
admin_session = UserSession(user_id="admin", role="admin")
admin_agent = ProductCatalogAgent(admin_session)
response = admin_agent.run("Update price for product LAPTOP-001 to $899")
```

**Production Testing:**

```python
from bedrock_agentcore import BedrockAgentCoreApp

# Initialize with Cognito token
app = BedrockAgentCoreApp(
    gateway_id="gateway-123",
    access_token="Bearer eyJ...",  # Cognito JWT
    trace_mode="console"  # or "cloudwatch"
)
response = app.run("What laptops do you have?")
```

### Evaluation Pattern

```python
from strands.evals import Evaluator, EvaluationRun
from custom_evaluators import ResponseQualityEvaluator

# Create evaluator
evaluator = ResponseQualityEvaluator()

# Run evaluation
run = EvaluationRun(
    agent=agent,
    dataset=test_cases,
    evaluators=[evaluator],
    model="claude-sonnet-4-5-20251101"
)
results = run.execute()
```

## Important Conventions

### Code Style

- Use dataclasses for structured data (UserSession, ProductInfo, etc.)
- Type hints for function signatures
- Descriptive variable names (no abbreviations)
- Clear separation: agents/ mcp_servers/ utils/ lambda_tools/

### Agent Patterns

- System prompts define agent personality and policies
- Tool filtering enforces RBAC at initialization
- MCP servers expose tools via FastMCP
- Use `BedrockAgentCoreApp` for production deployment

### Deployment Patterns

- Dockerfiles use ARM64 for Lambda compatibility
- Lambda functions implement MCP protocol
- Gateway interceptors validate JWT claims
- OTEL auto-instrumentation via BedrockAgentCoreApp

### Evaluation Best Practices

- Establish baselines before deployment (Module 2)
- Monitor production with OTEL traces (Module 4)
- Batch evaluate historical data (Module 5)
- Use domain-specific evaluators (not just generic LLM metrics)

## AWS Resources Created

**CDK Stack** (`EcommerceWorkshopStack`):

- DynamoDB tables: Products, Orders, Accounts
- SSM parameters for table names
- Sample data loading via custom resources

**AgentCore Resources**:

- Gateway with RBAC interceptor
- Runtime with agent container
- Lambda tools (product_tools, rbac_interceptor)
- Cognito user pool with customer/admin groups

**Observability**:

- CloudWatch log groups for OTEL traces
- Kinesis Firehose for S3 archival
- S3 buckets for evaluation results

## Troubleshooting

### Common Issues

**Agent not finding tools:**

- Verify MCP server is running locally
- Check Lambda function deployment status (production)
- Confirm tool filtering allows role access

**RBAC failures:**

- Verify JWT token contains `cognito:groups` claim
- Check interceptor Lambda logs in CloudWatch
- Confirm user is in correct Cognito group

**OTEL traces missing:**

- Ensure `BedrockAgentCoreApp` has `trace_mode="cloudwatch"`
- Check CloudWatch log group permissions
- Verify OTEL environment variables in Dockerfile

**Evaluation failures:**

- Confirm Claude Sonnet 4.5 model access
- Check evaluation dataset format (JSON with expected_output)
- Verify evaluator model_name matches available models

## Learning Outcomes

By completing this workshop, developers learn:

1. **Agent Architecture**: Build agents with MCP tools and RBAC
2. **Evaluation Rigor**: Create custom evaluators and establish baselines
3. **Production Deployment**: Use AgentCore for scalable, secure agent hosting
4. **Observability**: Leverage OTEL for production monitoring
5. **Continuous Improvement**: Analyze traces at scale to identify issues

## Key Takeaways

- Evaluation is NOT optional for production agents
- Observability enables data-driven improvement
- AgentCore simplifies operations (auth, scaling, monitoring)
- Tool calls reveal agent routing and decision-making
- Batch evaluation scales more efficiently than online evaluation

## Additional Resources

- Strands Agents SDK: [Documentation](https://docs.strands.ai)
- AWS Bedrock AgentCore: [User Guide](https://docs.aws.amazon.com/bedrock)
- Model Context Protocol: [Specification](https://modelcontextprotocol.io)
- OpenTelemetry: [Python SDK](https://opentelemetry.io/docs/languages/python)

## Cleanup

To tear down all AWS resources:

```bash
cd cleanup
python cleanup.py
```

This removes:

- AgentCore Gateway, Runtime, Lambda tools
- Cognito user pool
- DynamoDB tables
- CloudWatch log groups
- S3 buckets (evaluation results)
- CDK stack
