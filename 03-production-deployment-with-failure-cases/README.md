# Production Deployment with Failure Cases

## Purpose

This directory contains an **intentionally broken version** of the production e-commerce agent deployment from Module 03. It is designed for workshop attendees to practice diagnosing and remediating production issues using **AWS Bedrock AgentCore Observability**.

## What's Different from `03-production-deployment`?

This version contains **4 intentional failure cases** that represent real-world production issues:

1. **Poor Tool Metadata** - Vague tool descriptions and THREE tools with IDENTICAL descriptions causing wrong tool selection
2. **Tool Parameter Schema Mismatch** - Type validation errors from unclear parameter descriptions
3. **Wrong Model ID** - Deprecated model causing invocation failures
4. **Missing Conversation History** - Stateless agent with no memory across turns

## Directory Structure

```
03-production-deployment-with-failure-cases/
├── README.md                           # This file
├── FAILURECASES.md                     # Detailed failure documentation
├── agents/
│   ├── product_catalog_agent.py        # Agent with failures + enhanced logging
│   ├── Dockerfile                      # ARM64 container with OTEL
│   └── requirements.txt
├── lambda_tools/
│   ├── product_tools_lambda.py         # Lambda with failures + enhanced logging
│   └── rbac_interceptor_lambda.py      # RBAC interceptor (unchanged)
├── streamlit_app/
│   ├── app.py                          # Test UI (unchanged)
│   └── agent_config.json               # Deployment config
└── utils.py                            # Deployment utilities with broken tool schemas
```

## Files Modified with Failures

| File | Failure Cases | Lines Changed |
|------|--------------|---------------|
| `utils.py` | 1 (tool metadata), 2 (parameter schema) | 928-990, 1044-1056 |
| `lambda_tools/product_tools_lambda.py` | 1 (tool routing) | 13-18, 690, 750-773 |
| `agents/product_catalog_agent.py` | 1 (tool list), 3 (model ID), 4 (stateless) | 34, 40, 214-250 |

## Enhanced Logging Features

All files include **production-grade observability enhancements**:

### Agent Code (`product_catalog_agent.py`)

- Model initialization logging with model ID
- Tool selection and filtering logging
- Tool invocation parameter logging
- Structured error logging with context
- Session state logging (shows stateless behavior)

### Lambda Tools (`product_tools_lambda.py`)

- Tool execution logging with parameters
- Success/failure status logging
- Type error detection and logging
- Structured exception handling

### Log Examples

```
INFO: User role: customer | Session: abc-123 | Prompt: Show me laptops...
INFO: Tools available for customer: 6 / 11 total
INFO: Tool names: ['search', 'get_product_details', 'check_inventory', ...]
INFO: Initializing model: anthropic.claude-3-5-haiku-20241022-v1:0
ERROR: Agent error: ValidationException: Could not resolve the foundation model
INFO: Tool invoked: search with params: {'query': 'laptops'}
INFO: Created new agent instance - no conversation history loaded
```

## Workshop Usage

### For Workshop Instructors

**Setup:**

1. Deploy the working version from `03-production-deployment/` first
2. Have attendees test it to establish baseline behavior
3. Switch to this broken version for the observability module
4. Guide attendees through diagnosis using `FAILURECASES.md`

**Teaching Flow:**

```
Working Agent → Broken Agent → Observe Failures → Diagnose → Fix → Verify
```

### For Workshop Attendees

**Your Mission:**

Use AWS Bedrock AgentCore observability tools to find and fix all 4 failure cases.

**Steps:**

1. **Deploy this broken version** using the deployment notebook
2. **Test via Streamlit** using scenarios from `FAILURECASES.md`
3. **Observe failures** and document symptoms
4. **Use CloudWatch Logs** to find relevant log entries
5. **Use X-Ray traces** to visualize execution flow
6. **Identify root causes** by reading `FAILURECASES.md`
7. **Apply fixes** to your local code
8. **Redeploy and verify** each fix works

## Key Learning Objectives

By working through these failure cases, you will learn:

