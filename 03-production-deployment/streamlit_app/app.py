"""
E-Commerce Customer Service AI Agent - Streamlit Chat Application

A chat interface for the multi-agent customer service system with streaming support.
Connects to the Orchestrator Agent via A2A for coordinated multi-agent responses.
Falls back to direct Gateway/MCP connection if Orchestrator is not deployed.
"""

import streamlit as st
import json
import os
import uuid
from typing import Generator
from datetime import datetime

import boto3


# ============================================================================
# CONFIGURATION
# ============================================================================

def load_orchestrator_config():
    """
    Load Orchestrator configuration from orchestrator_config.json

    Returns:
        dict: Orchestrator configuration or None if not found
    """
    config_path = os.path.join(os.path.dirname(__file__), "orchestrator_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)
    return None


def load_gateway_config():
    """
    Load Gateway configuration from gateway_config.json (fallback)

    Returns:
        dict: Gateway configuration
    """
    config_path = os.path.join(os.path.dirname(__file__), "gateway_config.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), "..", "gateway_config.json")

    with open(config_path, "r") as f:
        return json.load(f)


def get_access_token(config):
    """
    Get OAuth access token from Cognito using client_credentials flow (M2M)

    Args:
        config: Configuration dict with auth info

    Returns:
        str: Access token
    """
    import requests
    import base64

    # Handle different config structures
    if 'auth' in config:
        auth_info = config['auth']
        user_pool_id = auth_info['user_pool_id']
        client_id = auth_info['client_id']
    elif 'client_info' in config:
        auth_info = config['client_info']
        user_pool_id = auth_info['user_pool_id']
        client_id = auth_info['client_id']
    else:
        raise Exception("No auth configuration found")

    region = config['region']

    cognito = boto3.client('cognito-idp', region_name=region)

    try:
        # Get client secret from Cognito
        client_details = cognito.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id
        )
        client_secret = client_details['UserPoolClient'].get('ClientSecret')

        # Get the Cognito domain
        pool_info = cognito.describe_user_pool(UserPoolId=user_pool_id)
        domain = pool_info['UserPool'].get('Domain')

        if not domain:
            raise Exception("No Cognito domain configured")

        # Use client_credentials OAuth flow
        token_url = f"https://{domain}.auth.{region}.amazoncognito.com/oauth2/token"

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {credentials}'
        }

        # Resource server scopes
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
            raise Exception(f"Token response error: {token_response}")

    except Exception as e:
        raise Exception(f"Failed to get access token: {str(e)}")


# ============================================================================
# A2A CLIENT (FOR ORCHESTRATOR)
# ============================================================================

def invoke_orchestrator_a2a(orchestrator_arn: str, region: str, message: str, session_id: str = None) -> dict:
    """
    Invoke Orchestrator Agent via A2A protocol

    Args:
        orchestrator_arn: ARN of the Orchestrator Runtime
        region: AWS region
        message: User message
        session_id: Session ID for conversation continuity

    Returns:
        dict: Response with message and metadata
    """
    client = boto3.client('bedrock-agentcore', region_name=region)

    if not session_id:
        # Generate a unique session ID (must be at least 33 characters)
        import time
        session_id = f"session-{int(time.time())}-{uuid.uuid4().hex[:20]}"

    # Payload format for AgentCore Runtime
    payload = {
        "input": {
            "prompt": message
        }
    }

    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=orchestrator_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(payload).encode('utf-8'),
            qualifier="DEFAULT"
        )

        # Read response blob
        response_body = response.get('response', b'')
        if hasattr(response_body, 'read'):
            response_body = response_body.read()

        response_data = json.loads(response_body)

        # Build detailed response
        result = {
            'message': '',
            'agent': None,
            'tools_used': 0,
            'timestamp': None,
            'session_id': session_id,
            'raw_response': response_data
        }

        # Extract details from response
        if 'output' in response_data:
            output = response_data['output']
            if isinstance(output, dict):
                # Extract message
                result['message'] = output.get('message', str(output))

                # Extract agent info - orchestrator returns which agents it routed to
                if output.get('agent') == 'orchestrator' and 'routed_to' in output:
                    # Orchestrator with routing info
                    routed_agents = output.get('routed_to', [])
                    if routed_agents:
                        result['agent'] = f"orchestrator → {', '.join(routed_agents)}"
                    else:
                        result['agent'] = 'orchestrator'

                    # Get total tools used across all agents
                    result['tools_used'] = output.get('tools_used', 0)

                    # Store routing details for debug view
                    result['routing_details'] = output.get('routing_details', [])
                else:
                    # Direct agent response
                    result['agent'] = output.get('agent', 'unknown')
                    result['tools_used'] = output.get('tools_used', 0)

                result['timestamp'] = output.get('timestamp')
            else:
                # Output is a string
                result['message'] = str(output)
                result['agent'] = 'orchestrator'
        elif 'error' in response_data:
            result['message'] = f"Error: {response_data['error']}"
            result['error'] = True
        else:
            # Fallback - try to extract any meaningful content
            result['message'] = str(response_data)

        return result

    except Exception as e:
        return {
            'message': f"Error communicating with Orchestrator: {str(e)}",
            'error': True,
            'session_id': session_id
        }


