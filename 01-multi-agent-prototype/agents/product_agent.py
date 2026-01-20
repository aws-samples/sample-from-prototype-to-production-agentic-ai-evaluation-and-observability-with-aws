"""
Product Agent - Handles product-related customer inquiries

Uses MCP (Model Context Protocol) to connect to the product service MCP server.
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


PRODUCT_AGENT_SYSTEM_PROMPT = """You are a Product Specialist for an e-commerce customer service team. Your role is to help customers find products and answer product-related questions.

## Your Capabilities
- Search for products by keywords, features, or categories
- Provide detailed product information and specifications
- Check product availability and inventory
- Give personalized product recommendations
- Compare products to help customers choose
- Explain return policies and warranties

## Product Categories We Carry
- Audio (headphones, earbuds, speakers)
- Wearables (smartwatches, fitness trackers)
- Monitors & Displays
- Gaming (keyboards, mice, accessories)
- Accessories (hubs, cables, stands)
- Cameras (webcams, action cameras)
- Furniture (office chairs, desks)

## Guidelines
1. Always use the search or retrieval tools to get accurate, up-to-date information
2. Don't make up product details - if you can't find information, say so
3. When recommending products:
   - Ask about budget if not mentioned
   - Consider the customer's use case
   - Mention complementary products when relevant

4. For inventory questions:
   - Provide current stock status
   - If out of stock, give restock date if available
   - Suggest alternatives if item is unavailable

5. For comparisons:
   - Highlight key differences
   - Give a recommendation based on use case
   - Be objective about pros and cons

## Response Format
- Start with the most relevant information
- Use bullet points for specifications
- Include prices when discussing products
- Mention warranty and return policy for purchase decisions
"""


class ProductAgent:
    """Product Agent using MCP tools from the product service MCP server."""

    def __init__(self, region: str = 'us-west-2'):
        """
        Initialize the Product Agent with MCP tools.

        Args:
            region: AWS region for Bedrock
        """
        self.region = region
        self.mcp_client = None
        self.agent = None
        self._setup_agent()

    def _setup_agent(self):
        """Set up the agent with MCP tools from the product service."""
        # Path to the MCP server
        mcp_server_path = Path(__file__).parent.parent / "mcp_servers" / "product_mcp_server.py"

        # Create server parameters for stdio connection
        # Use sys.executable to ensure the MCP server runs with the same Python
        server_params = StdioServerParameters(
            command=PYTHON_EXECUTABLE,
            args=[str(mcp_server_path)],
            env={
                **os.environ,  # Pass through all environment variables
                "AWS_REGION": self.region,
                "PRODUCTS_TABLE": os.environ.get('PRODUCTS_TABLE_NAME', 'ecommerce-workshop-products')
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
            temperature=0.3,  # Slightly higher for creative recommendations
            max_tokens=1500
        )

        # Create agent with MCP tools
        self.agent = Agent(
            name="ProductAgent",
            model=model,
            system_prompt=PRODUCT_AGENT_SYSTEM_PROMPT,
            tools=tools
        )

    def __call__(self, message: str) -> str:
        """
        Process a customer message about products.

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


def create_product_agent(region: str = 'us-west-2') -> ProductAgent:
    """
    Create and return the Product Agent with MCP tools.

    Args:
        region: AWS region

    Returns:
        ProductAgent: Configured product agent
    """
    return ProductAgent(region=region)


# For testing
if __name__ == "__main__":
    agent = create_product_agent()

    test_queries = [
        "Do you have any wireless headphones with noise cancellation?",
        "Is the 4K monitor PROD-042 in stock?"
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        response = agent(query)
        print(f"Response: {response}")

    agent.cleanup()