✅ **Tool Design Best Practices** - How to write clear, unambiguous tool metadata
✅ **Parameter Schema Design** - How to make LLMs pass correctly-typed parameters
✅ **Model Configuration** - How to detect and fix model ID issues
✅ **Session Management** - How to implement stateful conversation history
✅ **Observability Workflows** - How to use CloudWatch + X-Ray for debugging
✅ **Production Troubleshooting** - Systematic approaches to diagnosing AI agent issues

## Deployment Notes

### Prerequisites

Same as `03-production-deployment`:

- AWS account with Bedrock access
- AgentCore enabled in your region
- Cognito user pool with customer/admin users
- DynamoDB tables from Module 00

### Deployment Command

Use the same deployment notebook as Module 03, but point to this directory:

```python
# In deployment notebook, change:
AGENT_DIR = "03-production-deployment-with-failure-cases"
```

### Important

⚠️ **Do NOT deploy both versions simultaneously** - they will conflict on resource names.

Deploy one version, test it, tear it down, then deploy the other.

## Observability Tools Reference

### CloudWatch Logs

**Runtime logs:**
```
/aws/bedrock-agentcore/runtimes/<runtime-id>
```

**Lambda logs:**
```
/aws/lambda/product_tools_lambda
/aws/lambda/rbac_interceptor_lambda
```

### X-Ray Traces

Navigate to: **AWS X-Ray Console** → **Traces**

Filter by:
- Service: `bedrock-agentcore`
- Status: `Error` (to find failures)
- Annotation: `session_id` (to trace user sessions)

### CloudWatch Insights Queries

See `FAILURECASES.md` for pre-built queries to analyze logs.

## Comparison with Working Version

To see what was changed:

```bash
# Compare agent code
diff 03-production-deployment/agents/product_catalog_agent.py \
     03-production-deployment-with-failure-cases/agents/product_catalog_agent.py

# Compare tool schemas
diff 03-production-deployment/utils.py \
     03-production-deployment-with-failure-cases/utils.py

# Compare Lambda
diff 03-production-deployment/lambda_tools/product_tools_lambda.py \
     03-production-deployment-with-failure-cases/lambda_tools/product_tools_lambda.py
```

## Expected Workshop Timeline

| Activity | Time | Description |
|----------|------|-------------|
| Deploy broken version | 5 min | Use deployment notebook |
| Test and observe failures | 10 min | Run manual test scenarios |
| Diagnose Failure Case 1 | 15 min | Poor tool metadata |
| Fix and verify Case 1 | 10 min | Update code and redeploy |
| Diagnose Failure Case 2 | 10 min | Parameter schema mismatch |
| Fix and verify Case 2 | 5 min | Update description |
| Diagnose Failure Case 3 | 10 min | Wrong model ID |
| Fix and verify Case 3 | 10 min | Update model + rebuild |
| Diagnose Failure Case 4 | 15 min | Missing conversation history |
| Fix and verify Case 4 | 20 min | Implement session persistence |
| **Total** | **~2 hours** | Full workshop |

## Success Criteria

You've successfully completed this module when:

✅ All 4 failure cases are identified using observability tools
✅ All fixes are applied and tested
✅ Streamlit app works correctly for all test scenarios
✅ CloudWatch logs show healthy agent behavior
✅ X-Ray traces show successful tool invocations

## Troubleshooting

**Q: I can't find the logs in CloudWatch**

A: Make sure you're looking in the correct region and the runtime has been invoked at least once.

**Q: The agent still doesn't work after my fix**

A: Did you redeploy? Most changes require redeploying the Lambda/Gateway/Runtime.

**Q: Can I skip to the fixes without diagnosing?**

A: You can, but you'll miss the learning! The goal is to practice observability-driven troubleshooting.

**Q: How do I reset to retry a failure?**

A: Revert your code changes (e.g., `git checkout <file>`) and redeploy.

## Additional Resources

- **AWS Bedrock AgentCore Docs**: https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html
- **OpenTelemetry Python**: https://opentelemetry.io/docs/languages/python/
- **CloudWatch Logs Insights**: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html
- **AWS X-Ray**: https://docs.aws.amazon.com/xray/latest/devguide/

## Next Module

After completing this module, proceed to:

**Module 04: Online Evaluation & Observability**
- Learn multi-agent orchestration
- Monitor production agent behavior at scale
- Analyze traces for quality metrics

---

**Happy debugging! Remember: observability is key to production AI agents.** 🔍
