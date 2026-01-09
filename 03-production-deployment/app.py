"""
E-Commerce Customer Service Multi-Agent Application

This is the production application deployed to AgentCore Runtime.
It includes the orchestrator and specialized agents with full observability.
"""

import os
import sys
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import AgentCore
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Import Strands
from strands import Agent, tool
from strands.models import BedrockModel

# ============================================================================
# TOOL DEFINITIONS (inline for single-file deployment)
# ============================================================================

import boto3


def get_orders_table():
    """Get DynamoDB orders table"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('ORDERS_TABLE_NAME', 'ecommerce-workshop-orders')
    return dynamodb.Table(table_name)


def get_accounts_table():
    """Get DynamoDB accounts table"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('ACCOUNTS_TABLE_NAME', 'ecommerce-workshop-accounts')
    return dynamodb.Table(table_name)


# Order Tools
@tool
def get_order_status(order_id: str) -> dict:
    """Get the current status and details of an order."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']
        result = {
            'success': True,
            'order_id': order['order_id'],
            'status': order['status'],
            'order_date': order['order_date'],
            'items': order.get('items', []),
            'total': float(order.get('total', 0))
        }

        if order['status'] == 'shipped':
            result['tracking_number'] = order.get('tracking_number', 'N/A')
            result['shipping_carrier'] = order.get('shipping_carrier', 'N/A')

        return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


@tool
def track_shipment(order_id: str) -> dict:
    """Get tracking information for a shipped order."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']
        if order['status'] not in ['shipped', 'delivered']:
            return {'success': False, 'message': f'Order is in "{order["status"]}" status, not yet shipped'}

        return {
            'success': True,
            'order_id': order_id,
            'status': order['status'],
            'carrier': order.get('shipping_carrier', 'N/A'),
            'tracking_number': order.get('tracking_number', 'N/A'),
            'estimated_delivery': order.get('estimated_delivery', order.get('delivery_date', 'N/A'))
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@tool
def process_return(order_id: str, reason: str) -> dict:
    """Initiate a return request for an order."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']
        if order['status'] not in ['delivered', 'shipped']:
            return {'success': False, 'message': f'Cannot return order in "{order["status"]}" status'}

        table.update_item(
            Key={'order_id': order_id},
            UpdateExpression='SET #status = :status, return_reason = :reason',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'return_requested',
                ':reason': reason
            }
        )

        return {
            'success': True,
            'order_id': order_id,
            'message': f'Return request submitted. You will receive a shipping label via email.'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# Product Tools
@tool
def search_products(query: str, max_results: int = 5) -> dict:
    """Search for products using Bedrock Knowledge Base."""
    try:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        kb_id = os.environ.get('KNOWLEDGE_BASE_ID')

        if not kb_id:
            return {'success': False, 'error': 'Knowledge Base ID not configured'}

        client = boto3.client('bedrock-agent-runtime', region_name=region)
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {'numberOfResults': max_results}
            }
        )

        results = [
            {'content': r.get('content', {}).get('text', ''), 'score': r.get('score', 0)}
            for r in response.get('retrievalResults', [])
        ]

        return {'success': True, 'query': query, 'results': results}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@tool
def check_inventory(product_id: str) -> dict:
    """Check inventory for a product."""
    inventory = {
        'PROD-001': {'in_stock': True, 'quantity': 150},
        'PROD-015': {'in_stock': True, 'quantity': 75},
        'PROD-042': {'in_stock': True, 'quantity': 45},
        'PROD-088': {'in_stock': False, 'quantity': 0, 'restock_date': '2025-01-15'},
        'PROD-101': {'in_stock': True, 'quantity': 25}
    }

    if product_id in inventory:
        return {'success': True, 'product_id': product_id, **inventory[product_id]}
    return {'success': False, 'error': f'Product {product_id} not found'}


# Account Tools
@tool
def get_account_info(customer_email: str) -> dict:
    """Get customer account information."""
    try:
        table = get_accounts_table()
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        if not response.get('Items'):
            return {'success': False, 'error': f'Account not found for {customer_email}'}

        account = response['Items'][0]
        return {
            'success': True,
            'email': account['email'],
            'name': f"{account['first_name']} {account['last_name']}",
            'membership_tier': account['membership_tier'],
            'account_status': account['account_status']
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@tool
def get_membership_benefits(tier: str) -> dict:
    """Get membership tier benefits."""
    benefits = {
        'standard': {'shipping_threshold': 50, 'points_multiplier': 1.0, 'return_days': 30},
        'gold': {'shipping_threshold': 25, 'points_multiplier': 1.5, 'return_days': 45},
        'platinum': {'shipping_threshold': 0, 'points_multiplier': 2.0, 'return_days': 60}
    }

    tier_lower = tier.lower()
    if tier_lower in benefits:
        return {'success': True, 'tier': tier, **benefits[tier_lower]}
    return {'success': False, 'error': f'Unknown tier: {tier}'}


# ============================================================================
# AGENT DEFINITIONS
# ============================================================================

REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Models (global cross-region inference profiles)
HAIKU_MODEL = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET_MODEL = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"


def create_order_agent():
    """Create Order Agent with Haiku"""
    model = BedrockModel(model_id=HAIKU_MODEL, region_name=REGION, temperature=0.1)
    return Agent(
        name="OrderAgent",
        model=model,
        system_prompt="""You are an Order Specialist. Help customers with order status, tracking, returns, and cancellations.
        Always verify order IDs and provide clear status updates. Be empathetic with issues.""",
        tools=[get_order_status, track_shipment, process_return]
    )


def create_product_agent():
    """Create Product Agent with Haiku"""
    model = BedrockModel(model_id=HAIKU_MODEL, region_name=REGION, temperature=0.3)
    return Agent(
        name="ProductAgent",
        model=model,
        system_prompt="""You are a Product Specialist. Help customers find products, check inventory, and get recommendations.
        Use the knowledge base to provide accurate product information.""",
        tools=[search_products, check_inventory]
    )


def create_account_agent():
    """Create Account Agent with Haiku"""
    model = BedrockModel(model_id=HAIKU_MODEL, region_name=REGION, temperature=0.1)
    return Agent(
        name="AccountAgent",
        model=model,
        system_prompt="""You are an Account Specialist. Help customers with account info, membership benefits, and settings.
        Protect sensitive information and verify customer identity.""",
        tools=[get_account_info, get_membership_benefits]
    )


# Create agent instances
_order_agent = None
_product_agent = None
_account_agent = None


def get_agents():
    """Lazy initialization of agents"""
    global _order_agent, _product_agent, _account_agent
    if _order_agent is None:
        _order_agent = create_order_agent()
        _product_agent = create_product_agent()
        _account_agent = create_account_agent()
    return _order_agent, _product_agent, _account_agent


# Create orchestrator tools
@tool
def delegate_to_order_agent(query: str) -> str:
    """Delegate order-related queries (status, tracking, returns) to Order Agent."""
    order_agent, _, _ = get_agents()
    return str(order_agent(query))


@tool
def delegate_to_product_agent(query: str) -> str:
    """Delegate product queries (search, inventory, recommendations) to Product Agent."""
    _, product_agent, _ = get_agents()
    return str(product_agent(query))


@tool
def delegate_to_account_agent(query: str) -> str:
    """Delegate account queries (info, membership, settings) to Account Agent."""
    _, _, account_agent = get_agents()
    return str(account_agent(query))


def create_orchestrator():
    """Create Orchestrator with Sonnet"""
    model = BedrockModel(model_id=SONNET_MODEL, region_name=REGION, temperature=0.2)
    return Agent(
        name="CustomerServiceOrchestrator",
        model=model,
        system_prompt="""You are the Customer Service Orchestrator. Route customer requests to the appropriate agent:
        - Order Agent: order status, tracking, returns, cancellations
        - Product Agent: product search, inventory, recommendations
        - Account Agent: account info, membership, settings

        For complex queries spanning multiple domains, consult multiple agents and synthesize responses.""",
        tools=[delegate_to_order_agent, delegate_to_product_agent, delegate_to_account_agent]
    )


# ============================================================================
# AGENTCORE APPLICATION
# ============================================================================

app = BedrockAgentCoreApp()
orchestrator = None


@app.entrypoint
def invoke(payload, context=None):
    """Main entry point for AgentCore Runtime"""
    global orchestrator

    prompt = payload.get("prompt", "Hello, how can I help you?")
    session_id = context.session_id if context else "default"

    logger.info(f"Processing request - Session: {session_id}")
    logger.info(f"Prompt: {prompt[:100]}...")

    try:
        # Lazy initialize orchestrator
        if orchestrator is None:
            orchestrator = create_orchestrator()
            logger.info("Orchestrator initialized")

        # Process request
        response = orchestrator(prompt)
        response_text = str(response)

        logger.info(f"Response generated - Length: {len(response_text)}")

        return {"response": response_text}

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return {"response": f"I apologize, but I encountered an error: {str(e)}"}


if __name__ == "__main__":
    app.run()
