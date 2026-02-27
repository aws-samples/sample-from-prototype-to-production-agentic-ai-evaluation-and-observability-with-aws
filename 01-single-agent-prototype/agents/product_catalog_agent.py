"""
Product Catalog Agent - Single agent with Role-Based Access Control (RBAC)

This agent handles all product catalog operations with tool access determined
by the user's role (customer vs admin).

- Customer role: Can search, view, compare products and check inventory
- Admin role: Full access including create, update, delete products and manage pricing/inventory

Uses MCP (Model Context Protocol) to connect to the product service MCP server.
Uses Claude Haiku (small LLM) for cost efficiency.
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import logging

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

logging.getLogger("strands").setLevel(logging.INFO)
logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler()]
    )


# Get the current Python executable to ensure MCP server uses same environment
PYTHON_EXECUTABLE = sys.executable

# Model configuration
HAIKU_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


# =============================================================================
# User Session & RBAC
# =============================================================================

@dataclass
class UserSession:
    """
    Represents an authenticated user session with role information.

    In production (Module 03), this maps to JWT claims from AgentCore Identity:
    - user_id -> JWT 'sub' claim
    - role -> JWT custom claim or Cognito group
    - email -> JWT 'email' claim

    For the prototype (Module 01), we simulate this locally.
    """
    user_id: str
    role: str       # "customer" or "admin"
    email: str
    name: str = ""

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_customer(self) -> bool:
        return self.role == "customer"


# Tool names organized by access level
CUSTOMER_TOOLS = [
    "search_products",
    "get_product_details",
    "check_inventory",
    "get_product_recommendations",
    "compare_products",
    "get_return_policy",
]

ADMIN_ONLY_TOOLS = [
    "create_product",
    "update_product",
    "delete_product",
    "update_inventory",
    "update_pricing",
]

ADMIN_TOOLS = CUSTOMER_TOOLS + ADMIN_ONLY_TOOLS


def get_tools_for_role(all_mcp_tools: list, role: str) -> list:
    """
    Filter MCP tools based on user role.

    This is the core RBAC mechanism: the agent only receives tools
    that the user's role is authorized to use. Since the LLM can only
    call tools it knows about, this provides a strong access control boundary.

    Args:
        all_mcp_tools: All tools from the MCP server
        role: User role ("customer" or "admin")

    Returns:
        Filtered list of tools appropriate for the role
    """
    allowed_names = ADMIN_TOOLS if role == "admin" else CUSTOMER_TOOLS
    return [t for t in all_mcp_tools if t.tool_name in allowed_names]


# =============================================================================
# System Prompts by Role
# =============================================================================

CUSTOMER_SYSTEM_PROMPT = """You are a Product Catalog Assistant for an e-commerce store. You help customers find and learn about products.

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
0. For requests to create, update, delete, or modify products or inventory, just say "Sorry that I couldn't do so!".
1. Always use the search or retrieval tools to get accurate, up-to-date information
2. Don't make up product details - if you can't find information, say so
3. When recommending products, consider the customer's use case and budget
4. For inventory questions, provide current stock status and alternatives if unavailable
5. For comparisons, highlight key differences and give objective pros/cons

## Current User
- Role: Customer
- User: {user_name} ({user_email})

## Response Format
- Start with the most relevant information
- Use bullet points for specifications
- Include prices when discussing products
- Mention warranty and return policy for purchase decisions
"""

ADMIN_SYSTEM_PROMPT = """You are a Product Catalog Administrator for an e-commerce store. You have full access to manage the product catalog.

## Your Capabilities

### Read Operations (same as customer)
- Search for products by keywords, features, or categories
- Provide detailed product information and specifications
- Check product availability and inventory
- Give product recommendations
- Compare products
- View return policies and warranties

### Admin Operations
- **Create products**: Add new products to the catalog with full details
- **Update products**: Modify product information (name, description, price, specs, etc.)
- **Delete products**: Remove products from the catalog (soft delete - marks as discontinued)
- **Update inventory**: Adjust stock quantities and set restock dates
- **Update pricing**: Change prices and set sale prices with end dates

## Product Categories
- Audio, Wearables, Monitors, Gaming, Accessories, Cameras, Furniture

## Guidelines
1. Always verify product exists before updating or deleting
2. Use appropriate product ID format: PROD-XXX (e.g., PROD-200)
3. When creating products, ensure all required fields are provided
4. For price changes, confirm the change with the user before executing
5. For deletions, this is a soft delete (marks as discontinued) - explain this to the user
6. Provide specifications as valid JSON when creating/updating products
7. Keep audit trail awareness - all changes are timestamped

## Current User
- Role: Admin
- User: {user_name} ({user_email})

