"""
Order Agent - Handles order-related customer inquiries

Uses MCP (Model Context Protocol) to connect to the order service MCP server.
Uses Claude Haiku (small LLM) for cost efficiency.
"""

import os
import sys
from pathlib import Path

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

# Get the current Python executable to ensure MCP server uses same environment
PYTHON_EXECUTABLE = sys.executable


ORDER_AGENT_SYSTEM_PROMPT = """You are an Order Specialist for an e-commerce customer service team. Your role is to help customers with all order-related inquiries.

## Your Capabilities
- Check order status and details
- Track shipments and provide delivery estimates
- Process return requests
- Cancel or modify orders (when possible)
- Look up customer order history

## Guidelines
1. Always verify the order ID format (ORD-YYYY-NNNNN) before proceeding
2. Be empathetic when customers have issues with their orders
3. Clearly explain order statuses:
   - pending: Order received, payment processing
   - processing: Order confirmed, preparing for shipment
   - shipped: Order dispatched, in transit
   - delivered: Order delivered to customer
   - return_requested: Return initiated
   - refunded: Refund processed
   - cancelled: Order cancelled

4. For returns:
   - Confirm the order is within 30-day return window
   - Ask for return reason if not provided
   - Explain the return process clearly

5. For order modifications:
   - Only pending/processing orders can be modified
   - Be clear about what can and cannot be changed

6. If you cannot help with something, suggest the customer contact a human agent

## Response Format
- Be concise but complete
- Always confirm the action taken
- Provide next steps when applicable
- Include relevant order numbers in your response
"""


class OrderAgent:
    """Order Agent using MCP tools from the order service MCP server."""

    def __init__(self, region: str = 'us-west-2'):
        """
        Initialize the Order Agent with MCP tools.

        Args:
            region: AWS region for Bedrock
        """
        self.region = region
        self.mcp_client = None
        self.agent = None
        self._setup_agent()

    def _setup_agent(self):
        """Set up the agent with MCP tools from the order service."""
        # Path to the MCP server
        mcp_server_path = Path(__file__).parent.parent / "mcp_servers" / "order_mcp_server.py"

        # Create server parameters for stdio connection
        # Use sys.executable to ensure the MCP server runs with the same Python
        server_params = StdioServerParameters(
            command=PYTHON_EXECUTABLE,
            args=[str(mcp_server_path)],
            env={
                **os.environ,  # Pass through all environment variables
                "AWS_REGION": self.region,
                "ORDERS_TABLE_NAME": os.environ.get('ORDERS_TABLE_NAME', 'ecommerce-workshop-orders')
            }
        )

        # Initialize MCP client
        self.mcp_client = MCPClient(lambda: stdio_client(server_params))
        self.mcp_client.__enter__()

        # Get tools from MCP server
        tools = self.mcp_client.list_tools_sync()

        # Initialize Bedrock model - Claude Haiku for cost efficiency
        model = BedrockModel(
            model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            region_name=self.region,
            temperature=0.1,  # Low temperature for consistent responses
            max_tokens=1024
        )

        # Create agent with MCP tools
        self.agent = Agent(
            name="OrderAgent",
            model=model,
            system_prompt=ORDER_AGENT_SYSTEM_PROMPT,
            tools=tools
        )

    def __call__(self, message: str) -> str:
        """
        Process a customer message about orders.

        Args:
            message: Customer message

        Returns:
            str: Agent response
        """
        response = self.agent(message)
        return str(response)

    def cleanup(self):
        """Clean up MCP client resources."""
        if self.mcp_client:
            try:
                self.mcp_client.__exit__(None, None, None)
            except Exception:
                pass

    def __del__(self):
        """Destructor to clean up resources."""
        self.cleanup()


def create_order_agent(region: str = 'us-west-2') -> OrderAgent:
    """
    Create and return the Order Agent with MCP tools.

    Args:
        region: AWS region

    Returns:
        OrderAgent: Configured order agent
    """
    return OrderAgent(region=region)


# For testing
if __name__ == "__main__":
    agent = create_order_agent()

    test_queries = [
        "What's the status of order ORD-2024-10002?",
        "Can you track my shipment for order ORD-2024-10009?"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        response = agent(query)
        print(f"Response: {response}")

    agent.cleanup()
