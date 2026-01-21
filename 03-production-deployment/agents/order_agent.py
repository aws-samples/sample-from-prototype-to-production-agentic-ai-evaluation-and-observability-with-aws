"""
Order Agent - AgentCore Runtime Agent

This agent handles order-related queries using MCP tools from AgentCore Gateway.
Follows the AgentCore Runtime contract with /invocations and /ping endpoints.
"""

import logging
import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
import uvicorn
import boto3
import requests
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
REGION = os.environ.get('AGENT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
GATEWAY_URL = os.environ.get('GATEWAY_URL', '')
USER_POOL_ID = os.environ.get('USER_POOL_ID', '')
CLIENT_ID = os.environ.get('CLIENT_ID', '')
MODEL_ID = os.environ.get('MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')

# FastAPI app
app = FastAPI(title="Order Agent Server", version="1.0.0")

# Global state
mcp_client = None
order_tools = []
order_agent = None


class InvocationRequest(BaseModel):
    input: Dict[str, Any]


class InvocationResponse(BaseModel):
    output: Dict[str, Any]


def get_oauth_token():
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


def initialize_agent():
    """Initialize the Order Agent with MCP tools from Gateway."""
    global mcp_client, order_tools, order_agent

    logger.info("Initializing Order Agent...")
    logger.info(f"Region: {REGION}")
    logger.info(f"Gateway URL: {GATEWAY_URL}")

    if not GATEWAY_URL or not USER_POOL_ID or not CLIENT_ID:
        logger.warning("Gateway configuration incomplete - creating agent without tools")
        order_agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt="Order Agent - Gateway not configured. Cannot access order tools."
        )
        return

    try:
        access_token = get_oauth_token()
        if not access_token:
            logger.error("Failed to get access token")
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

        order_agent = Agent(
            model=model,
            tools=order_tools,
            system_prompt=system_prompt
        )

        logger.info("Order Agent initialized successfully")

    except Exception as e:
        logger.error(f"Error initializing agent: {e}")
        # Create fallback agent without tools
        order_agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
            system_prompt=f"Order Agent - Error connecting to Gateway: {str(e)}"
        )


@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup."""
    initialize_agent()


@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    """Main invocation endpoint for agent interactions."""
    try:
        user_message = request.input.get("prompt", "")
        if not user_message:
            raise HTTPException(
                status_code=400,
                detail="No prompt found in input. Please provide a 'prompt' key."
            )

        if order_agent is None:
            raise HTTPException(
                status_code=503,
                detail="Agent not initialized"
            )

        # Invoke the agent
        result = order_agent(user_message)

        response = {
            "message": str(result),
            "agent": "order-agent",
            "tools_used": len(order_tools),
            "timestamp": datetime.utcnow().isoformat()
        }

        return InvocationResponse(output=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent invocation error: {e}")
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {str(e)}")


@app.get("/ping")
async def ping():
    """Health check endpoint required by AgentCore Runtime."""
    return {
        "status": "healthy",
        "agent": "order-agent",
        "gateway_connected": mcp_client is not None,
        "tools_count": len(order_tools)
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
