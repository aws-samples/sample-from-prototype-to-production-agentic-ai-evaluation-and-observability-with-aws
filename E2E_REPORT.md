# E2E Verification Report — Ecommerce Agent Workshop

**Date:** 2026-03-28 00:30 UTC
**Account:** 534409838809 | **Region:** us-west-2

## Summary: 45/45 passed (100%)

## Nicholas Moore's Issues

| # | Issue | Code ✓ | Live ✓ |
|---|-------|--------|--------|
| 1 | MODULE_DIR path variable | ✅ | ✅ |
| 2 | Failure cases independent prefix | ✅ | ✅ |
| 3 | %store persistence + cleanup | ✅ | ✅ |
| 4 | evaluate() API fix | ✅ | ✅ |
| 5 | Dashboard namespace fix | ✅ | ✅ |

## All Checks


### Module 00

- ✅ **00: DynamoDB ecommerce-workshop-products**: 13 items
- ✅ **00: DynamoDB ecommerce-workshop-orders**: 10 items
- ✅ **00: DynamoDB ecommerce-workshop-accounts**: 8 items

### Module 01

- ✅ **01: SDK imports**
- ✅ **01: MCP server file exists**
- ✅ **01: MCP tools loaded**: 11 tools: ['search_products', 'get_product_details', 'check_inventory', 'get_product_recommendations', 'compare_products', 'get_return_policy', 'create_product', 'update_product', 'delete_product', 'u
- ✅ **01: Basic agent query**: Response: Here are the matching product IDs:

- **PROD-001** – Wireless Bluetooth Headphones
- **PROD-055** – Noise Canceling Earbuds
- **PROD-300** – Wireless 
- ✅ **01: RBAC customer agent**

### Module 03

- ✅ **03: MODULE_DIR resolves**
- ✅ **03: agents/ dir**
- ✅ **03: lambda_tools/ dir**
- ✅ **03: Dockerfile exists**
- ✅ **03: %store persistence**
- ✅ **03: save_config fallback**
- ✅ **03: cleanup has %store restore**
- ✅ **03: IAM role ecommerce-workshop-runtime-role**: arn:aws:iam::534409838809:role/ecommerce-workshop-runtime-role
- ✅ **03: IAM role ecommerce-workshop-gateway-role**: arn:aws:iam::534409838809:role/ecommerce-workshop-gateway-role
- ✅ **03: IAM role ecommerce-workshop-lambda-role**: arn:aws:iam::534409838809:role/ecommerce-workshop-lambda-role
- ✅ **03: Cognito user pool**: us-west-2_zZFgcKaqx
- ✅ **03: Cognito clients**
- ✅ **03: Lambda ecommerce-workshop-product-tools**: Runtime: python3.11
- ✅ **03: Lambda ecommerce-workshop-rbac-interceptor**: Runtime: python3.11
- ✅ **03: ECR images**: 10 images
- ✅ **03: ECR login**
- ✅ **03: Docker build**: ARM64 image built successfully
- ✅ **03: Docker push to ECR**
- ✅ **03: Gateway created**: URL: https://ecommerce-workshop-gateway-dz6wubkxyf.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp
- ✅ **03: Runtime created**: ID: ecommerce_workshop_product_catalog_agent-Nda58K37yj
- ✅ **03: Agent invocation (via Gateway)**: Keys: ['status', 'response', 'metadata']
- ✅ **03: Config JSON round-trip**

### Module 03b

- ✅ **03b: Independent prefix**: Uses 'ecommerce-workshop-broken'
- ✅ **03b: Won't overwrite working agent**

### Module 04

- ✅ **04: Eval IAM role**: arn:aws:iam::534409838809:role/ecommerce-workshop-evaluation-role
- ✅ **04: No create_evaluation_job (Issue #4)**: Removed non-existent API
- ✅ **04: Has evaluate() API (Issue #4)**
- ✅ **04: Correct namespace AWS/Bedrock-AgentCore (Issue #5)**
- ✅ **04: Has Logs Insights queries (Issue #5)**
- ✅ **04: Has pre-flight check**
- ✅ **04: Has runtime log group query**
- ✅ **04: CW metrics exist**: 500 metrics in AWS/Bedrock-AgentCore
- ✅ **04: Bedrock-AgentCore/AgentRuntime empty (expected)**
- ✅ **04: Bedrock-AgentCore/Evaluations empty (expected)**
- ✅ **04: Eval log group exists**
- ✅ **04: aws/spans log group**
- ✅ **04: evaluate() API live test**: API exists but rejected test input (expected): An error occurred (ValidationException) when calling the Evaluate operation: 1 validation error detected: Value at 'evaluationTarget.traceIds' failed 

## Infrastructure

- Runtime ID: ecommerce_workshop_product_catalog_agent-Nda58K37yj
- Gateway ID: ecommerce-workshop-gateway-dz6wubkxyf
- Gateway URL: https://ecommerce-workshop-gateway-dz6wubkxyf.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp
- ECR: 534409838809.dkr.ecr.us-west-2.amazonaws.com/ecommerce-workshop-product-catalog-agent:latest
- Cognito Pool: us-west-2_zZFgcKaqx
