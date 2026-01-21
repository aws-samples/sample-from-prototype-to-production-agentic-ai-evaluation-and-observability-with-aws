"""
Utility Functions for AgentCore Gateway Deployment

Helper functions for creating Lambda functions, Cognito resources,
and AgentCore Gateway configuration.
"""

import boto3
import json
import zipfile
import os
import time
from datetime import datetime


def create_lambda_execution_role(iam_client, role_name: str, dynamodb_table_arns: list) -> dict:
    """
    Create IAM role for Lambda functions with DynamoDB access.

    Args:
        iam_client: boto3 IAM client
        role_name: Name for the IAM role
        dynamodb_table_arns: List of DynamoDB table ARNs to grant access

    Returns:
        dict: Role creation response with ARN
    """
    # Trust policy for Lambda
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        # Create role
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Lambda execution role for e-commerce MCP tools"
        )
        role_arn = role_response['Role']['Arn']
        print(f"Created IAM role: {role_name}")

        # Attach basic Lambda execution policy
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        )

        # Create and attach DynamoDB policy
        dynamodb_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Query",
                        "dynamodb:Scan"
                    ],
                    "Resource": dynamodb_table_arns
                }
            ]
        }

        policy_name = f"{role_name}-dynamodb-policy"
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(dynamodb_policy)
        )
        print(f"Attached DynamoDB policy to role")

        # Wait for role to be available
        time.sleep(10)

        return {'Role': role_response['Role'], 'exit_code': 0}

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} already exists, retrieving ARN...")
        role = iam_client.get_role(RoleName=role_name)
        return {'Role': role['Role'], 'exit_code': 0}
    except Exception as e:
        print(f"Error creating role: {e}")
        return {'Role': None, 'exit_code': 1, 'error': str(e)}


def create_lambda_function(
    lambda_client,
    function_name: str,
    role_arn: str,
    code_path: str,
    handler: str,
    environment_vars: dict,
    region: str
) -> dict:
    """
    Create or update a Lambda function.

    Args:
        lambda_client: boto3 Lambda client
        function_name: Name for the Lambda function
        role_arn: IAM role ARN for execution
        code_path: Path to the Python file
        handler: Handler name (e.g., 'lambda_function.lambda_handler')
        environment_vars: Environment variables dict
        region: AWS region

    Returns:
        dict: Lambda function details with ARN
    """
    # Create zip file with Lambda code
    zip_path = f"/tmp/{function_name}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Get the base filename for the zip entry
        base_name = os.path.basename(code_path)
        zipf.write(code_path, base_name)

    with open(zip_path, 'rb') as f:
        zip_content = f.read()

    try:
        # Try to create new function
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.11',
            Role=role_arn,
            Handler=handler,
            Code={'ZipFile': zip_content},
            Description='E-Commerce MCP Tool Lambda',
            Timeout=30,
            MemorySize=256,
            Environment={'Variables': environment_vars}
        )
        print(f"Created Lambda function: {function_name}")

        # Wait for function to be active
        waiter = lambda_client.get_waiter('function_active')
        waiter.wait(FunctionName=function_name)

        return {
            'function_arn': response['FunctionArn'],
            'function_name': function_name,
            'exit_code': 0
        }

    except lambda_client.exceptions.ResourceConflictException:
        # Function exists, update it
        print(f"Function {function_name} exists, updating...")
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_content
        )

        # Wait for the code update to complete before updating configuration
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)

        # Also update environment variables
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': environment_vars}
        )

        return {
            'function_arn': response['FunctionArn'],
            'function_name': function_name,
            'exit_code': 0
        }
    except Exception as e:
        print(f"Error creating/updating Lambda: {e}")
        return {'function_arn': None, 'exit_code': 1, 'error': str(e)}


def create_agentcore_gateway_role(iam_client, role_name: str, lambda_arns: list) -> dict:
    """
    Create IAM role for AgentCore Gateway with Lambda invoke permissions.

    Args:
        iam_client: boto3 IAM client
        role_name: Name for the role
        lambda_arns: List of Lambda function ARNs to invoke

    Returns:
        dict: Role details with ARN
    """
    # Trust policy for AgentCore Gateway
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="AgentCore Gateway role for e-commerce workshop"
        )
        role_arn = role_response['Role']['Arn']
        print(f"Created Gateway IAM role: {role_name}")

        # Create Lambda invoke policy
        lambda_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "lambda:InvokeFunction",
                    "Resource": lambda_arns
                }
            ]
        }

        policy_name = f"{role_name}-lambda-invoke-policy"
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(lambda_policy)
        )
        print(f"Attached Lambda invoke policy to Gateway role")

        time.sleep(10)

        return {'Role': role_response['Role']}

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} already exists, retrieving...")
        role = iam_client.get_role(RoleName=role_name)
        return {'Role': role['Role']}


