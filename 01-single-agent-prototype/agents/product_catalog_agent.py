"""
Product Catalog Agent - Single agent with Role-Based Access Control (RBAC)

This agent handles all product catalog operations with tool access determined
by the user's role (customer vs admin).

- Customer role: Can search, view, compare products and check inventory
- Admin role: Full access including create, update, delete products and manage pricing/inventory

Uses MCP (Model Context Protocol) to connect to the product service MCP server.
Uses Claude Sonnet 4.6 for high-quality responses.
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
from config_loader import AgentBehaviorConfig, load_agent_behavior_config

logging.getLogger("strands").setLevel(logging.INFO)
logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler()]
    )


# Get the current Python executable to ensure MCP server uses same environment
PYTHON_EXECUTABLE = sys.executable

# Versioned local behavior contract
BEHAVIOR_CONFIG = load_agent_behavior_config()

# Model and policy constants kept for compatibility with later notebooks.
SONNET_MODEL_ID = BEHAVIOR_CONFIG.model_config["model_id"]
CUSTOMER_TOOLS = BEHAVIOR_CONFIG.tools_for_role("customer")
ADMIN_TOOLS = BEHAVIOR_CONFIG.tools_for_role("admin")
ADMIN_ONLY_TOOLS = [tool for tool in ADMIN_TOOLS if tool not in CUSTOMER_TOOLS]


# =============================================================================
# User Session & RBAC
# =============================================================================

@dataclass
class UserSession:
    """
    Represents an authenticated user session with role information.

    For the prototype (Module 01), we simulate this locally.
    Later sections can replace this local role source while keeping the same
    role-to-tool behavior contract.
    """
    user_id: str
    role: str       # "customer" or "admin"
    email: str
    name: str = ""

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_customer(self) -> bool:
        return self.role == "customer"


def strip_tool_prefix(tool_name: str) -> str:
    """Return a plain MCP tool name, tolerating future prefixed tool names."""
    delimiter = "___"
    if delimiter in tool_name:
        return tool_name[tool_name.index(delimiter) + len(delimiter) :]
    return tool_name


def get_mcp_tool_name(tool) -> str:
    """Return the tool name from an MCP tool-like object."""
    return strip_tool_prefix(getattr(tool, "tool_name", getattr(tool, "name", "")))


def get_tools_for_role(
    all_mcp_tools: list,
    role: str,
    behavior_config: AgentBehaviorConfig | None = None,
) -> list:
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
    config = behavior_config or BEHAVIOR_CONFIG
    allowed_names = set(config.tools_for_role(role))
    return [t for t in all_mcp_tools if get_mcp_tool_name(t) in allowed_names]


# =============================================================================
# System Prompts by Role
# =============================================================================

CUSTOMER_SYSTEM_PROMPT = BEHAVIOR_CONFIG.prompts["customer"]
ADMIN_SYSTEM_PROMPT = BEHAVIOR_CONFIG.prompts["admin"]


def build_system_prompt(
    user_session: UserSession,
    behavior_config: AgentBehaviorConfig | None = None,
) -> str:
    """Build role-appropriate system prompt with user context."""
    config = behavior_config or BEHAVIOR_CONFIG
    return config.render_prompt(
        role=user_session.role,
        user_name=user_session.name or user_session.user_id,
        user_email=user_session.email,
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

    def __init__(
        self,
        region: str = 'us-west-2',
        user_session: Optional[UserSession] = None,
        behavior_config: Optional[AgentBehaviorConfig] = None,
    ):
        """
        Initialize the Product Catalog Agent.

        Args:
            region: AWS region for Bedrock
            user_session: Authenticated user session with role info.
                         Defaults to a customer role if not provided.
        """
        self.region = region
        self.behavior_config = behavior_config or BEHAVIOR_CONFIG
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
        mcp_server = self.behavior_config.mcp_server_config
        mcp_server_path = self.behavior_config.section_dir / mcp_server["path"]

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
        role_tools = get_tools_for_role(
            self._all_tools,
            self.user_session.role,
            self.behavior_config,
        )

        # Build role-aware system prompt
        system_prompt = build_system_prompt(self.user_session, self.behavior_config)

        # Initialize Bedrock model
        model_config = self.behavior_config.model_config
        model = BedrockModel(
            model_id=model_config["model_id"],
            region_name=self.region,
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
        )

        # Create agent with filtered tools
        self.agent = Agent(
            name=self.behavior_config.agent_name,
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
        return self.behavior_config.tools_for_role(self.user_session.role)

    def get_user_info(self) -> dict:
        """Return current user session info."""
        available_tools = self.get_available_tools()
        return {
            'user_id': self.user_session.user_id,
            'role': self.user_session.role,
            'email': self.user_session.email,
            'name': self.user_session.name,
            'tools_available': len(available_tools),
            'tools': available_tools,
        }

    def get_agent_manifest(self) -> dict:
        """
        Return a JSON-serializable local behavior manifest for this agent run.

        The manifest does not create or modify resources. It records the local
        configuration contract that later lifecycle sections can consume.
        """
        available_tools = self.get_available_tools()
        resolved_role = self.behavior_config.normalize_role(self.user_session.role)
        manifest = self.behavior_config.base_manifest()
        manifest["model"]["region"] = self.region
        manifest["role"] = {
            "requested": self.user_session.role,
            "resolved": resolved_role,
            "default_role_applied": resolved_role != self.user_session.role,
        }
        manifest["user_session"] = {
            "user_id": self.user_session.user_id,
            "role": self.user_session.role,
            "email": self.user_session.email,
            "name": self.user_session.name,
        }
        manifest["available_tools"] = available_tools
        manifest["tool_metadata"] = self.behavior_config.metadata_for_tools(
            available_tools
        )
        return manifest

    def cleanup(self):
        """Clean up MCP client resources."""
        if getattr(self, "mcp_client", None):
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
