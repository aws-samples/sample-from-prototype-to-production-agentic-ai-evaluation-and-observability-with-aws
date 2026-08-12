"""
Product Catalog Agent for AgentCore Runtime

Production version of the single Product Catalog Agent from Module 01.
Deployed as a container to AgentCore Runtime with:
  - Gateway MCP tools via SigV4 authentication
  - JWT-based RBAC (role extracted from Cognito JWT claims)
  - Role-aware system prompts
  - BedrockAgentCoreApp entrypoint

The RBAC pattern from Module 01 (local UserSession) maps to production as:
  Module 01: UserSession.role field -> Module 03: JWT cognito:groups claim
"""

import base64
import json
import logging
import os
from urllib.parse import urlparse

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp, BedrockAgentCoreContext
from opentelemetry import trace
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
tracer = trace.get_tracer(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
GATEWAY_URL = os.environ.get("GATEWAY_URL", "")
AGENT_REGION = os.environ.get("AGENT_REGION", os.environ.get("AWS_REGION", "us-west-2"))
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-4-6")
DEPLOYMENT_ID = os.environ.get("DEPLOYMENT_ID", "unknown")
AGENT_VERSION = os.environ.get("AGENT_VERSION", "section03-local")
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "unknown")
TOOL_POLICY_VERSION = os.environ.get("TOOL_POLICY_VERSION", "unknown")
OTEL_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "product-catalog-agent")

SAFE_TRACE_ATTRIBUTE_KEYS = {
    "deployment.id",
    "agent.version",
    "agent.model_id",
    "agent.prompt_version",
    "agent.tool_policy_version",
    "runtime.role",
    "runtime.session_id",
    "runtime.region",
    "gateway.url_host",
    "tools.available_count",
    "tools.allowed_count",
    "tools.used_count",
    "operation.status",
    "error.type",
}

# ---------------------------------------------------------------------------
# RBAC constants (same as Module 01)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
CUSTOMER_SYSTEM_PROMPT = """You are the Product Catalog Assistant for our e-commerce store.
You are helping a customer browse and explore products.

Your capabilities:
- Search for products by keywords or category
- Show detailed product information
- Check inventory and stock availability
- Recommend products based on preferences
- Compare products side by side
- Explain return policies and warranties

Product categories we carry:
- Audio (headphones, earbuds, speakers)
- Wearables (smartwatches, fitness trackers)
- Monitors & Displays
- Gaming (keyboards, mice, accessories)
- Accessories (hubs, cables, stands)
- Cameras (webcams, action cameras)
- Furniture (office chairs, desks)
Only use these categories when searching - do not invent other category names.

Guidelines:
- Product IDs are sparse and non-sequential (e.g. PROD-001, PROD-008, PROD-015).
  Never guess a product ID from a number the customer mentions - search for the
  product first, or ask the customer to clarify which product they mean.
- Always use the search or retrieval tools to get accurate, up-to-date information.
- Don't make up product details - if you can't find information, say so.

You do NOT have access to any administrative functions like creating, updating,
or deleting products. If a customer asks you to modify the catalog, politely explain
that these operations require administrator privileges.

Hypothetical or "what if" questions are NOT action requests. If a customer asks
what would happen if a price, stock level, or product detail changed, answer the
hypothetical question directly and helpfully (you may look up current details for
context), then note that actual changes require administrator access. Do not
refuse to discuss a hypothetical scenario.

Always be helpful, accurate, and customer-focused."""

ADMIN_SYSTEM_PROMPT = """You are the Product Catalog Assistant for our e-commerce store.
You are helping an administrator manage the product catalog.

Your capabilities include ALL customer tools PLUS administrative functions:
- Create new products in the catalog
- Update existing product information
- Delete (discontinue) products
- Manage inventory levels
- Update pricing and set sales

Product categories: Audio, Wearables, Monitors, Gaming, Accessories, Cameras, Furniture.
Only use these categories when searching - do not invent other category names.

Product IDs are sparse and non-sequential (e.g. PROD-001, PROD-008, PROD-015).
Never guess a product ID from a number the user mentions - search for the
product first, or ask the user to clarify which product they mean.

Use administrative tools carefully. Always confirm important changes.
For deletions, note that they are soft deletes (products are marked as discontinued)."""