def get_or_create_cognito_user_pool(cognito_client, pool_name: str) -> str:
    """Get existing or create new Cognito User Pool."""
    # Check if pool exists
    response = cognito_client.list_user_pools(MaxResults=60)
    for pool in response['UserPools']:
        if pool['Name'] == pool_name:
            print(f"Found existing user pool: {pool['Id']}")
            return pool['Id']

    # Create new pool
    response = cognito_client.create_user_pool(
        PoolName=pool_name,
        Policies={
            'PasswordPolicy': {
                'MinimumLength': 8,
                'RequireUppercase': True,
                'RequireLowercase': True,
                'RequireNumbers': True,
                'RequireSymbols': False
            }
        },
        AutoVerifiedAttributes=['email'],
        UsernameAttributes=['email'],
        Schema=[
            {'Name': 'email', 'AttributeDataType': 'String', 'Required': True}
        ]
    )
    print(f"Created user pool: {response['UserPool']['Id']}")
    return response['UserPool']['Id']


def get_or_create_cognito_resource_server(
    cognito_client,
    user_pool_id: str,
    identifier: str,
    name: str,
    scopes: list
) -> None:
    """Create Cognito resource server with custom scopes."""
    try:
        cognito_client.create_resource_server(
            UserPoolId=user_pool_id,
            Identifier=identifier,
            Name=name,
            Scopes=scopes
        )
        print(f"Created resource server: {identifier}")
    except cognito_client.exceptions.InvalidParameterException:
        print(f"Resource server {identifier} already exists")


def get_or_create_cognito_app_client(
    cognito_client,
    user_pool_id: str,
    client_name: str,
    resource_server_id: str
) -> tuple:
    """Create Cognito app client for M2M authentication."""
    # Check if client exists
    response = cognito_client.list_user_pool_clients(
        UserPoolId=user_pool_id,
        MaxResults=60
    )
    for client in response['UserPoolClients']:
        if client['ClientName'] == client_name:
            # Get client details including secret
            client_details = cognito_client.describe_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client['ClientId']
            )
            print(f"Found existing app client: {client['ClientId']}")
            return client['ClientId'], client_details['UserPoolClient'].get('ClientSecret')

    # Create new client
    response = cognito_client.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=client_name,
        GenerateSecret=True,
        AllowedOAuthFlows=['client_credentials'],
        AllowedOAuthScopes=[
            f"{resource_server_id}/gateway:read",
            f"{resource_server_id}/gateway:write"
        ],
        AllowedOAuthFlowsUserPoolClient=True,
        SupportedIdentityProviders=['COGNITO']
    )
    print(f"Created app client: {response['UserPoolClient']['ClientId']}")
    return response['UserPoolClient']['ClientId'], response['UserPoolClient']['ClientSecret']


def get_or_create_cognito_domain(cognito_client, user_pool_id: str, domain_prefix: str) -> str:
    """Create Cognito domain for OAuth endpoints."""
    try:
        cognito_client.create_user_pool_domain(
            Domain=domain_prefix,
            UserPoolId=user_pool_id
        )
        print(f"Created Cognito domain: {domain_prefix}")
    except cognito_client.exceptions.InvalidParameterException:
        print(f"Domain {domain_prefix} already exists or invalid")

    return domain_prefix


def create_test_user(cognito_client, user_pool_id: str, client_id: str, email: str, password: str) -> None:
    """Create a test user in Cognito User Pool."""
    try:
        # Create user
        cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ],
            MessageAction='SUPPRESS'  # Don't send welcome email
        )

        # Set password
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True
        )
        print(f"Created test user: {email}")

    except cognito_client.exceptions.UsernameExistsException:
        print(f"User {email} already exists")


def get_oauth_token(user_pool_id: str, client_id: str, client_secret: str, scopes: str, region: str) -> dict:
    """Get OAuth access token from Cognito using client credentials grant."""
    import requests
    import base64

    # Get token endpoint
    token_endpoint = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"

    # For M2M, use the domain endpoint
    cognito = boto3.client('cognito-idp', region_name=region)

    try:
        # Get domain info
        pool_info = cognito.describe_user_pool(UserPoolId=user_pool_id)
        domain = pool_info['UserPool'].get('Domain')

        if domain:
            token_url = f"https://{domain}.auth.{region}.amazoncognito.com/oauth2/token"

            # Prepare credentials
            credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {credentials}'
            }

            data = {
                'grant_type': 'client_credentials',
                'scope': scopes
            }

            response = requests.post(token_url, headers=headers, data=data)
            return response.json()
    except Exception as e:
        print(f"Error getting token: {e}")

    return {}


