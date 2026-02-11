"""
Product Catalog Agent for AgentCore Runtime

Production version of the single Product Catalog Agent from Module 01.
Deployed as a container to AgentCore Runtime with:
  - Gateway MCP tools via SigV4 authentication
  - JWT-based RBAC (role extracted from Cognito JWT claims)
  - Role-aware system prompts
  - BedrockAgentCoreApp entrypoint

The RBAC pattern from Module 01 (local UserSession) maps to production as:
  Module 01: UserSession.role field -> Module 03: JWT cognito:groups claim
"""

import os
import json
import logging
import base64
import boto3

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
GATEWAY_URL = os.environ.get('GATEWAY_URL', '')
AGENT_REGION = os.environ.get('AGENT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
MODEL_ID = os.environ.get('MODEL_ID', 'global.anthropic.claude-haiku-4-5-20251001-v1:0')

# ---------------------------------------------------------------------------
# RBAC constants (same as Module 01)
# ---------------------------------------------------------------------------
CUSTOMER_TOOLS = [
    'search_products', 'get_product_details', 'check_inventory',
    'get_product_recommendations', 'compare_products', 'get_return_policy'
]
ADMIN_ONLY_TOOLS = [
    'create_product', 'update_product', 'delete_product',
    'update_inventory', 'update_pricing'
]
ADMIN_TOOLS = CUSTOMER_TOOLS + ADMIN_ONLY_TOOLS

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
CUSTOMER_SYSTEM_PROMPT = """You are the Product Catalog Assistant for our e-commerce store.
You are helping a customer browse and explore products.

Your capabilities:
- Search for products by keywords or category
- Show detailed product information
- Check inventory and stock availability
- Recommend products based on preferences
- Compare products side by side
- Explain return policies and warranties

You do NOT have access to any administrative functions like creating, updating,
or deleting products. If a customer asks you to modify the catalog, politely explain
that these operations require administrator privileges.

Always be helpful, accurate, and customer-focused."""

ADMIN_SYSTEM_PROMPT = """You are the Product Catalog Assistant for our e-commerce store.
You are helping an administrator manage the product catalog.

Your capabilities include ALL customer tools PLUS administrative functions:
- Create new products in the catalog
- Update existing product information
- Delete (discontinue) products
- Manage inventory levels
- Update pricing and set sales

Use administrative tools carefully. Always confirm important changes.
For deletions, note that they are soft deletes (products are marked as discontinued)."""


def decode_jwt_claims(token: str) -> dict:
    """Decode JWT payload to extract claims."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as e:
        logger.error(f"Error decoding JWT: {e}")
        return {}


def get_role_from_jwt(token: str) -> str:
    """Extract role from JWT cognito:groups claim."""
    claims = decode_jwt_claims(token)
    groups = claims.get('cognito:groups', [])
    if isinstance(groups, str):
        groups = [groups]
    return 'admin' if 'admin' in groups else 'customer'


def get_tools_for_role(all_tools: list, role: str) -> list:
    """Filter MCP tools based on user role."""
    allowed = ADMIN_TOOLS if role == 'admin' else CUSTOMER_TOOLS
    return [t for t in all_tools if strip_prefix(t.tool_name) in allowed]


def strip_prefix(tool_name: str) -> str:
    """Strip Gateway target prefix from tool name."""
    delimiter = '___'
    if delimiter in tool_name:
        return tool_name[tool_name.index(delimiter) + len(delimiter):]
    return tool_name


# ---------------------------------------------------------------------------
# SigV4 transport for Gateway MCP connection
# ---------------------------------------------------------------------------
def create_sigv4_mcp_client(gateway_url: str, region: str, bearer_token: str = None):
    """
    Create an MCP client that connects to AgentCore Gateway.
    Uses Bearer JWT for CUSTOM_JWT gateways, or SigV4 for AWS_IAM gateways.
    """
    from mcp.client.streamable_http import streamablehttp_client

    if bearer_token:
        # CUSTOM_JWT gateway: use Bearer token only (SigV4 would overwrite Authorization header)
        def transport():
            return streamablehttp_client(
                url=gateway_url,
                headers={'Authorization': f'Bearer {bearer_token}'}
            )
    else:
        # AWS_IAM gateway: use SigV4 signing
        import httpx
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        session = boto3.Session(region_name=region)
        credentials = session.get_credentials().get_frozen_credentials()

        class SigV4Auth_HTTPX(httpx.Auth):
            def auth_flow(self, request: httpx.Request):
                headers = dict(request.headers)
                headers.pop('connection', None)
                aws_req = AWSRequest(
                    method=request.method,
                    url=str(request.url),
                    data=request.content,
                    headers=headers
                )
                SigV4Auth(credentials, 'bedrock-agentcore', region).add_auth(aws_req)
                request.headers.update(dict(aws_req.headers))
                yield request

        def transport():
            return streamablehttp_client(
                url=gateway_url,
                auth=SigV4Auth_HTTPX()
            )

    return MCPClient(transport)


# ---------------------------------------------------------------------------
# BedrockAgentCoreApp
# ---------------------------------------------------------------------------
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload=None, **kwargs):
    """
    Main entry point for AgentCore Runtime invocations.

    Expected payload:
    {
        "prompt": "user message",
        "session_id": "optional session id",
        "bearer_token": "optional JWT for role extraction"
    }

    The bearer_token is passed by the frontend after Cognito login.
    It contains cognito:groups claim used for RBAC.
    """
    if not payload:
        return {"error": "No payload provided"}

    # Handle warmup
    if payload.get('warmup'):
        return {"status": "warmed"}

    prompt = payload.get('prompt', '')
    bearer_token = payload.get('bearer_token', '')  # ID token for role extraction
    access_token = payload.get('access_token', '')   # Access token for Gateway auth
    session_id = payload.get('session_id', 'default')

    if not prompt:
        return {"error": "No prompt provided"}

    # Determine role from JWT
    role = 'customer'  # Default to least privilege
    if bearer_token:
        role = get_role_from_jwt(bearer_token)
    logger.info(f"User role: {role} | Session: {session_id}")

    # Connect to Gateway MCP tools
    if not GATEWAY_URL:
        return {"error": "GATEWAY_URL not configured"}

    # Use access_token for Gateway auth (has client_id claim for CUSTOM_JWT validation)
    # Fall back to bearer_token (ID token) if no access_token provided
    gateway_token = access_token or bearer_token
    mcp_client = create_sigv4_mcp_client(GATEWAY_URL, AGENT_REGION, gateway_token)

    try:
        mcp_client.__enter__()
        all_tools = mcp_client.list_tools_sync()

        # Filter tools by role (application-level RBAC - defense in depth)
        role_tools = get_tools_for_role(all_tools, role)
        logger.info(f"Tools available for {role}: {len(role_tools)} / {len(all_tools)} total")

        # Select system prompt based on role
        system_prompt = ADMIN_SYSTEM_PROMPT if role == 'admin' else CUSTOMER_SYSTEM_PROMPT

        # Create agent
        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=AGENT_REGION,
            temperature=0.3,
            max_tokens=1500
        )

        agent = Agent(
            model=model,
            tools=role_tools,
            system_prompt=system_prompt
        )

        # Invoke agent
        response = agent(prompt)
        response_text = response.message['content'][0]['text']

        # Collect tool usage metadata from full conversation history
        # Strands uses 'toolUse' key (camelCase) in ContentBlock TypedDict
        tools_used = []
        for msg in agent.messages:
            if msg.get('role') == 'assistant':
                for content_block in msg.get('content', []):
                    if 'toolUse' in content_block:
                        tool_name = content_block['toolUse'].get('name', '')
                        tools_used.append(strip_prefix(tool_name))

        return {
            "status": "success",
            "response": response_text,
            "metadata": {
                "role": role,
                "tools_available": len(role_tools),
                "tools_used": tools_used,
                "session_id": session_id,
                "model": MODEL_ID
            }
        }

    except Exception as e:
        logger.error(f"Agent error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        try:
            mcp_client.__exit__(None, None, None)
        except Exception:
            pass


if __name__ == "__main__":
    app.run()
