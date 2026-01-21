"""
Orchestrator Agent - Main Entry Point

This agent acts as the customer service coordinator, routing requests to
specialized agents (Order, Product, Account) via SDK invocation.
Follows the AgentCore Runtime contract with /invocations and /ping endpoints.
"""

import logging
import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from strands import Agent, tool
from strands.models import BedrockModel
import uvicorn
import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
REGION = os.environ.get('AGENT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
MODEL_ID = os.environ.get('MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')

# Specialized Agent ARNs (set via environment variables)
ORDER_AGENT_ARN = os.environ.get('ORDER_AGENT_ARN', '')
PRODUCT_AGENT_ARN = os.environ.get('PRODUCT_AGENT_ARN', '')
ACCOUNT_AGENT_ARN = os.environ.get('ACCOUNT_AGENT_ARN', '')

# FastAPI app
app = FastAPI(title="Customer Service Orchestrator", version="1.0.0")

# Global state
orchestrator_agent = None
agentcore_runtime_client = None


class InvocationRequest(BaseModel):
    input: Dict[str, Any]


class InvocationResponse(BaseModel):
    output: Dict[str, Any]


def invoke_specialized_agent(agent_arn: str, prompt: str) -> str:
    """Invoke a specialized agent via the SDK."""
    global agentcore_runtime_client

    if not agent_arn:
        return "Agent not configured"

    if agentcore_runtime_client is None:
        agentcore_runtime_client = boto3.client('bedrock-agentcore', region_name=REGION)

    try:
        # Generate a unique session ID (must be at least 33 characters)
        import uuid
        import time
        session_id = f"session-{int(time.time())}-{uuid.uuid4().hex[:20]}"

        logger.info(f"Invoking agent {agent_arn} with session {session_id}")

        payload = json.dumps({
            "input": {"prompt": prompt}
        })

        response = agentcore_runtime_client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            payload=payload.encode('utf-8'),
            qualifier="DEFAULT"
        )

        # Read the response blob
        response_body = response.get('response', b'')
        if hasattr(response_body, 'read'):
            response_body = response_body.read()

        logger.info(f"Response from agent: {response_body[:500] if response_body else 'empty'}")
        response_data = json.loads(response_body)

        # Extract message from response
        if 'output' in response_data:
            return response_data['output'].get('message', str(response_data['output']))
        return str(response_data)

    except Exception as e:
        logger.error(f"Error invoking agent {agent_arn}: {e}")
        return f"Error communicating with agent: {str(e)}"


@tool
def ask_order_agent(query: str) -> str:
    """
    Route order-related queries to the Order Agent.

    Use this for questions about:
    - Order status and details
    - Shipment tracking
    - Returns and refunds
    - Order modifications and cancellations
    - Customer order history

    Args:
        query: The order-related question or request from the customer

    Returns:
        Response from the Order Agent
    """
    if not ORDER_AGENT_ARN:
        return "Order Agent is not configured."

    logger.info(f"Routing to Order Agent: {query}")
    return invoke_specialized_agent(ORDER_AGENT_ARN, query)


@tool
def ask_product_agent(query: str) -> str:
    """
    Route product-related queries to the Product Agent.

    Use this for questions about:
    - Product search and discovery
    - Product details and specifications
    - Inventory availability
    - Product recommendations
    - Product comparisons
    - Return policies

    Args:
        query: The product-related question or request from the customer

    Returns:
        Response from the Product Agent
    """
    if not PRODUCT_AGENT_ARN:
        return "Product Agent is not configured."

    logger.info(f"Routing to Product Agent: {query}")
    return invoke_specialized_agent(PRODUCT_AGENT_ARN, query)


@tool
def ask_account_agent(query: str) -> str:
    """
    Route account-related queries to the Account Agent.

    Use this for questions about:
    - Account information and settings
    - Shipping address updates
    - Membership tier benefits
    - Password resets
    - Notification preferences
    - Reward points and loyalty program

    Args:
        query: The account-related question or request from the customer

    Returns:
        Response from the Account Agent
    """
    if not ACCOUNT_AGENT_ARN:
        return "Account Agent is not configured."

    logger.info(f"Routing to Account Agent: {query}")
    return invoke_specialized_agent(ACCOUNT_AGENT_ARN, query)


def initialize_orchestrator():
    """Create the Orchestrator Agent."""
    global orchestrator_agent

    logger.info("Initializing Orchestrator Agent...")
    logger.info(f"Region: {REGION}")
    logger.info(f"Order Agent ARN: {ORDER_AGENT_ARN}")
    logger.info(f"Product Agent ARN: {PRODUCT_AGENT_ARN}")
    logger.info(f"Account Agent ARN: {ACCOUNT_AGENT_ARN}")

    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=REGION,
        temperature=0.2
    )

    system_prompt = """You are the Customer Service Orchestrator for an e-commerce company.
Your role is to understand customer requests and route them to the appropriate specialized agent.

## Available Specialized Agents

### Order Agent (use ask_order_agent)
Handle requests about:
- Order status and details (e.g., "What's the status of my order?")
- Shipment tracking (e.g., "Where is my package?")
- Returns and refunds (e.g., "I want to return my order")
- Order modifications (e.g., "Cancel my order")
- Order history (e.g., "Show my recent orders")

### Product Agent (use ask_product_agent)
Handle requests about:
- Product search (e.g., "Do you have wireless headphones?")
- Product details (e.g., "Tell me about product PROD-001")
- Inventory checks (e.g., "Is this in stock?")
- Recommendations (e.g., "Suggest products under $100")
- Product comparisons (e.g., "Compare these products")
- Return policies (e.g., "What's your return policy?")

### Account Agent (use ask_account_agent)
Handle requests about:
- Account information (e.g., "Show my account details")
- Address updates (e.g., "Update my shipping address")
- Membership benefits (e.g., "What are Gold member benefits?")
- Password resets (e.g., "I forgot my password")
- Notification preferences (e.g., "Turn off emails")
- Reward points (e.g., "How many points do I have?")

## Guidelines

1. Analyze the customer's request to understand their intent
2. Select the appropriate agent based on the request type
3. Present the response in a helpful, customer-friendly manner

For complex requests spanning multiple domains, query each relevant agent and synthesize a unified response.

Always use the specialized agents via their tools. Do not make up information."""

    orchestrator_agent = Agent(
        model=model,
        tools=[ask_order_agent, ask_product_agent, ask_account_agent],
        system_prompt=system_prompt
    )

    logger.info("Orchestrator Agent initialized")


@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup."""
    initialize_orchestrator()


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

        if orchestrator_agent is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")

        result = orchestrator_agent(user_message)

        response = {
            "message": str(result),
            "agent": "orchestrator",
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
        "agent": "orchestrator",
        "connected_agents": {
            "order_agent": ORDER_AGENT_ARN or "not configured",
            "product_agent": PRODUCT_AGENT_ARN or "not configured",
            "account_agent": ACCOUNT_AGENT_ARN or "not configured"
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
