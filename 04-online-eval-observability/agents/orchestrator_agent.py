"""
Orchestrator Agent with AgentCore Observability

This agent uses BedrockAgentCoreApp for automatic OpenTelemetry instrumentation,
enabling traces and spans to be captured in CloudWatch GenAI Observability.

The orchestrator routes requests to specialized sub-agents via MCP.
"""

import json
import logging
import os
import base64
from datetime import datetime
from typing import Any, Dict

import boto3
import requests
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Initialize AgentCore Runtime App (provides automatic OTEL instrumentation)
app = BedrockAgentCoreApp()

# Configuration from environment
REGION = os.environ.get('AGENT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
GATEWAY_URL = os.environ.get('GATEWAY_URL', '')
USER_POOL_ID = os.environ.get('USER_POOL_ID', '')
CLIENT_ID = os.environ.get('CLIENT_ID', '')
MODEL_ID = os.environ.get('MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0')


def get_oauth_token() -> str | None:
    """Get OAuth token for Gateway authentication."""
    try:
        cognito = boto3.client('cognito-idp', region_name=REGION)

        client_details = cognito.describe_user_pool_client(
            UserPoolId=USER_POOL_ID,
            ClientId=CLIENT_ID
        )
        client_secret = client_details['UserPoolClient'].get('ClientSecret')

        pool_info = cognito.describe_user_pool(UserPoolId=USER_POOL_ID)
        domain = pool_info['UserPool'].get('Domain')

        if not domain:
            logger.error("No Cognito domain configured")
            return None

        token_url = f"https://{domain}.auth.{REGION}.amazoncognito.com/oauth2/token"
        credentials = base64.b64encode(f"{CLIENT_ID}:{client_secret}".encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {credentials}'
        }

        resource_server_id = 'ecommerce-workshop-gateway-api'
        scopes = f"{resource_server_id}/gateway:read {resource_server_id}/gateway:write"

        data = {
            'grant_type': 'client_credentials',
            'scope': scopes
        }

        response = requests.post(token_url, headers=headers, data=data)
        token_response = response.json()

        if 'access_token' in token_response:
            return token_response['access_token']
        else:
            logger.error(f"Token error: {token_response}")
            return None

    except Exception as e:
        logger.error(f"Error getting OAuth token: {e}")
        return None


def create_orchestrator_agent() -> tuple[Agent, list, list, MCPClient | None]:
    """
    Create and initialize the Orchestrator Agent with all MCP tools.

    Returns:
        Tuple of (agent, all_tools, routed_agents, mcp_client)
    """
    logger.info("Initializing Orchestrator Agent...")
    logger.info(f"Region: {REGION}")
    logger.info(f"Gateway URL: {GATEWAY_URL}")

    mcp_client = None
    all_tools = []
    routed_agents = []

    if not GATEWAY_URL or not USER_POOL_ID or not CLIENT_ID:
        logger.warning("Gateway configuration incomplete - creating agent without tools")
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt="Orchestrator Agent - Gateway not configured. Cannot route to sub-agents."
        )
        return agent, [], [], None

    try:
        access_token = get_oauth_token()
        if not access_token:
            raise Exception("OAuth token acquisition failed")

        def create_transport():
            return streamablehttp_client(
                GATEWAY_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )

        mcp_client = MCPClient(create_transport)
        mcp_client.__enter__()

        # Get ALL tools from Gateway (Order, Product, Account)
        all_tools = mcp_client.list_tools_sync()

        # Track which agent domains we have tools for
        if any('OrderTools' in t.tool_name for t in all_tools):
            routed_agents.append('order-agent')
        if any('ProductTools' in t.tool_name for t in all_tools):
            routed_agents.append('product-agent')
        if any('AccountTools' in t.tool_name for t in all_tools):
            routed_agents.append('account-agent')

        logger.info(f"Connected to Gateway with {len(all_tools)} total tools")
        logger.info(f"Can route to: {', '.join(routed_agents)}")

        # Use more capable model for orchestration
        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=REGION,
            temperature=0.3
        )

        system_prompt = """You are the E-Commerce Orchestrator Agent, a central coordinator that handles complex customer requests.

You have access to tools from three specialized domains:

1. **Order Management** (OrderTools___)
   - Check order status, track shipments, process returns, modify orders
   - Use for: order inquiries, shipping questions, return requests

2. **Product Information** (ProductTools___)
   - Search products, get details, check availability, view reviews
   - Use for: product searches, inventory questions, comparisons

3. **Account Services** (AccountTools___)
   - Get customer profiles, manage loyalty points, update info
   - Use for: account questions, rewards, membership tiers

**Orchestration Guidelines:**
- Analyze each request to determine which domain(s) to invoke
- For complex requests spanning multiple domains, gather info from each relevant domain
- Synthesize information from multiple tools into a coherent response
- Always provide helpful, complete answers by combining results
- If a request is ambiguous, ask for clarification

Be efficient, helpful, and provide comprehensive responses."""

        agent = Agent(
            model=model,
            tools=all_tools,
            system_prompt=system_prompt
        )

        logger.info("Orchestrator Agent initialized successfully")
        return agent, all_tools, routed_agents, mcp_client

    except Exception as e:
        logger.error(f"Error initializing agent: {e}")
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt=f"Orchestrator Agent - Error connecting to Gateway: {str(e)}"
        )
        return agent, [], [], None


@app.entrypoint
def orchestrator_agent_entrypoint(payload: Dict[str, Any]) -> str:
    """
    Entry point for AgentCore Runtime invocation.

    This function is decorated with @app.entrypoint which provides
    automatic OpenTelemetry instrumentation for CloudWatch observability.

    Args:
        payload: Input payload containing the user prompt

    Returns:
        Agent response as JSON string
    """
    user_input = payload.get("prompt", "")

    logger.info(f"Orchestrator Agent invoked with prompt: {user_input}")

    # Initialize agent (lazy initialization)
    agent, tools, routed_agents, _ = create_orchestrator_agent()

    # Invoke the agent
    result = agent(user_input)

    # Extract response text
    response_text = str(result)
    if hasattr(result, 'message') and 'content' in result.message:
        response_text = result.message["content"][0]["text"]

    logger.info("Orchestrator Agent invocation completed successfully")
    logger.info(f"Routed to domains: {routed_agents}")

    response = {
        "message": response_text,
        "agent": "orchestrator",
        "routed_to": routed_agents,
        "tools_used": len(tools),
        "timestamp": datetime.utcnow().isoformat()
    }

    return json.dumps(response)


if __name__ == "__main__":
    app.run()
