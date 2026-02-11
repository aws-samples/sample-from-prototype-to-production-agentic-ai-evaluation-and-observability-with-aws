"""
RBAC Gateway Interceptor Lambda

This Lambda function runs as an AgentCore Gateway interceptor to enforce
role-based access control on MCP tool calls.

It operates at two interception points:
  - RESPONSE: Filters tools/list responses to hide admin tools from customers
  - REQUEST:  Blocks tools/call for admin tools when the caller is a customer

The user's role is extracted from the JWT token's 'cognito:groups' claim
passed in the Authorization header by the agent.

Admin-only tools: create_product, update_product, delete_product,
                  update_inventory, update_pricing
"""

import json
import base64
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tools restricted to admin role
ADMIN_ONLY_TOOLS = {
    'create_product',
    'update_product',
    'delete_product',
    'update_inventory',
    'update_pricing',
}


def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verification (Gateway already validated the token)."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        # Add padding
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        payload = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload)
    except Exception as e:
        logger.error(f"Error decoding JWT: {e}")
        return {}


def get_user_role(headers: dict) -> str:
    """
    Extract user role from JWT Authorization header.
    Returns 'admin' if user is in the admin group, otherwise 'customer'.
    """
    auth_header = headers.get('Authorization') or headers.get('authorization', '')
    if not auth_header:
        return 'customer'  # Default to least privilege

    token = auth_header.replace('Bearer ', '').replace('bearer ', '')
    claims = decode_jwt_payload(token)

    # Check cognito:groups claim
    groups = claims.get('cognito:groups', [])
    if isinstance(groups, str):
        groups = [groups]

    if 'admin' in groups:
        return 'admin'
    return 'customer'


def strip_target_prefix(tool_name: str) -> str:
    """Remove the Gateway target prefix from a tool name (e.g., ProductTools___search_products -> search_products)."""
    delimiter = '___'
    if delimiter in tool_name:
        return tool_name[tool_name.index(delimiter) + len(delimiter):]
    return tool_name


def is_admin_tool(tool_name: str) -> bool:
    """Check if a tool name (with or without prefix) is admin-only."""
    base_name = strip_target_prefix(tool_name)
    return base_name in ADMIN_ONLY_TOOLS


def lambda_handler(event, context):
    """
    Gateway interceptor handler.

    Handles two interception points:
    - RESPONSE on tools/list: filters out admin tools for customer role
    - REQUEST on tools/call: blocks admin tool calls for customer role
    """
    try:
        mcp_data = event.get('mcp', {})

        # -------------------------------------------------------------------
        # RESPONSE interception: filter tools/list
        # -------------------------------------------------------------------
        if 'gatewayResponse' in mcp_data and mcp_data['gatewayResponse'] is not None:
            gateway_response = mcp_data['gatewayResponse']
            gateway_request = mcp_data.get('gatewayRequest', {})

            headers = gateway_request.get('headers', {})
            role = get_user_role(headers)

            response_body = gateway_response.get('body', {})

            # Check if this is a tools/list response
            result = response_body.get('result', {})
            if 'tools' in result:
                original_tools = result['tools']

                if role == 'admin':
                    # Admin sees all tools
                    filtered_tools = original_tools
                    logger.info(f"Admin user - showing all {len(filtered_tools)} tools")
                else:
                    # Customer: filter out admin-only tools
                    filtered_tools = [
                        t for t in original_tools
                        if not is_admin_tool(t.get('name', ''))
                    ]
                    removed = len(original_tools) - len(filtered_tools)
                    logger.info(f"Customer user - filtered {removed} admin tools, showing {len(filtered_tools)} tools")

                return {
                    'interceptorOutputVersion': '1.0',
                    'mcp': {
                        'transformedGatewayResponse': {
                            'statusCode': gateway_response.get('statusCode', 200),
                            'body': {
                                'jsonrpc': '2.0',
                                'result': {'tools': filtered_tools},
                                'id': response_body.get('id')
                            }
                        }
                    }
                }

            # Not a tools/list response - pass through
            return {
                'interceptorOutputVersion': '1.0',
                'mcp': {
                    'transformedGatewayResponse': {
                        'statusCode': gateway_response.get('statusCode', 200),
                        'body': response_body
                    }
                }
            }

        # -------------------------------------------------------------------
        # REQUEST interception: block unauthorized tool calls
        # -------------------------------------------------------------------
        if 'gatewayRequest' in mcp_data:
            gateway_request = mcp_data['gatewayRequest']
            headers = gateway_request.get('headers', {})
            body = gateway_request.get('body', {})

            role = get_user_role(headers)

            # Check if this is a tools/call
            method = body.get('method', '')
            if method == 'tools/call':
                tool_name = body.get('params', {}).get('name', '')

                if is_admin_tool(tool_name) and role != 'admin':
                    base_name = strip_target_prefix(tool_name)
                    logger.warning(
                        f"RBAC DENIED: customer attempted admin tool '{base_name}'"
                    )
                    return {
                        'interceptorOutputVersion': '1.0',
                        'mcp': {
                            'transformedGatewayResponse': {
                                'statusCode': 403,
                                'body': {
                                    'jsonrpc': '2.0',
                                    'id': body.get('id'),
                                    'error': {
                                        'code': -32600,
                                        'message': f'Access denied: tool "{base_name}" requires admin privileges.'
                                    }
                                }
                            }
                        }
                    }

                logger.info(f"RBAC ALLOWED: {role} calling tool '{tool_name}'")

            # Pass through authorized requests
            return {
                'interceptorOutputVersion': '1.0',
                'mcp': {
                    'transformedGatewayRequest': {
                        'headers': headers,
                        'body': body
                    }
                }
            }

        # Unknown event structure - pass through
        logger.warning(f"Unknown interceptor event structure: {list(mcp_data.keys())}")
        return {
            'interceptorOutputVersion': '1.0',
            'mcp': {}
        }

    except Exception as e:
        logger.error(f"Interceptor error: {e}")
        # On error, fail open for reads but block writes (safe default)
        return {
            'interceptorOutputVersion': '1.0',
            'mcp': {
                'transformedGatewayResponse': {
                    'statusCode': 500,
                    'body': {
                        'jsonrpc': '2.0',
                        'error': {
                            'code': -32603,
                            'message': f'RBAC interceptor error: {str(e)}'
                        }
                    }
                }
            }
        }
