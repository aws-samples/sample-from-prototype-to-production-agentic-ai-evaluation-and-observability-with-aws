"""
Product Catalog Agent - Streamlit Chat Application

Chat interface for the single Product Catalog Agent deployed to AgentCore Runtime.
Supports user login (customer/admin) and demonstrates RBAC in production.
"""

import streamlit as st
import json
import os
import uuid
from datetime import datetime
import boto3


# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
    """Load deployment configuration from agent_config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "agent_config.json")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return None


def get_user_token(cognito_client, user_pool_id, client_id, email, password):
    """Authenticate user and get JWT tokens."""
    try:
        response = cognito_client.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow='ADMIN_USER_PASSWORD_AUTH',
            AuthParameters={'USERNAME': email, 'PASSWORD': password}
        )
        tokens = response.get('AuthenticationResult', {})
        return {
            'id_token': tokens.get('IdToken', ''),
            'access_token': tokens.get('AccessToken', ''),
        }
    except Exception as e:
        st.error(f"Login failed: {e}")
        return None


# ============================================================================
# AGENT INVOCATION
# ============================================================================

def invoke_agent(config, prompt, bearer_token, session_id):
    """Invoke the Product Catalog Agent via AgentCore Runtime."""
    try:
        region = config.get('region', 'us-west-2')
        runtime_arn = config['runtime_arn']

        client = boto3.client('bedrock-agentcore', region_name=region)

        payload = {
            'prompt': prompt,
            'bearer_token': bearer_token,
            'session_id': session_id
        }

        response = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            sessionId=session_id,
            payload=json.dumps(payload).encode('utf-8')
        )

        result = b''
        for event in response.get('body', []):
            if 'chunk' in event:
                result += event['chunk']['bytes']

        return json.loads(result.decode('utf-8'))
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


# ============================================================================
# STREAMLIT UI
# ============================================================================

st.set_page_config(
    page_title="Product Catalog Agent",
    page_icon="🛍",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
.role-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 0.85em;
    font-weight: bold;
}
.role-customer { background-color: #d4edda; color: #155724; }
.role-admin { background-color: #fff3cd; color: #856404; }
.tools-info { background-color: #f8f9fa; padding: 10px; border-radius: 5px; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

st.title("Product Catalog Agent")

# Load config
config = load_config()
if not config:
    st.error("Configuration not found. Run the deployment notebook first (03-production-deployment.ipynb).")
    st.stop()

# Session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'bearer_token' not in st.session_state:
    st.session_state.bearer_token = ''

# Sidebar - Login
with st.sidebar:
    st.header("User Login")

    if not st.session_state.logged_in:
        st.write("Login to test different roles (RBAC)")

        # Pre-configured test users
        user_options = {
            "Customer (John Smith)": {
                "email": config.get('customer_email', 'john.customer@example.com'),
                "password": config.get('test_password', 'Workshop1234'),
                "role": "customer"
            },
            "Admin (Alice Admin)": {
                "email": config.get('admin_email', 'alice.admin@example.com'),
                "password": config.get('test_password', 'Workshop1234'),
                "role": "admin"
            }
        }

        selected_user = st.selectbox("Select test user:", list(user_options.keys()))

        if st.button("Login", type="primary"):
            user = user_options[selected_user]
            region = config.get('region', 'us-west-2')
            cognito = boto3.client('cognito-idp', region_name=region)

            tokens = get_user_token(
                cognito,
                config['user_pool_id'],
                config['user_client_id'],
                user['email'],
                user['password']
            )

            if tokens:
                st.session_state.logged_in = True
                st.session_state.user_role = user['role']
                st.session_state.bearer_token = tokens['id_token']
                st.session_state.messages = []
                st.rerun()
    else:
        role = st.session_state.user_role
        badge_class = f"role-{role}"
        st.markdown(
            f'<span class="role-badge {badge_class}">{role.upper()}</span>',
            unsafe_allow_html=True
        )

        if role == 'customer':
            st.info("Tools: search, details, inventory, compare, recommendations, return policy")
        else:
            st.success("Tools: ALL 11 tools (6 read + 5 admin)")

        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user_role = None
            st.session_state.bearer_token = ''
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.subheader("Example Queries")
        if role == 'customer':
            examples = [
                "Search for wireless headphones under $100",
                "Compare PROD-001 and PROD-055",
                "Is PROD-088 in stock?",
                "What's the return policy?"
            ]
        else:
            examples = [
                "Create product PROD-200 'Gaming Headset' in Audio for $129.99",
                "Set PROD-088 inventory to 100 units",
                "Put PROD-001 on sale for $59.99 until 2025-06-30",
                "Discontinue product PROD-200"
            ]
        for ex in examples:
            if st.button(ex, key=f"ex_{ex[:20]}"):
                st.session_state.pending_query = ex

# Main chat area
if not st.session_state.logged_in:
    st.info("Please login from the sidebar to start chatting with the Product Catalog Agent.")
    st.stop()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg['role']):
        st.markdown(msg['content'])
        if 'metadata' in msg:
            meta = msg['metadata']
            with st.expander("Response metadata"):
                st.json(meta)

# Handle pending query from sidebar
if 'pending_query' in st.session_state:
    prompt = st.session_state.pop('pending_query')
else:
    prompt = st.chat_input("Ask about products...")

if prompt:
    st.session_state.messages.append({'role': 'user', 'content': prompt})
    with st.chat_message('user'):
        st.markdown(prompt)

    with st.chat_message('assistant'):
        with st.spinner("Thinking..."):
            result = invoke_agent(
                config, prompt,
                st.session_state.bearer_token,
                st.session_state.session_id
            )

        if result.get('status') == 'success':
            response_text = result.get('response', 'No response')
            st.markdown(response_text)

            metadata = result.get('metadata', {})
            st.session_state.messages.append({
                'role': 'assistant',
                'content': response_text,
                'metadata': metadata
            })
        else:
            error = result.get('error', 'Unknown error')
            st.error(f"Error: {error}")
            st.session_state.messages.append({
                'role': 'assistant',
                'content': f"Error: {error}"
            })
