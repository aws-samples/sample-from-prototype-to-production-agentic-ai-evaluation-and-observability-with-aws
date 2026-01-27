"""
Order Agent with AgentCore Observability

This agent uses BedrockAgentCoreApp for automatic OpenTelemetry instrumentation,
enabling traces and spans to be captured in CloudWatch GenAI Observability.
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
MODEL_ID = os.environ.get('MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0')


def get_oauth_token() -> str | None:
    """Get OAuth token for Gateway authentication."""
    try:
        cognito = boto3.client('cognito-idp', region_name=REGION)

        # Get client secret
        client_details = cognito.describe_user_pool_client(
            UserPoolId=USER_POOL_ID,
            ClientId=CLIENT_ID
        )
        client_secret = client_details['UserPoolClient'].get('ClientSecret')

        # Get domain
        pool_info = cognito.describe_user_pool(UserPoolId=USER_POOL_ID)
        domain = pool_info['UserPool'].get('Domain')

        if not domain:
            logger.error("No Cognito domain configured")
            return None

        # Get token
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


def create_order_agent() -> tuple[Agent, list, MCPClient | None]:
    """
    Create and initialize the Order Agent with MCP tools.

    Returns:
        Tuple of (agent, tools, mcp_client)
    """
    logger.info("Initializing Order Agent...")
    logger.info(f"Region: {REGION}")
    logger.info(f"Gateway URL: {GATEWAY_URL}")

    mcp_client = None
    order_tools = []

    if not GATEWAY_URL or not USER_POOL_ID or not CLIENT_ID:
        logger.warning("Gateway configuration incomplete - creating agent without tools")
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt="Order Agent - Gateway not configured. Cannot access order tools."
        )
        return agent, [], None

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

        # Get all tools and filter for order-related ones
        all_tools = mcp_client.list_tools_sync()
        order_tools = [t for t in all_tools if 'OrderTools' in t.tool_name]

        logger.info(f"Connected to Gateway with {len(order_tools)} order tools:")
        for tool in order_tools:
            logger.info(f"  - {tool.tool_name}")

        # Create the agent
        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=REGION,
            temperature=0.2
        )

        system_prompt = """You are the Order Agent, a specialized e-commerce assistant focused on order management.

Your capabilities include:
- Checking order status and details (use OrderTools___get_order_status)
- Tracking shipments with carrier information (use OrderTools___track_shipment)
- Processing return requests (use OrderTools___process_return)
- Modifying orders - cancellation, address updates (use OrderTools___modify_order)
- Retrieving customer order history (use OrderTools___get_customer_orders)

Always use the appropriate tools to get accurate, real-time information from the database.
Be helpful, concise, and provide clear next steps when relevant."""

        agent = Agent(
            model=model,
            tools=order_tools,
            system_prompt=system_prompt
        )

        logger.info("Order Agent initialized successfully")
        return agent, order_tools, mcp_client

    except Exception as e:
        logger.error(f"Error initializing agent: {e}")
        # Create fallback agent without tools
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt=f"Order Agent - Error connecting to Gateway: {str(e)}"
        )
        return agent, [], None


@app.entrypoint
def order_agent_entrypoint(payload: Dict[str, Any]) -> str:
    """
    Entry point for AgentCore Runtime invocation.

    This function is decorated with @app.entrypoint which makes it the entry point
    for the AgentCore Runtime. The BedrockAgentCoreApp automatically provides
    OpenTelemetry instrumentation for traces and spans.

    Args:
        payload: Input payload containing the user prompt

    Returns:
        Agent response as JSON string
    """
    user_input = payload.get("prompt", "")

    logger.info(f"Order Agent invoked with prompt: {user_input}")

    # Initialize agent (lazy initialization)
    agent, tools, _ = create_order_agent()

    # Invoke the agent
    result = agent(user_input)

    # Extract response text
    response_text = str(result)
    if hasattr(result, 'message') and 'content' in result.message:
        response_text = result.message["content"][0]["text"]

    logger.info("Order Agent invocation completed successfully")

    # Return structured response
    import json
    response = {
        "message": response_text,
        "agent": "order-agent",
        "tools_used": len(tools),
        "timestamp": datetime.utcnow().isoformat()
    }

    return json.dumps(response)


if __name__ == "__main__":
    # When deployed to AgentCore Runtime, this starts the HTTP server
    # with automatic OTEL instrumentation
    app.run()