def create_gateway(gateway_client, name: str, role_arn: str, auth_config: dict, description: str) -> dict:
    """
    Create or get existing AgentCore Gateway with specified authentication.

    Args:
        gateway_client: boto3 bedrock-agentcore-control client
        name: Gateway name
        role_arn: IAM role ARN for the gateway
        auth_config: Authentication configuration dict
        description: Gateway description

    Returns:
        dict: Gateway response with ID and URL
    """
    try:
        response = gateway_client.create_gateway(
            name=name,
            roleArn=role_arn,
            protocolType='MCP',
            authorizerType='CUSTOM_JWT',
            authorizerConfiguration=auth_config,
            description=description
        )
        print(f"Created Gateway: {response['gatewayId']}")
        print(f"Gateway URL: {response['gatewayUrl']}")
        return response
    except gateway_client.exceptions.ConflictException:
        # Gateway already exists, find and return it
        print(f"Gateway '{name}' already exists, retrieving...")
        try:
            # List gateways to find the existing one (response uses 'items' key)
            response = gateway_client.list_gateways()
            for gateway in response.get('items', []):
                if gateway.get('name') == name:
                    gateway_id = gateway['gatewayId']
                    # Get full gateway details
                    details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
                    print(f"Found existing Gateway: {gateway_id}")
                    print(f"Gateway URL: {details.get('gatewayUrl')}")
                    return {
                        'gatewayId': gateway_id,
                        'gatewayUrl': details.get('gatewayUrl'),
                        'name': name
                    }
        except Exception as list_error:
            print(f"Error listing gateways: {list_error}")
        return None
    except Exception as e:
        print(f"Error creating gateway: {e}")
        return None


def create_lambda_gateway_target(
    gateway_client,
    gateway_id: str,
    target_name: str,
    lambda_arn: str,
    tool_schemas: list,
    description: str
) -> dict:
    """
    Create a Lambda target in AgentCore Gateway.

    Args:
        gateway_client: boto3 bedrock-agentcore-control client
        gateway_id: Gateway ID to add target to
        target_name: Name for the target
        lambda_arn: Lambda function ARN
        tool_schemas: List of tool schema definitions
        description: Target description

    Returns:
        dict: Target creation response
    """
    target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": tool_schemas
                }
            }
        }
    }

    credential_config = [
        {"credentialProviderType": "GATEWAY_IAM_ROLE"}
    ]

    try:
        response = gateway_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=target_name,
            description=description,
            targetConfiguration=target_config,
            credentialProviderConfigurations=credential_config
        )
        print(f"Created Gateway target: {target_name}")
        return response
    except gateway_client.exceptions.ConflictException:
        # Target already exists, find and return it
        print(f"Gateway target '{target_name}' already exists, retrieving...")
        try:
            # Response uses 'items' key
            response = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id)
            for target in response.get('items', []):
                if target.get('name') == target_name:
                    print(f"Found existing target: {target_name}")
                    return {'targetId': target['targetId'], 'name': target_name}
        except Exception as list_error:
            print(f"Error listing targets: {list_error}")
        return None
    except Exception as e:
        print(f"Error creating target: {e}")
        return None


def delete_gateway(gateway_client, gateway_id: str) -> bool:
    """Delete an AgentCore Gateway and all its targets."""
    try:
        # First list and delete all targets (response uses 'items' key)
        response = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id)
        for target in response.get('items', []):
            try:
                gateway_client.delete_gateway_target(
                    gatewayIdentifier=gateway_id,
                    targetIdentifier=target['targetId']
                )
                print(f"Deleted target: {target['name']}")
            except Exception as e:
                print(f"Error deleting target {target['name']}: {e}")

        # Delete gateway
        gateway_client.delete_gateway(gatewayIdentifier=gateway_id)
        print(f"Deleted gateway: {gateway_id}")
        return True
    except Exception as e:
        print(f"Error deleting gateway: {e}")
        return False