def safe_error(exc: Exception) -> str:
    """Return a token-safe error string for logs and responses."""
    return f"{type(exc).__name__}: see runtime logs for sanitized context"


def gateway_host() -> str:
    """Return the Gateway host without path, query string, or credentials."""
    try:
        return urlparse(GATEWAY_URL).netloc
    except Exception:
        return "unknown"


def base_trace_attributes(role: str = None, session_id: str = None) -> dict:
    """Safe release/runtime attributes for custom spans."""
    attrs = {
        "deployment.id": DEPLOYMENT_ID,
        "agent.version": AGENT_VERSION,
        "agent.model_id": MODEL_ID,
        "agent.prompt_version": PROMPT_VERSION,
        "agent.tool_policy_version": TOOL_POLICY_VERSION,
        "runtime.region": AGENT_REGION,
        "gateway.url_host": gateway_host() if GATEWAY_URL else None,
    }
    if role:
        attrs["runtime.role"] = role
    if session_id:
        attrs["runtime.session_id"] = session_id
    return attrs


def set_safe_span_attributes(span, attrs: dict) -> None:
    """Attach only allowlisted non-empty span attributes."""
    if not span:
        return
    for key, value in attrs.items():
        if key not in SAFE_TRACE_ATTRIBUTE_KEYS or value is None:
            continue
        span.set_attribute(key, value)


