# Failure Cases for AWS Bedrock AgentCore Observability Workshop

This directory contains an intentionally broken version of the production e-commerce agent deployment. The goal is to teach workshop attendees how to use **AWS Bedrock AgentCore Observability** (CloudWatch Logs, OTEL traces, and structured logging) to diagnose and remediate common production failures.

## Overview

Each failure case represents a real-world production issue that can't be caught by traditional testing alone. Attendees will:

1. **Experience the failure** through the Streamlit app
2. **Use observability tools** to diagnose the root cause
3. **Apply the fix** based on their findings
4. **Verify the resolution** with the same test scenario

---

## Failure Case 1: Poor Tool Metadata

### Description

Tools have vague or generic names and descriptions that confuse the LLM's tool selection logic:

- `search` has a vague description: "Find items" (doesn't specify what items or that it searches products)
- **THREE tools have IDENTICAL descriptions**: "Get information about a product"
  - `get_product_details`
  - `check_inventory`
  - `compare_products`

The LLM cannot distinguish between these tools, leading to incorrect tool selection.

### Symptoms

- Agent returns "no results found" when products clearly exist
- Agent calls the wrong tool (e.g., `check_inventory` instead of `get_product_details`)
- Results look plausible but are incorrect or incomplete
- Subtle failures that don't throw obvious errors

### Manual Test Scenario

**Test Scenario 1 - Vague Search Tool:**

```
User: "Search for wireless headphones under $100"
Expected: Agent uses search tool and returns relevant products
Actual: Agent may not use any tool, or uses wrong tool because "Find items" is too vague
```

**Test Scenario 2 - Identical Descriptions:**

```
User: "Show me details about product LAPTOP-001"
Expected: Agent uses get_product_details tool (returns full product info)
Actual: Agent randomly picks get_product_details, check_inventory, or compare_products
        because all three have identical descriptions. May return only stock quantity
        instead of full product details.
```

**Test Scenario 3 - Identical Descriptions:**

```
User: "Compare LAPTOP-001 and LAPTOP-002"
Expected: Agent uses compare_products tool
Actual: Agent may use get_product_details or check_inventory instead because
        all have the same description
```

### Diagnosis with Observability

**CloudWatch Logs:**

```bash
# Search for tool invocations
aws logs filter-log-events \
  --log-group-name /aws/bedrock-agentcore/runtimes/... \
  --filter-pattern "Tool invoked"
```

Look for:

- `Tool invoked: search` instead of `search_products`
- Missing tool invocations when they should have occurred
- Wrong tool selected (e.g., `check_inventory` when `get_product_details` was needed)

**OTEL Traces:**

Navigate to X-Ray console → Traces:

- Look for tool call spans
- Check `tool.name` attribute - may show generic "search" instead of specific tool
- Compare tool names in successful vs failed requests
- Note missing tool invocation spans

**Key Log Entries:**

```
Tool names: ['search', 'get_product_details', 'check_inventory', ...]
Tool invoked: search with params: {'query': 'wireless headphones'}
```

### Root Cause

**Files to inspect:**

1. **`utils.py` (lines 928-990)** - Tool schema definitions
   - Line 930: `"description": "Find items"` is too vague - doesn't specify products
   - **Lines 944, 955, 978**: THREE IDENTICAL descriptions cause LLM confusion:
     - Line 944: `get_product_details` - "Get information about a product"
     - Line 955: `check_inventory` - "Get information about a product" (IDENTICAL)
     - Line 978: `compare_products` - "Get information about a product" (IDENTICAL)

2. **`lambda_tools/product_tools_lambda.py` (line 690)** - Tool routing
   - Line 690: `"search": search_products` should be `"search_products": search_products`

3. **`agents/product_catalog_agent.py` (line 40)** - Tool filtering
   - Line 40: `"search"` in CUSTOMER_TOOLS should be `"search_products"`

### Fix Implementation

**Step 1: Fix tool schema in `utils.py`**

```python
{
    "name": "search_products",  # Changed from "search"
    "description": "Search for products in the catalog using keywords and optional category filter",  # Made specific - mentions "products" and "catalog"
    ...
},
{
    "name": "get_product_details",
    "description": "Get detailed information about a specific product including name, price, description, specifications, and warranty",  # Made specific and distinct
    ...
},
{
    "name": "check_inventory",
    "description": "Check current inventory levels and stock availability for a product",  # Made specific and distinct - focuses on inventory/stock
    ...
},
{
    "name": "compare_products",
    "description": "Compare multiple products side by side (2-5 products)",  # Made specific
    ...
}
```

**Step 2: Fix tool routing in `lambda_tools/product_tools_lambda.py`**

```python
TOOLS = {
    "search_products": search_products,  # Changed from "search"
    ...
}
```

**Step 3: Fix tool list in `agents/product_catalog_agent.py`**

```python
CUSTOMER_TOOLS = [
    "search_products",  # Changed from "search"
    ...
]
```

### Verification

Redeploy and retest with the same scenarios. CloudWatch logs should now show:

```
Tool names: ['search_products', 'get_product_details', 'check_inventory', ...]
Tool invoked: search_products with params: {'query': 'wireless headphones'}
```

---

## Failure Case 2: Tool Parameter Schema Mismatch

### Description

The `update_inventory` tool has a parameter type mismatch:

- Schema defines `new_quantity` as `{"type": "integer"}`
- Description says "New stock level" (vague - doesn't clarify it must be a number)
- LLM may pass strings like "five", "100 units", "low stock"
- Lambda receives malformed parameters and fails

### Symptoms

- Tool calls fail with type errors
- Lambda returns 500 errors
- Admin operations report "Error updating inventory"
- Silent failures or validation errors

### Manual Test Scenario

**Test as Admin:**

```
User: "Set inventory for LAPTOP-001 to one hundred units"
Expected: Inventory updated to 100
Actual: Error - Lambda receives "one hundred units" as string, type validation fails
```

**Test as Admin:**

```
User: "Update stock for PROD-055 to low"
Expected: Should fail gracefully or ask for clarification
Actual: Lambda throws TypeError
```

### Diagnosis with Observability

**CloudWatch Logs:**

```bash
# Search for Lambda errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/product_tools_lambda \
  --filter-pattern "error"
```

Look for:

- `TypeError: argument must be int, not str`
- `Executing tool: update_inventory with args: {'product_id': 'LAPTOP-001', 'new_quantity': 'one hundred'}`
- `Lambda error: TypeError`

**OTEL Traces:**

In X-Ray console:

- Find failed tool invocation spans with status `ERROR`
- Check `tool.parameters` attribute - shows malformed input
- Response status code: 500
- Error message in span attributes

**Key Log Entries:**

```
Executing tool: update_inventory with args: {'product_id': 'LAPTOP-001', 'new_quantity': 'one hundred units'}
Lambda error: TypeError: 'str' object cannot be interpreted as an integer
Tool update_inventory completed successfully: False
```

### Root Cause

**Files to inspect:**

1. **`utils.py` (line 1051)** - Tool parameter schema
   - Description is too vague: `"New stock level"`
   - Should be: `"New stock quantity (must be an integer number)"`

2. **`lambda_tools/product_tools_lambda.py` (line 550)** - Function signature
   - Function expects `new_quantity: int` but receives string from LLM

### Fix Implementation

**Step 1: Fix parameter description in `utils.py`**

```python
{
    "name": "update_inventory",
    "description": "Update inventory levels for a product (admin only)",
    "inputSchema": {
        "type": "object",
        "properties": {
            "product_id": {"type": "string", "description": "Product ID"},
            "new_quantity": {
                "type": "integer",
                "description": "New stock quantity (must be a positive integer number, e.g., 100)"
            },
            "restock_date": {"type": "string", "description": "Restock date (YYYY-MM-DD)"}
        },
        "required": ["product_id", "new_quantity"]
    }
}
```

**Optional: Add validation in Lambda function**

```python
def update_inventory(product_id: str, new_quantity: int, restock_date: str = None) -> dict:
    try:
        # Add explicit type validation
        if not isinstance(new_quantity, int):
            logger.warning(f"Invalid type for new_quantity: {type(new_quantity)} - attempting conversion")
            try:
                new_quantity = int(new_quantity)
            except (ValueError, TypeError):
                return {
                    "success": False,
                    "error": f"new_quantity must be an integer, received: {new_quantity}"
                }
        ...
```

### Verification

Redeploy and retest. CloudWatch logs should show:

```
Executing tool: update_inventory with args: {'product_id': 'LAPTOP-001', 'new_quantity': 100}
Tool update_inventory completed successfully: True
```

---

## Failure Case 3: Wrong Model ID (Deprecated Model)

### Description

The agent is configured with an incorrect or deprecated model ID:

- Current: `anthropic.claude-3-5-haiku-20241022-v1:0` (deprecated)
- Should be: `global.anthropic.claude-haiku-4-5-20251001-v1:0`

This causes:

- Agent fails to start
- Model invocation errors
- Poor tool calling performance (if fallback occurs)
- Runtime health check failures

### Symptoms

- Agent returns 500 errors immediately
- No tool calls are executed
- CloudWatch shows Bedrock `ValidationException`
- Runtime status shows `FAILED` or repeated restarts

### Manual Test Scenario

**Test as Customer or Admin:**

```
User: "Show me laptops under $1000"
Expected: Agent searches and returns results
Actual: Error - "Unable to invoke agent" or "Model invocation failed"
```

### Diagnosis with Observability

**CloudWatch Logs:**

```bash
# Search for model initialization errors
aws logs filter-log-events \
  --log-group-name /aws/bedrock-agentcore/runtimes/... \
  --filter-pattern "model"
```

Look for:

- `Initializing model: anthropic.claude-3-5-haiku-20241022-v1:0`
- `ValidationException: Could not resolve the foundation model`
- `ResourceNotFoundException: Model not found`
- `Agent error: ValidationException`

**OTEL Traces:**

In X-Ray console:

- Look for failed spans at the model invocation level
- Status: `ERROR`
- Error message: "ValidationException: Could not resolve the foundation model"
- No tool invocation spans (agent never gets to that stage)

**Key Log Entries:**

```
Initializing model: anthropic.claude-3-5-haiku-20241022-v1:0
Agent error: ValidationException: Could not resolve the foundation model from model identifier: anthropic.claude-3-5-haiku-20241022-v1:0
```

### Root Cause

**File to inspect:**

1. **`agents/product_catalog_agent.py` (line 34)** - Model configuration
   - Line 34: `MODEL_ID = os.environ.get("MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")`
   - This is a deprecated model ID

### Fix Implementation

**Step 1: Fix default model ID in `agents/product_catalog_agent.py`**

```python
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
```

**Step 2: Verify available models in your account**

```bash
aws bedrock list-foundation-models \
  --by-provider anthropic \
  --query 'modelSummaries[?contains(modelId, `haiku`)].modelId'
```

**Step 3: Update environment variable in deployment (if using ENV vars)**

If the model ID is passed via environment variables in the Dockerfile or deployment configuration, update it there as well.

### Verification

Rebuild Docker image and redeploy runtime:

```bash
# Rebuild container
cd 03-production-deployment-with-failure-cases/agents
docker build --platform linux/arm64 -t product-catalog-agent .

# Push to ECR and update runtime
# (deployment steps vary by workshop setup)
```

CloudWatch logs should show:

```
Initializing model: global.anthropic.claude-haiku-4-5-20251001-v1:0
Model initialized successfully
Agent response received - length: 234 chars
```

---

## Failure Case 4: Missing Conversation History (Stateless Agent)

### Description

The agent is completely stateless - it creates a fresh agent instance on every invocation without persisting conversation history:

- Each invocation starts with empty message history
- Agent has no memory of previous turns
- Multi-turn conversations fail completely

This causes:

- Agent asks user to repeat information
- Contradicts previous answers
- Cannot maintain context across turns
- Redundant tool calls

### Symptoms

- User says "What was the price?" and agent responds "What product?"
- Agent re-asks for information already provided
- Cannot follow up on previous queries
- Each response treats conversation as brand new

### Manual Test Scenario

**Test as Customer (Multi-turn):**

```
Turn 1:
User: "Show me details about product LAPTOP-001"
Agent: [Provides details about LAPTOP-001]

Turn 2:
User: "Is that product in stock?"
Expected: Agent knows "that product" refers to LAPTOP-001 from previous turn
Actual: Agent responds "Which product are you referring to?" or "I need a product ID"
```

**Test as Admin (Multi-turn):**

```
Turn 1:
User: "Create a new product PHONE-999 in the Electronics category for $599"
Agent: [Creates product successfully]

Turn 2:
User: "Now set its inventory to 50 units"
Expected: Agent knows to update PHONE-999 inventory
Actual: Agent asks "Which product should I update?" (no memory of PHONE-999)
```

### Diagnosis with Observability

**CloudWatch Logs:**

```bash
# Search for agent initialization
aws logs filter-log-events \
  --log-group-name /aws/bedrock-agentcore/runtimes/... \
  --filter-pattern "Created new agent"
```

Look for:

- `Created new agent instance - no conversation history loaded` (appears on EVERY invocation)
- Same session_id but agent messages count is always reset
- Redundant tool calls for the same information

**OTEL Traces:**

In X-Ray console:

- Compare traces across turns for the same session_id
- Each trace starts with no prior context
- Tool invocation patterns show redundant lookups
- No evidence of message history being passed between invocations

**Key Log Entries:**

```
User role: customer | Session: abc-123-def | Prompt: Is that product in stock?...
Created new agent instance - no conversation history loaded
Tool invoked: check_inventory with params: {}  # Missing product_id - no context!
```

### Root Cause

**File to inspect:**

1. **`agents/product_catalog_agent.py` (line 248-249)** - Agent instantiation
   - Agent is created fresh on every invocation: `agent = Agent(model=model, tools=role_tools, system_prompt=system_prompt)`
   - No `messages` parameter passed with previous conversation history
   - Session ID is received but never used to retrieve history

### Fix Implementation

This requires implementing session persistence. Here's a comprehensive solution:

**Step 1: Add session storage (DynamoDB table for session history)**

Create a DynamoDB table to store conversation history:

```python
# In utils.py or separate module
import boto3
from boto3.dynamodb.conditions import Key

def get_session_table():
    dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-west-2'))
    table_name = os.environ.get('SESSION_TABLE_NAME', 'agent-sessions')
    return dynamodb.Table(table_name)

def load_session_history(session_id: str) -> list:
    """Load conversation history for a session."""
    try:
        table = get_session_table()
        response = table.get_item(Key={'session_id': session_id})
        if 'Item' in response:
            return json.loads(response['Item'].get('messages', '[]'))
        return []
    except Exception as e:
        logger.error(f"Error loading session history: {e}")
        return []

def save_session_history(session_id: str, messages: list) -> None:
    """Save conversation history for a session."""
    try:
        table = get_session_table()
        table.put_item(Item={
            'session_id': session_id,
            'messages': json.dumps(messages),
            'updated_at': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving session history: {e}")
```

**Step 2: Update agent invocation in `product_catalog_agent.py`**

```python
# Load conversation history
previous_messages = load_session_history(session_id)
logger.info(f"Loaded {len(previous_messages)} previous messages for session {session_id}")

# Create agent with conversation history
agent = Agent(
    model=model,
    tools=role_tools,
    system_prompt=system_prompt,
    messages=previous_messages  # Add conversation history!
)

# Invoke agent
response = agent(prompt)
response_text = response.message["content"][0]["text"]

# Save updated conversation history
save_session_history(session_id, agent.messages)
logger.info(f"Saved {len(agent.messages)} messages for session {session_id}")
```

**Step 3: Update IAM role to grant DynamoDB access**

```python
# In utils.py - update create_agent_runtime_role
iam_client.put_role_policy(
    RoleName=role_name,
    PolicyName=f"{role_name}-dynamodb-sessions",
    PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem"
            ],
            "Resource": f"arn:aws:dynamodb:{region}:{account_id}:table/agent-sessions"
        }]
    })
)
```

**Step 4: Create the DynamoDB table**

```bash
aws dynamodb create-table \
  --table-name agent-sessions \
  --attribute-definitions AttributeName=session_id,AttributeType=S \
  --key-schema AttributeName=session_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2
```

### Verification

Redeploy and retest with multi-turn scenarios. CloudWatch logs should show:

```
Loaded 4 previous messages for session abc-123-def
Created new agent instance with conversation history
Tool invoked: check_inventory with params: {'product_id': 'LAPTOP-001'}  # Has context!
Saved 6 messages for session abc-123-def
```

OTEL traces should show session continuity across invocations.

---

## Summary Table

| Failure Case                        | Key Symptom                                 | Primary Diagnostic                               | Fix Location                                                      | Deployment Required                     |
| ----------------------------------- | ------------------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------- | --------------------------------------- |
| **1. Poor Tool Metadata**           | Wrong tool selected, "no results"           | CloudWatch logs, tool invocation spans           | `utils.py`, `product_tools_lambda.py`, `product_catalog_agent.py` | Lambda + Gateway update                 |
| **2. Parameter Schema Mismatch**    | Lambda errors, type validation failures     | CloudWatch Lambda logs, error spans              | `utils.py` (tool schema description)                              | Gateway update                          |
| **3. Wrong Model ID**               | Agent fails to start, ValidationException   | CloudWatch runtime logs, model invocation errors | `product_catalog_agent.py` (MODEL_ID)                             | Full container rebuild + runtime update |
| **4. Missing Conversation History** | No memory across turns, redundant questions | CloudWatch logs (session), tool call patterns    | `product_catalog_agent.py` (add session persistence)              | Runtime update + DynamoDB table         |

---

## Workshop Flow

For each failure case, attendees will:

1. **Deploy the broken version** (this directory)
2. **Run manual test scenarios** via Streamlit app
3. **Observe failures** and document symptoms
4. **Use CloudWatch Logs** to find relevant log entries
5. **Use X-Ray traces** to visualize tool invocations
6. **Identify root cause** by correlating logs and code
7. **Apply fixes** as documented above
8. **Redeploy and verify** fixes work

---

## Additional Observability Tips

### Structured Logging Best Practices

The enhanced logging in this codebase follows these patterns:

```python
# Good: Structured fields
logger.info(f"Tool invoked: {tool_name} with params: {params}")

# Better: JSON structured logging for CloudWatch Insights
logger.info(json.dumps({
    "event": "tool_invocation",
    "tool_name": tool_name,
    "params": params,
    "session_id": session_id,
    "role": role
}))
```

### CloudWatch Insights Queries

**Find all failed tool invocations:**

```
fields @timestamp, @message
| filter @message like /Tool invoked/
| filter @message like /error/ or @message like /failed/
| sort @timestamp desc
```

**Track tool usage by role:**

```
fields @timestamp, role, tool_name
| filter @message like /Tool invoked/
| stats count() by role, tool_name
```

**Find type errors in Lambda:**

```
fields @timestamp, error_type, tool_name, args
| filter error_type = "TypeError"
| sort @timestamp desc
```

### X-Ray Trace Analysis

Key spans to inspect:

- `bedrock-agentcore:invoke-runtime` - Overall agent invocation
- `bedrock:invoke-model` - Model calls (check for errors)
- `mcp:tool-call` - Individual tool invocations (check parameters)
- `gateway:interceptor` - RBAC enforcement points

---

## Questions & Troubleshooting

**Q: How do I know if the fix worked?**

A: Run the same manual test scenario. CloudWatch logs should show the corrected behavior (e.g., correct tool name, successful invocation, valid parameters).

**Q: Can I test locally before deploying?**

A: Partially. You can test the Lambda functions locally, but full agent behavior requires the AgentCore Runtime environment. Focus on validating tool schemas and Lambda logic locally.

**Q: What if I fix one issue but others remain?**

A: Each failure case is independent. Fix them one at a time, redeploying between each fix to isolate the impact.

**Q: How do I reset the environment to re-test a failure?**

A: Revert your code changes and redeploy the broken version from this directory.

---

## Learning Outcomes

By completing this workshop, you will:

✅ Understand how tool metadata affects LLM tool selection
✅ Diagnose parameter type mismatches using CloudWatch logs
✅ Identify model configuration errors from Bedrock invocation traces
✅ Recognize stateless agent behavior and implement session persistence
✅ Use OTEL traces and CloudWatch Logs effectively for production debugging
✅ Apply systematic observability-driven troubleshooting to AI agent systems

---

## Next Steps

After remediating all failure cases:

1. Compare this broken version with the working version in `03-production-deployment/`
2. Review the differences to understand what changed
3. Proceed to **Module 04** for advanced multi-agent observability
4. Learn how to scale evaluation using historical trace data in **Module 05**
