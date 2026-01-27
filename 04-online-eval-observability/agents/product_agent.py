"""
Product Agent with AgentCore Observability

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

# NOTE: Do NOT manually configure OTLP exporter here!
# The opentelemetry-instrument wrapper (in Dockerfile CMD) + aws-opentelemetry-distro
# automatically configures OTEL tracing via environment variables.

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


def create_product_agent() -> tuple[Agent, list, MCPClient | None]:
    """
    Create and initialize the Product Agent with MCP tools.

    Returns:
        Tuple of (agent, tools, mcp_client)
    """
    logger.info("Initializing Product Agent...")
    logger.info(f"Region: {REGION}")
    logger.info(f"Gateway URL: {GATEWAY_URL}")

    mcp_client = None
    product_tools = []

    if not GATEWAY_URL or not USER_POOL_ID or not CLIENT_ID:
        logger.warning("Gateway configuration incomplete - creating agent without tools")
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt="Product Agent - Gateway not configured. Cannot access product tools."
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

        # Get all tools and filter for product-related ones
        all_tools = mcp_client.list_tools_sync()
        product_tools = [t for t in all_tools if 'ProductTools' in t.tool_name]

        logger.info(f"Connected to Gateway with {len(product_tools)} product tools:")
        for tool in product_tools:
            logger.info(f"  - {tool.tool_name}")

        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=REGION,
            temperature=0.2
        )

        system_prompt = """You are the Product Agent, a specialized e-commerce assistant focused on product information.

Your capabilities include:
- Searching products by category, keywords, or price range (use ProductTools___search_products)
- Getting detailed product information (use ProductTools___get_product_details)
- Checking product availability and stock levels (use ProductTools___check_availability)
- Retrieving product reviews and ratings (use ProductTools___get_product_reviews)
- Finding related or similar products (use ProductTools___get_related_products)

Always use the appropriate tools to provide accurate product information.
Be helpful and provide detailed product descriptions when relevant."""

        agent = Agent(
            model=model,
            tools=product_tools,
            system_prompt=system_prompt
        )

        logger.info("Product Agent initialized successfully")
        return agent, product_tools, mcp_client

    except Exception as e:
        logger.error(f"Error initializing agent: {e}")
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt=f"Product Agent - Error connecting to Gateway: {str(e)}"
        )
        return agent, [], None


@app.entrypoint
def product_agent_entrypoint(payload: Dict[str, Any]) -> str:
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

    logger.info(f"Product Agent invoked with prompt: {user_input}")

    # Initialize agent (lazy initialization)
    agent, tools, _ = create_product_agent()

    # Invoke the agent
    result = agent(user_input)

    # Extract response text
    response_text = str(result)
    if hasattr(result, 'message') and 'content' in result.message:
        response_text = result.message["content"][0]["text"]

    logger.info("Product Agent invocation completed successfully")

    import json
    response = {
        "message": response_text,
        "agent": "product-agent",
        "tools_used": len(tools),
        "timestamp": datetime.utcnow().isoformat()
    }

    return json.dumps(response)


if __name__ == "__main__":
    app.run()
