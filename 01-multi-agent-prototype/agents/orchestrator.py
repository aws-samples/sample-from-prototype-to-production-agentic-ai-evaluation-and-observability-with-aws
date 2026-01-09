"""
Orchestrator Agent - Routes customer requests to appropriate specialized agents

Uses Claude Sonnet (large LLM) for complex reasoning and coordination.
"""

from strands import Agent, tool
from strands.models import BedrockModel
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from order_agent import create_order_agent
from product_agent import create_product_agent
from account_agent import create_account_agent


# Global agent instances (created lazily)
_order_agent = None
_product_agent = None
_account_agent = None


def _get_order_agent(region: str):
    global _order_agent
    if _order_agent is None:
        _order_agent = create_order_agent(region)
    return _order_agent


def _get_product_agent(region: str):
    global _product_agent
    if _product_agent is None:
        _product_agent = create_product_agent(region)
    return _product_agent


def _get_account_agent(region: str):
    global _account_agent
    if _account_agent is None:
        _account_agent = create_account_agent(region)
    return _account_agent


# Define tools that wrap the specialized agents
def create_agent_tools(region: str):
    """Create tool wrappers for specialized agents"""

    @tool
    def delegate_to_order_agent(query: str) -> str:
        """
        Delegate order-related queries to the Order Agent.

        Use this for queries about:
        - Order status and tracking
        - Shipment tracking
        - Returns and refunds
        - Order cancellation or modification
        - Order history

        Args:
            query: The customer's order-related question or request

        Returns:
            str: The Order Agent's response
        """
        agent = _get_order_agent(region)
        response = agent(query)
        return str(response)

    @tool
    def delegate_to_product_agent(query: str) -> str:
        """
        Delegate product-related queries to the Product Agent.

        Use this for queries about:
        - Product search and discovery
        - Product specifications and details
        - Inventory and availability
        - Product recommendations
        - Product comparisons
        - Return policies and warranties

        Args:
            query: The customer's product-related question or request

        Returns:
            str: The Product Agent's response
        """
        agent = _get_product_agent(region)
        response = agent(query)
        return str(response)

    @tool
    def delegate_to_account_agent(query: str) -> str:
        """
        Delegate account-related queries to the Account Agent.

        Use this for queries about:
        - Account information and settings
        - Shipping address updates
        - Payment methods
        - Password reset
        - Notification preferences
        - Membership and benefits

        Args:
            query: The customer's account-related question or request

        Returns:
            str: The Account Agent's response
        """
        agent = _get_account_agent(region)
        response = agent(query)
        return str(response)

    return [delegate_to_order_agent, delegate_to_product_agent, delegate_to_account_agent]


ORCHESTRATOR_SYSTEM_PROMPT = """You are the Customer Service Orchestrator for an e-commerce company. Your role is to understand customer needs and route their requests to the appropriate specialized agent.

## Your Role
You coordinate between three specialized agents:
1. **Order Agent**: Handles order status, tracking, returns, modifications
2. **Product Agent**: Handles product search, details, inventory, recommendations
3. **Account Agent**: Handles account settings, addresses, payments, passwords

## How to Route Requests

### Route to Order Agent when customer asks about:
- Order status ("Where is my order?", "What's the status of order #X?")
- Shipment tracking ("Track my package", "When will my order arrive?")
- Returns ("I want to return this", "How do I send this back?")
- Refunds ("Where is my refund?", "I need a refund")
- Order cancellation ("Cancel my order")
- Order modifications ("Change my shipping address for order X")
- Order history ("Show my recent orders")

### Route to Product Agent when customer asks about:
- Product search ("Do you have wireless headphones?")
- Product details ("Tell me about product X", "What are the specs?")
- Inventory ("Is this in stock?", "When will it be available?")
- Recommendations ("What do you recommend for gaming?")
- Comparisons ("Compare product A vs B")
- Warranties/policies ("What's the return policy?", "Is this covered by warranty?")

### Route to Account Agent when customer asks about:
- Account info ("What's my account status?")
- Address updates ("Change my address")
- Payment methods ("Show my saved cards", "Update payment method")
- Password ("Reset my password", "I forgot my password")
- Notifications ("Turn off email notifications")
- Membership ("What are Gold member benefits?")

## Complex Queries
For queries that span multiple domains, break them down and route to each relevant agent sequentially:
- "I want to return order #X and buy a different product" → Order Agent (return) then Product Agent (recommendations)
- "Update my address and show my recent orders" → Account Agent (address) then Order Agent (orders)

## Guidelines
1. **Understand First**: Make sure you understand what the customer needs before routing
2. **Single Routing When Possible**: If a query fits one category, route to one agent
3. **Multi-Agent for Complex**: Use multiple agents only when truly necessary
4. **Preserve Context**: Pass relevant context to the specialized agent
5. **Synthesize Responses**: When using multiple agents, combine their responses coherently
6. **Handle Ambiguity**: If unclear, ask the customer for clarification
7. **Be Helpful**: If something is outside your scope, acknowledge and suggest alternatives

## Response Format
- Provide clear, helpful responses
- Include relevant details from specialized agents
- Format information in an easy-to-read manner
- If multiple agents were consulted, present a unified response
"""


def create_orchestrator(region: str = 'us-east-1') -> Agent:
    """Create and return the Orchestrator Agent instance"""

    # Use Claude Sonnet 4.5 for complex reasoning and coordination (global cross-region inference)
    model = BedrockModel(
        model_id="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        region_name=region,
        temperature=0.2,
        max_tokens=2048
    )

    # Create agent tools
    tools = create_agent_tools(region)

    agent = Agent(
        name="CustomerServiceOrchestrator",
        model=model,
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        tools=tools
    )

    return agent


class MultiAgentCustomerService:
    """
    Multi-Agent Customer Service System

    This class provides a convenient interface for the multi-agent system
    and tracks usage metrics for cost analysis.
    """

    def __init__(self, region: str = 'us-east-1'):
        self.region = region
        self.orchestrator = create_orchestrator(region)

        # Usage tracking
        self.total_requests = 0
        self.orchestrator_calls = 0
        self.order_agent_calls = 0
        self.product_agent_calls = 0
        self.account_agent_calls = 0

    def chat(self, message: str) -> str:
        """
        Process a customer message through the multi-agent system.

        Args:
            message: Customer's message/query

        Returns:
            str: Response from the agent system
        """
        self.total_requests += 1
        self.orchestrator_calls += 1

        response = self.orchestrator(message)

        return str(response)

    def get_usage_stats(self) -> dict:
        """Get usage statistics for cost analysis"""
        return {
            'total_requests': self.total_requests,
            'orchestrator_calls': self.orchestrator_calls,
            'order_agent_calls': self.order_agent_calls,
            'product_agent_calls': self.product_agent_calls,
            'account_agent_calls': self.account_agent_calls
        }

    def reset_stats(self):
        """Reset usage statistics"""
        self.total_requests = 0
        self.orchestrator_calls = 0
        self.order_agent_calls = 0
        self.product_agent_calls = 0
        self.account_agent_calls = 0


# For testing
if __name__ == "__main__":
    # Create the multi-agent system
    service = MultiAgentCustomerService()

    # Test queries across different domains
    test_queries = [
        "What's the status of order ORD-2024-10002?",
        "Do you have any wireless headphones under $100?",
        "I need to reset my password for john.smith@email.com",
        "I want to return order ORD-2024-10001 and buy a different headphone"
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Customer: {query}")
        print("-" * 60)
        response = service.chat(query)
        print(f"Agent: {response}")

    print(f"\n{'='*60}")
    print("Usage Stats:", service.get_usage_stats())