def save_gateway_config(config: dict, output_path: str) -> None:
    """Save gateway configuration to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"Saved gateway config to: {output_path}")


# =============================================================================
# AgentCore Runtime Deployment Functions
# =============================================================================

def create_agent_runtime_role(iam_client, role_name: str, dynamodb_table_arns: list = None) -> dict:
    """
    Create IAM role for AgentCore Runtime with necessary permissions.

    Args:
        iam_client: boto3 IAM client
        role_name: Name for the IAM role
        dynamodb_table_arns: Optional list of DynamoDB table ARNs to grant access

    Returns:
        dict: Role creation response with ARN
    """
    # Trust policy for AgentCore Runtime
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        # Create role
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="AgentCore Runtime execution role for e-commerce agents"
        )
        role_arn = role_response['Role']['Arn']
        print(f"Created IAM role: {role_name}")

        # Attach Bedrock permissions
        bedrock_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"
                    ],
                    "Resource": "*"
                }
            ]
        }

        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-bedrock-policy",
            PolicyDocument=json.dumps(bedrock_policy)
        )

        # Attach DynamoDB permissions if provided
        if dynamodb_table_arns:
            dynamodb_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:UpdateItem",
                            "dynamodb:DeleteItem",
                            "dynamodb:Query",
                            "dynamodb:Scan"
                        ],
                        "Resource": dynamodb_table_arns
                    }
                ]
            }

            iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=f"{role_name}-dynamodb-policy",
                PolicyDocument=json.dumps(dynamodb_policy)
            )
            print(f"Attached DynamoDB policy to role")

        # Wait for role to be available
        time.sleep(10)

        return {'Role': role_response['Role'], 'exit_code': 0}

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} already exists, retrieving ARN...")
        role = iam_client.get_role(RoleName=role_name)
        return {'Role': role['Role'], 'exit_code': 0}
    except Exception as e:
        print(f"Error creating role: {e}")
        return {'Role': None, 'exit_code': 1, 'error': str(e)}


def create_agent_runtime(
    agentcore_client,
    runtime_name: str,
    role_arn: str,
    container_uri: str,
    environment_vars: dict = None,
    protocol_type: str = 'A2A',
    description: str = '',
    network_mode: str = 'PUBLIC'
) -> dict:
    """
    Create or get existing AgentCore Runtime.

    Args:
        agentcore_client: boto3 bedrock-agentcore-control client
        runtime_name: Name for the runtime
        role_arn: IAM role ARN for execution
        container_uri: ECR container image URI
        environment_vars: Environment variables for the container (string to string map)
        protocol_type: Protocol type ('A2A', 'MCP', or 'HTTP')
        description: Runtime description
        network_mode: Network mode ('PUBLIC' or 'VPC')

    Returns:
        dict: Runtime details including ARN and endpoint
    """
    try:
        # Build the request parameters
        create_params = {
            'agentRuntimeName': runtime_name,
            'roleArn': role_arn,
            'agentRuntimeArtifact': {
                'containerConfiguration': {
                    'containerUri': container_uri
                }
            },
            'networkConfiguration': {
                'networkMode': network_mode
            },
            'protocolConfiguration': {
                'serverProtocol': protocol_type
            }
        }

        # Add environment variables as top-level parameter (string to string map)
        if environment_vars:
            create_params['environmentVariables'] = environment_vars

        # Add description if provided
        if description:
            create_params['description'] = description

        response = agentcore_client.create_agent_runtime(**create_params)

        runtime_arn = response['agentRuntimeArn']
        print(f"Created AgentCore Runtime: {runtime_name}")
        print(f"Runtime ARN: {runtime_arn}")

        # Wait for runtime to be ready
        print("Waiting for runtime to be ready...")
        waiter_config = {'Delay': 10, 'MaxAttempts': 60}
        while True:
            status_response = agentcore_client.get_agent_runtime(
                agentRuntimeId=response['agentRuntimeId']
            )
            status = status_response.get('status')
            if status == 'READY':
                print(f"Runtime is ready!")
                break
            elif status in ['FAILED', 'DELETED']:
                print(f"Runtime creation failed with status: {status}")
                return None
            print(f"  Status: {status}...")
            time.sleep(10)

        return {
            'agentRuntimeId': response['agentRuntimeId'],
            'agentRuntimeArn': runtime_arn,
            'status': 'READY'
        }

    except agentcore_client.exceptions.ConflictException:
        # Runtime already exists, find and return it
        print(f"Runtime '{runtime_name}' already exists, retrieving...")
        try:
            response = agentcore_client.list_agent_runtimes()
            for runtime in response.get('items', []):
                if runtime.get('agentRuntimeName') == runtime_name:
                    runtime_id = runtime['agentRuntimeId']
                    details = agentcore_client.get_agent_runtime(agentRuntimeId=runtime_id)
                    print(f"Found existing Runtime: {runtime_id}")
                    return {
                        'agentRuntimeId': runtime_id,
                        'agentRuntimeArn': details.get('agentRuntimeArn'),
                        'status': details.get('status')
                    }
        except Exception as list_error:
            print(f"Error listing runtimes: {list_error}")
        return None
    except Exception as e:
        print(f"Error creating runtime: {e}")
        return None


def create_agent_runtime_endpoint(
    agentcore_client,
    runtime_id: str,
    endpoint_name: str,
    description: str = ''
) -> dict:
    """
    Create an endpoint for an AgentCore Runtime.

    Args:
        agentcore_client: boto3 bedrock-agentcore-control client
        runtime_id: Runtime ID to create endpoint for
        endpoint_name: Name for the endpoint
        description: Endpoint description

    Returns:
        dict: Endpoint details including URL
    """
    try:
        response = agentcore_client.create_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            name=endpoint_name,
            description=description
        )

        print(f"Created endpoint: {endpoint_name}")
        print(f"Endpoint URL: {response.get('agentRuntimeEndpointUrl')}")

        return {
            'endpointId': response.get('agentRuntimeEndpointId'),
            'endpointUrl': response.get('agentRuntimeEndpointUrl'),
            'endpointArn': response.get('agentRuntimeEndpointArn')
        }

    except agentcore_client.exceptions.ConflictException:
        print(f"Endpoint '{endpoint_name}' already exists, retrieving...")
        try:
            response = agentcore_client.list_agent_runtime_endpoints(agentRuntimeId=runtime_id)
            for endpoint in response.get('items', []):
                if endpoint.get('name') == endpoint_name:
                    print(f"Found existing endpoint: {endpoint_name}")
                    return {
                        'endpointId': endpoint.get('agentRuntimeEndpointId'),
                        'endpointUrl': endpoint.get('agentRuntimeEndpointUrl'),
                        'endpointArn': endpoint.get('agentRuntimeEndpointArn')
                    }
        except Exception as list_error:
            print(f"Error listing endpoints: {list_error}")
        return None
    except Exception as e:
        print(f"Error creating endpoint: {e}")
        return None


def get_runtime_invocation_url(region: str, runtime_arn: str) -> str:
    """
    Construct the invocation URL for an AgentCore Runtime.

    Args:
        region: AWS region
        runtime_arn: Runtime ARN

    Returns:
        str: Invocation URL
    """
    from urllib.parse import quote
    escaped_arn = quote(runtime_arn, safe='')
    return f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{escaped_arn}/invocations/"


def invoke_agent_runtime(
    agentcore_runtime_client,
    runtime_arn: str,
    session_id: str,
    payload: dict
) -> dict:
    """
    Invoke an AgentCore Runtime with a payload.

    Args:
        agentcore_runtime_client: boto3 bedrock-agentcore-runtime client
        runtime_arn: Runtime ARN to invoke
        session_id: Session ID for the invocation
        payload: JSON payload to send

    Returns:
        dict: Response from the runtime
    """
    try:
        response = agentcore_runtime_client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            sessionId=session_id,
            payload=json.dumps(payload).encode('utf-8')
        )

        # Read response
        result = b''
        for event in response.get('body', []):
            if 'chunk' in event:
                result += event['chunk']['bytes']

        return json.loads(result.decode('utf-8'))

    except Exception as e:
        print(f"Error invoking runtime: {e}")
        return {'error': str(e)}


def delete_agent_runtime(agentcore_client, runtime_id: str) -> bool:
    """Delete an AgentCore Runtime and its endpoints."""
    try:
        # First delete all endpoints
        endpoints = agentcore_client.list_agent_runtime_endpoints(agentRuntimeId=runtime_id)
        for endpoint in endpoints.get('items', []):
            try:
                agentcore_client.delete_agent_runtime_endpoint(
                    agentRuntimeId=runtime_id,
                    agentRuntimeEndpointId=endpoint['agentRuntimeEndpointId']
                )
                print(f"Deleted endpoint: {endpoint.get('name')}")
            except Exception as e:
                print(f"Error deleting endpoint: {e}")

        # Delete runtime
        agentcore_client.delete_agent_runtime(agentRuntimeId=runtime_id)
        print(f"Deleted runtime: {runtime_id}")
        return True
    except Exception as e:
        print(f"Error deleting runtime: {e}")
        return False