## Response Format
- Confirm actions taken with specific details
- Show before/after values for updates
- Include product IDs in all responses
- Warn about irreversible or high-impact changes
"""


def build_system_prompt(user_session: UserSession) -> str:
    """Build role-appropriate system prompt with user context."""
    template = ADMIN_SYSTEM_PROMPT if user_session.is_admin() else CUSTOMER_SYSTEM_PROMPT
    return template.format(
        user_name=user_session.name or user_session.user_id,
        user_email=user_session.email
    )


# =============================================================================
# Product Catalog Agent
# =============================================================================

class ProductCatalogAgent:
    """
    Product Catalog Agent with role-based access control.

    Connects to the product MCP server and filters available tools
    based on the authenticated user's role.
    """

    def __init__(self, region: str = 'us-west-2', user_session: Optional[UserSession] = None):
        """
        Initialize the Product Catalog Agent.

        Args:
            region: AWS region for Bedrock
            user_session: Authenticated user session with role info.
                         Defaults to a customer role if not provided.
        """
        self.region = region
        self.user_session = user_session or UserSession(
            user_id="anonymous",
            role="customer",
            email="anonymous@example.com",
            name="Guest"
        )
        self.mcp_client = None
        self.agent = None
        self._all_tools = None
        self._setup_agent()

    def _setup_agent(self):
        """Set up the agent with role-filtered MCP tools."""
        # Path to the MCP server
        mcp_server_path = Path(__file__).parent.parent / "mcp_servers" / "product_mcp_server.py"

        # Create server parameters for stdio connection
        server_params = StdioServerParameters(
            command=PYTHON_EXECUTABLE,
            args=[str(mcp_server_path)],
            env={
                **os.environ,
                "AWS_REGION": self.region,
                "PRODUCTS_TABLE": os.environ.get('PRODUCTS_TABLE_NAME', 'ecommerce-workshop-products')
            }
        )

        # Initialize MCP client
        self.mcp_client = MCPClient(lambda: stdio_client(server_params))
        self.mcp_client.__enter__()

        # Get ALL tools from MCP server
        self._all_tools = self.mcp_client.list_tools_sync()

        # Filter tools based on user role (RBAC enforcement)
        role_tools = get_tools_for_role(self._all_tools, self.user_session.role)

        # Build role-aware system prompt
        system_prompt = build_system_prompt(self.user_session)

        # Initialize Bedrock model - Claude Haiku for cost efficiency
        model = BedrockModel(
            model_id=HAIKU_MODEL_ID,
            region_name=self.region,
            temperature=0.3,
            max_tokens=1500
        )

        # Create agent with filtered tools
        self.agent = Agent(
            name="ProductCatalogAgent",
            model=model,
            system_prompt=system_prompt,
            tools=role_tools,
            callback_handler=None # disable the default console output
        )

    def __call__(self, message: str) -> str:
        """
        Process a user message.

        Args:
            message: User's message/query

        Returns:
            str: Agent response
        """
        response = self.agent(message)
        return str(response)

    def get_available_tools(self) -> list:
        """Return the list of tool names available to the current user."""
        allowed_names = ADMIN_TOOLS if self.user_session.is_admin() else CUSTOMER_TOOLS
        return allowed_names

    def get_user_info(self) -> dict:
        """Return current user session info."""
        return {
            'user_id': self.user_session.user_id,
            'role': self.user_session.role,
            'email': self.user_session.email,
            'name': self.user_session.name,
            'tools_available': len(self.get_available_tools()),
            'tools': self.get_available_tools()
        }

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


# =============================================================================
# Factory Functions
# =============================================================================

def create_product_catalog_agent(
    region: str = 'us-west-2',
    user_session: Optional[UserSession] = None
) -> ProductCatalogAgent:
    """
    Create and return a Product Catalog Agent with RBAC.

    Args:
        region: AWS region
        user_session: User session with role info

    Returns:
        ProductCatalogAgent: Configured agent with role-appropriate tools
    """
    return ProductCatalogAgent(region=region, user_session=user_session)


# Pre-built persona sessions for testing
CUSTOMER_PERSONAS = {
    "john": UserSession(
        user_id="CUST-1001",
        role="customer",
        email="john.smith@email.com",
        name="John Smith"
    ),
    "sarah": UserSession(
        user_id="CUST-1002",
        role="customer",
        email="sarah.johnson@email.com",
        name="Sarah Johnson"
    ),
}

ADMIN_PERSONAS = {
    "admin_alice": UserSession(
        user_id="ADMIN-001",
        role="admin",
        email="alice.admin@company.com",
        name="Alice (Admin)"
    ),
    "admin_bob": UserSession(
        user_id="ADMIN-002",
        role="admin",
        email="bob.admin@company.com",
        name="Bob (Admin)"
    ),
}


# For testing
if __name__ == "__main__":
    print("=== Testing Customer Role ===")
    customer_agent = create_product_catalog_agent(
        user_session=CUSTOMER_PERSONAS["john"]
    )
    print(f"User: {customer_agent.get_user_info()}")

    response = customer_agent("Do you have any wireless headphones?")
    print(f"Response: {response}")
    customer_agent.cleanup()

    print("\n=== Testing Admin Role ===")
    admin_agent = create_product_catalog_agent(
        user_session=ADMIN_PERSONAS["admin_alice"]
    )
    print(f"User: {admin_agent.get_user_info()}")

    response = admin_agent("Create a new product PROD-200 called 'Gaming Headset' in the Audio category for $129.99")
    print(f"Response: {response}")
    admin_agent.cleanup()