def decode_jwt_claims(token: str) -> dict:
    """Decode JWT payload to extract claims."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as e:
        logger.warning("JWT claim decoding failed: %s", type(e).__name__)
        return {}


def get_role_from_jwt(token: str) -> str:
    """Extract role from JWT cognito:groups claim."""
    claims = decode_jwt_claims(token)
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = [groups]
    return "admin" if "admin" in groups else "customer"


def get_tools_for_role(all_tools: list, role: str) -> list:
    """Filter MCP tools based on user role."""
    allowed = ADMIN_TOOLS if role == "admin" else CUSTOMER_TOOLS
    return [t for t in all_tools if strip_prefix(t.tool_name) in allowed]


def strip_prefix(tool_name: str) -> str:
    """Strip Gateway target prefix from tool name."""
    delimiter = "___"
    if delimiter in tool_name:
        return tool_name[tool_name.index(delimiter) + len(delimiter) :]
    return tool_name


def get_config_bundle() -> dict:
    """Read the AgentCore configuration bundle injected by Gateway A/B routing."""
    try:
        bundle = BedrockAgentCoreContext.get_config_bundle()
        return bundle if isinstance(bundle, dict) else {}
    except Exception as exc:
        logger.warning("Configuration bundle unavailable: %s", type(exc).__name__)
        return {}


def resolve_system_prompt(role: str, bundle: dict = None) -> str:
    """Choose the role-aware prompt, with bundle overrides when present."""
    default_prompt = ADMIN_SYSTEM_PROMPT if role == "admin" else CUSTOMER_SYSTEM_PROMPT
    bundle = bundle or {}

    if isinstance(bundle.get("system_prompt"), str):
        return bundle["system_prompt"]

    prompts = bundle.get("system_prompts")
    if isinstance(prompts, dict):
        return (
            prompts.get(role)
            or prompts.get("recommended_combined")
            or default_prompt
        )
    return default_prompt


def apply_tool_description_overrides(tools: list, bundle: dict = None) -> None:
    """Apply bundle tool-description overrides to Strands MCP tool specs."""
    bundle = bundle or {}
    descriptions = bundle.get("tool_descriptions")
    if not isinstance(descriptions, dict) or not descriptions:
        return

    for tool in tools:
        tool_name = getattr(tool, "tool_name", "")
        plain_name = strip_prefix(tool_name)
        description = descriptions.get(plain_name) or descriptions.get(tool_name)
        if not description or not hasattr(tool, "tool_spec"):
            continue
        try:
            tool.tool_spec["description"] = str(description)
        except Exception:
            logger.warning("Could not update tool description for %s", plain_name)


# ---------------------------------------------------------------------------
# SigV4 transport for Gateway MCP connection
# ---------------------------------------------------------------------------
def create_sigv4_mcp_client(gateway_url: str, region: str, bearer_token: str = None):
    """
    Create an MCP client that connects to AgentCore Gateway.
    Uses Bearer JWT for CUSTOM_JWT gateways, or SigV4 for AWS_IAM gateways.
    """
    from mcp.client.streamable_http import streamablehttp_client

    if bearer_token:
        # CUSTOM_JWT gateway: use Bearer token only (SigV4 would overwrite Authorization header)
        def transport():
            return streamablehttp_client(
                url=gateway_url, headers={"Authorization": f"Bearer {bearer_token}"}
            )
    else:
        # AWS_IAM gateway: use SigV4 signing
        import httpx
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        session = boto3.Session(region_name=region)
        credentials = session.get_credentials().get_frozen_credentials()

        class SigV4Auth_HTTPX(httpx.Auth):
            def auth_flow(self, request: httpx.Request):
                headers = dict(request.headers)
                headers.pop("connection", None)
                aws_req = AWSRequest(
                    method=request.method,
                    url=str(request.url),
                    data=request.content,
                    headers=headers,
                )
                SigV4Auth(credentials, "bedrock-agentcore", region).add_auth(aws_req)
                request.headers.update(dict(aws_req.headers))
                yield request

        def transport():
            return streamablehttp_client(url=gateway_url, auth=SigV4Auth_HTTPX())

    return MCPClient(transport)


# ---------------------------------------------------------------------------
# BedrockAgentCoreApp
# ---------------------------------------------------------------------------
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload=None, **kwargs):
    """
    Main entry point for AgentCore Runtime invocations.

    Expected payload:
    {
        "prompt": "user message",
        "session_id": "optional session id",
        "bearer_token": "optional JWT for role extraction"
    }

    The bearer_token is passed by the frontend after Cognito login.
    It contains cognito:groups claim used for RBAC.
    """
    with tracer.start_as_current_span("product_catalog.runtime_invocation") as root_span:
        if not payload:
            set_safe_span_attributes(
                root_span,
                {**base_trace_attributes(), "operation.status": "missing_payload"},
            )
            return {"error": "No payload provided"}

        # Handle warmup
        if payload.get("warmup"):
            set_safe_span_attributes(
                root_span,
                {**base_trace_attributes(), "operation.status": "warmup"},
            )
            return {"status": "warmed"}

        prompt = payload.get("prompt", "")
        bearer_token = payload.get("bearer_token", "")  # ID token for role extraction
        access_token = payload.get("access_token", "")  # Access token for Gateway auth
        session_id = payload.get("session_id", "default")

        if not prompt:
            set_safe_span_attributes(
                root_span,
                {
                    **base_trace_attributes(session_id=session_id),
                    "operation.status": "missing_prompt",
                },
            )
            return {"error": "No prompt provided"}

        # Determine role from JWT
        role = "customer"  # Default to least privilege
        with tracer.start_as_current_span("product_catalog.jwt_role_extraction") as span:
            if bearer_token:
                role = get_role_from_jwt(bearer_token)
            set_safe_span_attributes(
                span,
                {**base_trace_attributes(role, session_id), "operation.status": "ok"},
            )
        logger.info("Runtime invocation role=%s session_id=%s", role, session_id)
        set_safe_span_attributes(root_span, base_trace_attributes(role, session_id))

        # Connect to Gateway MCP tools
        if not GATEWAY_URL:
            set_safe_span_attributes(root_span, {"operation.status": "gateway_missing"})
            return {"error": "GATEWAY_URL not configured"}

        # Use access_token for Gateway auth (has client_id claim for CUSTOM_JWT validation)
        # Fall back to bearer_token (ID token) if no access_token provided
        gateway_token = access_token or bearer_token
        config_bundle = get_config_bundle()
        mcp_client = create_sigv4_mcp_client(GATEWAY_URL, AGENT_REGION, gateway_token)

        try:
            with tracer.start_as_current_span("product_catalog.gateway_mcp_connection") as span:
                set_safe_span_attributes(
                    span,
                    {**base_trace_attributes(role, session_id), "operation.status": "connecting"},
                )
                mcp_client.__enter__()
                set_safe_span_attributes(span, {"operation.status": "connected"})

            with tracer.start_as_current_span("product_catalog.tool_discovery") as span:
                all_tools = mcp_client.list_tools_sync()
                set_safe_span_attributes(
                    span,
                    {
                        **base_trace_attributes(role, session_id),
                        "tools.available_count": len(all_tools),
                        "operation.status": "ok",
                    },
                )

            # Filter tools by role (application-level RBAC - defense in depth)
            with tracer.start_as_current_span("product_catalog.rbac_tool_filtering") as span:
                role_tools = get_tools_for_role(all_tools, role)
                set_safe_span_attributes(
                    span,
                    {
                        **base_trace_attributes(role, session_id),
                        "tools.available_count": len(all_tools),
                        "tools.allowed_count": len(role_tools),
                        "operation.status": "ok",
                    },
                )
            logger.info(
                "Tools available for role=%s: %s/%s",
                role,
                len(role_tools),
                len(all_tools),
            )

            # Apply AgentCore configuration-bundle overrides when Gateway A/B
            # routing injects a bundle reference through request baggage.
            system_prompt = resolve_system_prompt(role, config_bundle)
            apply_tool_description_overrides(role_tools, config_bundle)

            # Create agent
            model = BedrockModel(
                model_id=MODEL_ID,
                region_name=AGENT_REGION,
                temperature=0.3,
                max_tokens=1500,
            )

            agent = Agent(model=model, tools=role_tools, system_prompt=system_prompt)

            # Invoke agent
            with tracer.start_as_current_span("product_catalog.agent_invocation") as span:
                set_safe_span_attributes(
                    span,
                    {**base_trace_attributes(role, session_id), "operation.status": "running"},
                )
                response = agent(prompt)
                response_text = response.message["content"][0]["text"]

            # Collect tool usage metadata from full conversation history
            # Strands uses 'toolUse' key (camelCase) in ContentBlock TypedDict
            tools_used = []
            for msg in agent.messages:
                if msg.get("role") == "assistant":
                    for content_block in msg.get("content", []):
                        if "toolUse" in content_block:
                            tool_name = content_block["toolUse"].get("name", "")
                            tools_used.append(strip_prefix(tool_name))

            set_safe_span_attributes(
                root_span,
                {
                    "tools.allowed_count": len(role_tools),
                    "tools.used_count": len(tools_used),
                    "operation.status": "success",
                },
            )

            return {
                "status": "success",
                "response": response_text,
                "metadata": {
                    "role": role,
                    "tools_available": len(role_tools),
                    "tools_used": tools_used,
                    "session_id": session_id,
                    "model": MODEL_ID,
                    "deployment_id": DEPLOYMENT_ID,
                    "agent_version": AGENT_VERSION,
                },
            }

        except Exception as e:
            logger.error("Agent error type=%s", type(e).__name__)
            set_safe_span_attributes(
                root_span,
                {"operation.status": "error", "error.type": type(e).__name__},
            )
            return {"status": "error", "error": safe_error(e)}
        finally:
            try:
                mcp_client.__exit__(None, None, None)
            except Exception:
                pass


if __name__ == "__main__":
    app.run()