# ============================================================================
# MCP CLIENT (FALLBACK FOR DIRECT GATEWAY)
# ============================================================================

def create_mcp_client(gateway_url, access_token=None):
    """
    Create MCP client with authentication (for fallback mode)
    """
    from strands.tools.mcp.mcp_client import MCPClient
    from mcp.client.streamable_http import streamablehttp_client

    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    return MCPClient(
        lambda: streamablehttp_client(
            gateway_url,
            headers=headers
        )
    )


def create_supervisor_agent(model_id, tools, region="us-west-2"):
    """
    Create Strands supervisor agent (for fallback mode)
    """
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(
        model_id=model_id,
        region_name=region,
        streaming=True,
        temperature=0.2
    )

    system_prompt = """You are the Customer Service Orchestrator for an e-commerce company.
Use the available tools to help customers with orders, products, and account inquiries.
Be helpful, professional, and provide accurate information."""

    return Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt
    )


# ============================================================================
# STREAMLIT APP
# ============================================================================

st.set_page_config(
    page_title="E-Commerce Customer Service",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FF9900;
        text-align: center;
        padding: 1rem 0;
    }
    .status-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .status-success {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .status-error {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .status-info {
        background-color: #cce5ff;
        border: 1px solid #99caff;
        color: #004085;
    }
    .agent-badge {
        background-color: #FF9900;
        color: white;
        padding: 0.3rem 0.6rem;
        border-radius: 0.3rem;
        font-size: 0.9rem;
        margin: 0.2rem;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)


def initialize_agent():
    """Initialize the agent connection and store in session state"""
    if 'agent_initialized' not in st.session_state:
        with st.spinner("🔧 Initializing Customer Service Agent..."):
            try:
                # Try to load Orchestrator config first (preferred)
                orchestrator_config = load_orchestrator_config()

                if orchestrator_config and 'orchestrator_arn' in orchestrator_config:
                    # Use Orchestrator Agent via A2A
                    st.session_state.mode = 'orchestrator'
                    st.session_state.config = orchestrator_config
                    st.session_state.orchestrator_arn = orchestrator_config['orchestrator_arn']
                    st.session_state.region = orchestrator_config['region']
                    st.session_state.session_id = str(uuid.uuid4())
                    st.session_state.agent_initialized = True
                    st.session_state.initialization_error = None
                else:
                    # Fallback: Direct Gateway/MCP mode
                    gateway_config = load_gateway_config()
                    st.session_state.mode = 'gateway'
                    st.session_state.config = gateway_config

                    # Get OAuth token
                    access_token = get_access_token(gateway_config)
                    st.session_state.access_token = access_token

                    # Create MCP client
                    mcp_client = create_mcp_client(gateway_config['gateway_url'], access_token)
                    st.session_state.mcp_client = mcp_client

                    # Initialize MCP client context
                    st.session_state.mcp_client.__enter__()

                    # Get tools
                    tools = mcp_client.list_tools_sync()
                    st.session_state.tools = tools

                    # Create agent
                    model_id = gateway_config.get('model_id', 'global.anthropic.claude-3-5-sonnet-20241022-v2:0')
                    agent = create_supervisor_agent(model_id, tools, gateway_config['region'])
                    st.session_state.agent = agent
                    st.session_state.region = gateway_config['region']

                    st.session_state.agent_initialized = True
                    st.session_state.initialization_error = None

            except FileNotFoundError as e:
                st.session_state.agent_initialized = False
                st.session_state.initialization_error = "Configuration file not found. Please run the deployment notebook first."
            except Exception as e:
                st.session_state.agent_initialized = False
                import traceback
                st.session_state.initialization_error = f"{str(e)}\n\nDetails:\n{traceback.format_exc()}"


def get_agent_response(prompt: str) -> dict:
    """
    Get response from agent based on current mode

    Args:
        prompt: User message

    Returns:
        dict: Agent response with metadata
    """
    if st.session_state.mode == 'orchestrator':
        # Use A2A to invoke Orchestrator
        return invoke_orchestrator_a2a(
            st.session_state.orchestrator_arn,
            st.session_state.region,
            prompt,
            st.session_state.session_id
        )
    else:
        # Use direct MCP/Gateway mode with local agent
        agent = st.session_state.agent
        response = agent(prompt)
        # Return as dict for consistency
        return {
            'message': str(response),
            'agent': 'gateway-direct',
            'tools_used': len(st.session_state.tools) if 'tools' in st.session_state else 0,
            'timestamp': datetime.utcnow().isoformat(),
            'session_id': st.session_state.get('session_id', 'direct-mode')
        }


def main():
    """Main application function"""

    # Header
    st.markdown('<div class="main-header">🛒 E-Commerce Customer Service</div>', unsafe_allow_html=True)
    st.markdown("---")

    # Initialize agent
    initialize_agent()

    # Sidebar
    with st.sidebar:
        st.header("ℹ️ About")
        st.markdown("""
        **AI-Powered Customer Service** helps you with:

        - 📦 **Orders** - Status, tracking, returns
        - 🛍️ **Products** - Search, recommendations
        - 👤 **Account** - Info, membership, settings

        Powered by Amazon Bedrock AgentCore
        """)

        st.markdown("---")

        # Status information
        if st.session_state.get('agent_initialized'):
            mode = st.session_state.get('mode', 'unknown')

            if mode == 'orchestrator':
                st.markdown('<div class="status-box status-success">✅ Orchestrator Agent Ready</div>', unsafe_allow_html=True)
                st.markdown("**Mode:** Multi-Agent (A2A)")

                st.markdown("**Specialized Agents:**")
                st.markdown('<span class="agent-badge">📦 Order Agent</span>', unsafe_allow_html=True)
                st.markdown('<span class="agent-badge">🛍️ Product Agent</span>', unsafe_allow_html=True)
                st.markdown('<span class="agent-badge">👤 Account Agent</span>', unsafe_allow_html=True)

                config = st.session_state.config
                if 'specialized_agents' in config:
                    with st.expander("Agent Details"):
                        for name, info in config['specialized_agents'].items():
                            st.text(f"{name}: Active")
            else:
                st.markdown('<div class="status-box status-info">✅ Gateway Mode</div>', unsafe_allow_html=True)
                st.markdown("**Mode:** Direct MCP")

                if 'tools' in st.session_state:
                    st.markdown(f"**Tools Available:** {len(st.session_state.tools)}")

                    with st.expander("Available Tools"):
                        for tool in st.session_state.tools:
                            st.text(f"• {tool.tool_name}")

            st.text(f"Region: {st.session_state.get('region', 'unknown')}")
        else:
            error = st.session_state.get('initialization_error', 'Unknown error')
            st.markdown(f'<div class="status-box status-error">❌ Initialization Failed</div>', unsafe_allow_html=True)
            with st.expander("Error Details"):
                st.text(error)

        st.markdown("---")

        # Example queries
        st.markdown("**Try asking:**")
        example_queries = [
            "What's the status of order ORD-2024-10002?",
            "Do you have wireless headphones under $100?",
            "What are Gold membership benefits?",
            "I want to return my order ORD-2024-10001"
        ]
        for query in example_queries:
            st.code(query, language=None)

        st.markdown("---")

        # Debug mode toggle
        st.markdown("**Developer Tools**")
        st.session_state.show_debug = st.checkbox(
            "Show Debug Info 🛠️",
            value=st.session_state.get('show_debug', False),
            help="Display detailed agent responses and tool usage"
        )

        # Clear chat button
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            if st.session_state.get('mode') == 'orchestrator':
                st.session_state.session_id = str(uuid.uuid4())
            st.rerun()

    # Initialize chat history
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            # For assistant messages with metadata, show agent info
            if message["role"] == "assistant" and message.get("metadata"):
                metadata = message["metadata"]
                agent_name = metadata.get('agent', 'unknown')
                tools_used = metadata.get('tools_used', 0)
                timestamp = metadata.get('timestamp', '')

                if agent_name and agent_name != 'unknown':
                    col1, col2, col3 = st.columns([2, 2, 3])
                    with col1:
                        st.markdown(f'<span class="agent-badge">🤖 {agent_name}</span>', unsafe_allow_html=True)
                    with col2:
                        if tools_used > 0:
                            st.markdown(f'<span class="agent-badge">🔧 {tools_used} tools</span>', unsafe_allow_html=True)
                    with col3:
                        if timestamp:
                            st.caption(f"📅 {timestamp[:19]}")

                # Show raw response in expander if debug mode
                if st.session_state.get('show_debug', False):
                    with st.expander("📊 Response Details"):
                        st.json(metadata)

            st.markdown(message["content"])

    # Chat input
    if st.session_state.get('agent_initialized'):
        if prompt := st.chat_input("How can I help you today?"):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)

            # Display assistant response
            with st.chat_message("assistant"):
                with st.spinner("🤔 Thinking..."):
                    response_data = get_agent_response(prompt)

                # Extract message and metadata
                if isinstance(response_data, dict):
                    message = response_data.get('message', str(response_data))
                    agent_name = response_data.get('agent', 'unknown')
                    tools_used = response_data.get('tools_used', 0)
                    timestamp = response_data.get('timestamp', '')

                    # Display agent metadata if available
                    if agent_name and agent_name != 'unknown':
                        col1, col2, col3 = st.columns([2, 2, 3])
                        with col1:
                            st.markdown(f'<span class="agent-badge">🤖 {agent_name}</span>', unsafe_allow_html=True)
                        with col2:
                            if tools_used > 0:
                                st.markdown(f'<span class="agent-badge">🔧 {tools_used} tools</span>', unsafe_allow_html=True)
                        with col3:
                            if timestamp:
                                st.caption(f"📅 {timestamp[:19]}")

                    # Display the message
                    st.markdown(message)

                    # Show raw response in expander for debugging
                    if st.session_state.get('show_debug', False):
                        with st.expander("📊 Response Details"):
                            st.json(response_data)
                else:
                    # Fallback for string responses
                    message = str(response_data)
                    st.markdown(message)

            # Add assistant response to chat history (store full data)
            st.session_state.messages.append({
                "role": "assistant",
                "content": message if isinstance(response_data, dict) else response_data,
                "metadata": response_data if isinstance(response_data, dict) else None
            })
    else:
        st.error("⚠️ Agent not initialized. Please check the sidebar for details.")
        st.info("Make sure you have run the deployment notebook to set up the infrastructure.")


if __name__ == "__main__":
    main()
