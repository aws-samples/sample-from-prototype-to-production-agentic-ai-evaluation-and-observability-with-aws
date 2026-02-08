"""
Utility Functions for Module 03 - Production Deployment

Helper functions for deploying a single Product Catalog Agent with RBAC to
Amazon Bedrock AgentCore, including:
  - Lambda function deployment (product tools + RBAC interceptor)
  - Cognito User Pool with customer/admin groups
  - AgentCore Gateway with interceptor-based RBAC
  - AgentCore Runtime for containerized agent hosting
"""

import boto3
import json
import zipfile
import os
import time
import base64
from datetime import datetime


# ===========================================================================
# Lambda & IAM
# ===========================================================================

def create_lambda_execution_role(iam_client, role_name: str, dynamodb_table_arns: list) -> dict:
    """Create IAM role for Lambda functions with DynamoDB access."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Lambda execution role for product catalog tools"
        )
        role_arn = role_response['Role']['Arn']
        print(f"Created IAM role: {role_name}")

        # Basic Lambda execution
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        )

        # DynamoDB access
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-dynamodb-policy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem", "dynamodb:PutItem",
                        "dynamodb:UpdateItem", "dynamodb:DeleteItem",
                        "dynamodb:Query", "dynamodb:Scan"
                    ],
                    "Resource": dynamodb_table_arns
                }]
            })
        )
        print(f"Attached DynamoDB policy to role")
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
    lambda_client, function_name: str, role_arn: str,
    code_path: str, handler: str, environment_vars: dict, region: str
) -> dict:
    """Create or update a Lambda function."""
    zip_path = f"/tmp/{function_name}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        base_name = os.path.basename(code_path)
        zipf.write(code_path, base_name)

    with open(zip_path, 'rb') as f:
        zip_content = f.read()

    try:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.11',
            Role=role_arn,
            Handler=handler,
            Code={'ZipFile': zip_content},
            Description='E-Commerce Product Catalog Tool Lambda',
            Timeout=30,
            MemorySize=256,
            Environment={'Variables': environment_vars}
        )
        print(f"Created Lambda function: {function_name}")
        waiter = lambda_client.get_waiter('function_active')
        waiter.wait(FunctionName=function_name)
        return {'function_arn': response['FunctionArn'], 'function_name': function_name, 'exit_code': 0}

    except lambda_client.exceptions.ResourceConflictException:
        print(f"Function {function_name} exists, updating...")
        response = lambda_client.update_function_code(FunctionName=function_name, ZipFile=zip_content)
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': environment_vars}
        )
        return {'function_arn': response['FunctionArn'], 'function_name': function_name, 'exit_code': 0}
    except Exception as e:
        print(f"Error creating/updating Lambda: {e}")
        return {'function_arn': None, 'exit_code': 1, 'error': str(e)}


# ===========================================================================
# Cognito with Groups (customer / admin)
# ===========================================================================

def get_or_create_cognito_user_pool(cognito_client, pool_name: str) -> str:
    """Get existing or create new Cognito User Pool."""
    response = cognito_client.list_user_pools(MaxResults=60)
    for pool in response['UserPools']:
        if pool['Name'] == pool_name:
            print(f"Found existing user pool: {pool['Id']}")
            return pool['Id']

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
        Schema=[{'Name': 'email', 'AttributeDataType': 'String', 'Required': True}]
    )
    print(f"Created user pool: {response['UserPool']['Id']}")
    return response['UserPool']['Id']


def create_cognito_group(cognito_client, user_pool_id: str, group_name: str, description: str = '') -> None:
    """Create a group in the Cognito User Pool."""
    try:
        cognito_client.create_group(
            GroupName=group_name,
            UserPoolId=user_pool_id,
            Description=description
        )
        print(f"Created Cognito group: {group_name}")
    except cognito_client.exceptions.GroupExistsException:
        print(f"Group '{group_name}' already exists")


def get_or_create_cognito_resource_server(
    cognito_client, user_pool_id: str, identifier: str, name: str, scopes: list
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
    cognito_client, user_pool_id: str, client_name: str,
    resource_server_id: str, scopes: list
) -> tuple:
    """Create Cognito app client for M2M authentication."""
    response = cognito_client.list_user_pool_clients(UserPoolId=user_pool_id, MaxResults=60)
    for client in response['UserPoolClients']:
        if client['ClientName'] == client_name:
            details = cognito_client.describe_user_pool_client(
                UserPoolId=user_pool_id, ClientId=client['ClientId']
            )
            print(f"Found existing app client: {client['ClientId']}")
            return client['ClientId'], details['UserPoolClient'].get('ClientSecret')

    response = cognito_client.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=client_name,
        GenerateSecret=True,
        AllowedOAuthFlows=['client_credentials'],
        AllowedOAuthScopes=scopes,
        AllowedOAuthFlowsUserPoolClient=True,
        SupportedIdentityProviders=['COGNITO']
    )
    print(f"Created app client: {response['UserPoolClient']['ClientId']}")
    return response['UserPoolClient']['ClientId'], response['UserPoolClient']['ClientSecret']


def get_or_create_user_app_client(
    cognito_client, user_pool_id: str, client_name: str
) -> str:
    """Create Cognito app client for user login (USER_PASSWORD_AUTH)."""
    response = cognito_client.list_user_pool_clients(UserPoolId=user_pool_id, MaxResults=60)
    for client in response['UserPoolClients']:
        if client['ClientName'] == client_name:
            print(f"Found existing user app client: {client['ClientId']}")
            return client['ClientId']

    response = cognito_client.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=client_name,
        GenerateSecret=False,
        ExplicitAuthFlows=[
            'ALLOW_USER_PASSWORD_AUTH',
            'ALLOW_REFRESH_TOKEN_AUTH'
        ]
    )
    print(f"Created user app client: {response['UserPoolClient']['ClientId']}")
    return response['UserPoolClient']['ClientId']


def get_or_create_cognito_domain(cognito_client, user_pool_id: str, domain_prefix: str) -> str:
    """Create Cognito domain for OAuth endpoints."""
    try:
        cognito_client.create_user_pool_domain(Domain=domain_prefix, UserPoolId=user_pool_id)
        print(f"Created Cognito domain: {domain_prefix}")
    except cognito_client.exceptions.InvalidParameterException:
        print(f"Domain {domain_prefix} already exists or invalid")
    return domain_prefix


def create_test_user(
    cognito_client, user_pool_id: str, email: str, password: str,
    group_name: str = None, name: str = ''
) -> None:
    """Create a test user in Cognito and optionally add to a group."""
    try:
        attrs = [
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'true'}
        ]
        if name:
            attrs.append({'Name': 'name', 'Value': name})

        cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=attrs,
            MessageAction='SUPPRESS'
        )
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True
        )
        print(f"Created test user: {email}")
    except cognito_client.exceptions.UsernameExistsException:
        print(f"User {email} already exists")

    # Add to group
    if group_name:
        try:
            cognito_client.admin_add_user_to_group(
                UserPoolId=user_pool_id,
                Username=email,
                GroupName=group_name
            )
            print(f"Added {email} to group: {group_name}")
        except Exception as e:
            print(f"Error adding user to group: {e}")


def get_user_token(
    cognito_client, user_pool_id: str, client_id: str,
    email: str, password: str
) -> dict:
    """Get user tokens via USER_PASSWORD_AUTH flow (includes cognito:groups in ID token)."""
    try:
        response = cognito_client.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow='ADMIN_USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': email,
                'PASSWORD': password
            }
        )
        tokens = response.get('AuthenticationResult', {})
        print(f"Got tokens for user: {email}")
        return {
            'id_token': tokens.get('IdToken', ''),
            'access_token': tokens.get('AccessToken', ''),
            'token_type': tokens.get('TokenType', 'Bearer')
        }
    except Exception as e:
        print(f"Error getting user token: {e}")
        return {}


def get_oauth_token(user_pool_id: str, client_id: str, client_secret: str, scopes: str, region: str) -> dict:
    """Get OAuth access token via client credentials grant (M2M)."""
    import requests

    cognito = boto3.client('cognito-idp', region_name=region)
    try:
        pool_info = cognito.describe_user_pool(UserPoolId=user_pool_id)
        domain = pool_info['UserPool'].get('Domain')

        if domain:
            token_url = f"https://{domain}.auth.{region}.amazoncognito.com/oauth2/token"
            credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            response = requests.post(
                token_url,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {credentials}'
                },
                data={'grant_type': 'client_credentials', 'scope': scopes}
            )
            return response.json()
    except Exception as e:
        print(f"Error getting token: {e}")
    return {}


# ===========================================================================
# AgentCore Gateway with RBAC Interceptor
# ===========================================================================

def create_agentcore_gateway_role(iam_client, role_name: str, lambda_arns: list) -> dict:
    """Create IAM role for AgentCore Gateway with Lambda invoke permissions."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="AgentCore Gateway role for product catalog workshop"
        )
        print(f"Created Gateway IAM role: {role_name}")

        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-lambda-invoke-policy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": "lambda:InvokeFunction",
                    "Resource": lambda_arns
                }]
            })
        )
        print(f"Attached Lambda invoke policy to Gateway role")
        time.sleep(10)
        return {'Role': role_response['Role']}

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} already exists, retrieving...")
        role = iam_client.get_role(RoleName=role_name)
        return {'Role': role['Role']}


def create_gateway(
    gateway_client, name: str, role_arn: str, auth_config: dict,
    description: str, interceptor_lambda_arn: str = None
) -> dict:
    """
    Create AgentCore Gateway with optional RBAC interceptor.

    Args:
        gateway_client: bedrock-agentcore-control client
        name: Gateway name
        role_arn: Gateway IAM role ARN
        auth_config: JWT authorizer configuration
        description: Gateway description
        interceptor_lambda_arn: Optional Lambda ARN for RBAC interceptor
    """
    create_params = {
        'name': name,
        'roleArn': role_arn,
        'protocolType': 'MCP',
        'authorizerType': 'CUSTOM_JWT',
        'authorizerConfiguration': auth_config,
        'description': description
    }

    # Add RBAC interceptor if provided
    if interceptor_lambda_arn:
        create_params['interceptorConfigurations'] = [
            {
                'interceptor': {'lambda': {'arn': interceptor_lambda_arn}},
                'interceptionPoints': ['REQUEST'],
                'inputConfiguration': {'passRequestHeaders': True}
            },
            {
                'interceptor': {'lambda': {'arn': interceptor_lambda_arn}},
                'interceptionPoints': ['RESPONSE'],
                'inputConfiguration': {'passRequestHeaders': True}
            }
        ]

    try:
        response = gateway_client.create_gateway(**create_params)
        print(f"Created Gateway: {response['gatewayId']}")
        print(f"Gateway URL: {response['gatewayUrl']}")
        if interceptor_lambda_arn:
            print(f"RBAC Interceptor: attached (REQUEST + RESPONSE)")
        return response
    except gateway_client.exceptions.ConflictException:
        print(f"Gateway '{name}' already exists, retrieving...")
        try:
            response = gateway_client.list_gateways()
            for gw in response.get('items', []):
                if gw.get('name') == name:
                    details = gateway_client.get_gateway(gatewayIdentifier=gw['gatewayId'])
                    print(f"Found existing Gateway: {gw['gatewayId']}")
                    return {
                        'gatewayId': gw['gatewayId'],
                        'gatewayUrl': details.get('gatewayUrl'),
                        'name': name
                    }
        except Exception as e:
            print(f"Error listing gateways: {e}")
        return None
    except Exception as e:
        print(f"Error creating gateway: {e}")
        return None


def create_lambda_gateway_target(
    gateway_client, gateway_id: str, target_name: str,
    lambda_arn: str, tool_schemas: list, description: str
) -> dict:
    """Create a Lambda target in AgentCore Gateway."""
    target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {"inlinePayload": tool_schemas}
            }
        }
    }
    credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

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
        print(f"Target '{target_name}' already exists, retrieving...")
        try:
            response = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id)
            for t in response.get('items', []):
                if t.get('name') == target_name:
                    return {'targetId': t['targetId'], 'name': target_name}
        except Exception as e:
            print(f"Error listing targets: {e}")
        return None
    except Exception as e:
        print(f"Error creating target: {e}")
        return None


def delete_gateway(gateway_client, gateway_id: str) -> bool:
    """Delete an AgentCore Gateway and all its targets."""
    try:
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

        gateway_client.delete_gateway(gatewayIdentifier=gateway_id)
        print(f"Deleted gateway: {gateway_id}")
        return True
    except Exception as e:
        print(f"Error deleting gateway: {e}")
        return False


# ===========================================================================
# AgentCore Runtime
# ===========================================================================

def create_agent_runtime_role(iam_client, role_name: str, gateway_arn: str = None) -> dict:
    """Create IAM role for AgentCore Runtime with Bedrock + Gateway permissions."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="AgentCore Runtime role for product catalog agent"
        )
        print(f"Created Runtime IAM role: {role_name}")

        # Bedrock model invocation
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-bedrock-policy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"
                    ],
                    "Resource": "*"
                }]
            })
        )

        # ECR pull + CloudWatch logs
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-ecr-logs-policy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ecr:BatchGetImage",
                            "ecr:GetDownloadUrlForLayer",
                            "ecr:BatchCheckLayerAvailability",
                            "ecr:GetAuthorizationToken"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents"
                        ],
                        "Resource": "arn:aws:logs:*:*:log-group:/aws/bedrock-agentcore/*"
                    }
                ]
            })
        )

        # AgentCore Gateway invocation (for MCP tools)
        if gateway_arn:
            iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=f"{role_name}-gateway-policy",
                PolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": "bedrock-agentcore:InvokeGateway",
                        "Resource": gateway_arn
                    }]
                })
            )

        # Workload identity (for JWT token exchange)
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-identity-policy",
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "bedrock-agentcore:GetWorkloadAccessToken",
                        "bedrock-agentcore:GetWorkloadAccessTokenForJWT"
                    ],
                    "Resource": "*"
                }]
            })
        )

        time.sleep(10)
        return {'Role': role_response['Role'], 'exit_code': 0}

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} already exists, retrieving...")
        role = iam_client.get_role(RoleName=role_name)
        return {'Role': role['Role'], 'exit_code': 0}
    except Exception as e:
        print(f"Error creating role: {e}")
        return {'Role': None, 'exit_code': 1, 'error': str(e)}


def create_agent_runtime(
    agentcore_client, runtime_name: str, role_arn: str,
    container_uri: str, environment_vars: dict = None,
    auth_config: dict = None, description: str = ''
) -> dict:
    """Create AgentCore Runtime with optional JWT auth."""
    try:
        create_params = {
            'agentRuntimeName': runtime_name,
            'roleArn': role_arn,
            'agentRuntimeArtifact': {
                'containerConfiguration': {'containerUri': container_uri}
            },
            'networkConfiguration': {'networkMode': 'PUBLIC'},
            'protocolConfiguration': {'serverProtocol': 'HTTP'}
        }

        if environment_vars:
            create_params['environmentVariables'] = environment_vars
        if auth_config:
            create_params['authorizerConfiguration'] = auth_config
        if description:
            create_params['description'] = description

        response = agentcore_client.create_agent_runtime(**create_params)
        runtime_arn = response['agentRuntimeArn']
        print(f"Created AgentCore Runtime: {runtime_name}")
        print(f"Runtime ARN: {runtime_arn}")

        # Wait for ready
        print("Waiting for runtime to be ready...")
        while True:
            status_response = agentcore_client.get_agent_runtime(
                agentRuntimeId=response['agentRuntimeId']
            )
            status = status_response.get('status')
            if status == 'READY':
                print(f"Runtime is ready!")
                break
            elif status in ['FAILED', 'DELETED']:
                print(f"Runtime failed: {status}")
                return None
            print(f"  Status: {status}...")
            time.sleep(10)

        return {
            'agentRuntimeId': response['agentRuntimeId'],
            'agentRuntimeArn': runtime_arn,
            'status': 'READY'
        }

    except agentcore_client.exceptions.ConflictException:
        print(f"Runtime '{runtime_name}' already exists, retrieving...")
        try:
            response = agentcore_client.list_agent_runtimes()
            for rt in response.get('items', []):
                if rt.get('agentRuntimeName') == runtime_name:
                    details = agentcore_client.get_agent_runtime(agentRuntimeId=rt['agentRuntimeId'])
                    return {
                        'agentRuntimeId': rt['agentRuntimeId'],
                        'agentRuntimeArn': details.get('agentRuntimeArn'),
                        'status': details.get('status')
                    }
        except Exception as e:
            print(f"Error listing runtimes: {e}")
        return None
    except Exception as e:
        print(f"Error creating runtime: {e}")
        return None


def create_agent_runtime_endpoint(
    agentcore_client, runtime_id: str, endpoint_name: str, description: str = ''
) -> dict:
    """Create an endpoint for an AgentCore Runtime."""
    try:
        response = agentcore_client.create_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            name=endpoint_name,
            description=description
        )
        print(f"Created endpoint: {endpoint_name}")
        return {
            'endpointId': response.get('agentRuntimeEndpointId'),
            'endpointUrl': response.get('agentRuntimeEndpointUrl'),
            'endpointArn': response.get('agentRuntimeEndpointArn')
        }
    except agentcore_client.exceptions.ConflictException:
        print(f"Endpoint '{endpoint_name}' already exists, retrieving...")
        try:
            response = agentcore_client.list_agent_runtime_endpoints(agentRuntimeId=runtime_id)
            for ep in response.get('items', []):
                if ep.get('name') == endpoint_name:
                    return {
                        'endpointId': ep.get('agentRuntimeEndpointId'),
                        'endpointUrl': ep.get('agentRuntimeEndpointUrl'),
                        'endpointArn': ep.get('agentRuntimeEndpointArn')
                    }
        except Exception as e:
            print(f"Error listing endpoints: {e}")
        return None
    except Exception as e:
        print(f"Error creating endpoint: {e}")
        return None


def invoke_agent_runtime(
    agentcore_runtime_client, runtime_arn: str, session_id: str, payload: dict
) -> dict:
    """Invoke an AgentCore Runtime with a payload."""
    try:
        response = agentcore_runtime_client.invoke_agent_runtime(
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
        print(f"Error invoking runtime: {e}")
        return {'error': str(e)}


# ===========================================================================
# Cleanup
# ===========================================================================

def delete_agent_runtime(agentcore_client, runtime_id: str) -> bool:
    """Delete an AgentCore Runtime and its endpoints."""
    try:
        endpoints = agentcore_client.list_agent_runtime_endpoints(agentRuntimeId=runtime_id)
        for ep in endpoints.get('items', []):
            try:
                agentcore_client.delete_agent_runtime_endpoint(
                    agentRuntimeId=runtime_id,
                    agentRuntimeEndpointId=ep['agentRuntimeEndpointId']
                )
                print(f"Deleted endpoint: {ep.get('name')}")
            except Exception as e:
                print(f"Error deleting endpoint: {e}")

        agentcore_client.delete_agent_runtime(agentRuntimeId=runtime_id)
        print(f"Deleted runtime: {runtime_id}")
        return True
    except Exception as e:
        print(f"Error deleting runtime: {e}")
        return False


def save_config(config: dict, output_path: str) -> None:
    """Save configuration to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)
    print(f"Saved config to: {output_path}")


# ===========================================================================
# Tool Schema Definitions (for Gateway target registration)
# ===========================================================================

def get_product_tool_schemas() -> list:
    """Return the 11 product tool schemas for AgentCore Gateway registration."""
    return [
        # --- READ tools ---
        {
            "name": "search_products",
            "description": "Search for products in the catalog using keywords and optional category filter",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords"},
                    "category": {"type": "string", "description": "Optional category filter"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_product_details",
            "description": "Get detailed information about a specific product by its ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID (e.g., PROD-001)"}
                },
                "required": ["product_id"]
            }
        },
        {
            "name": "check_inventory",
            "description": "Check inventory availability and stock quantity for a product",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to check"}
                },
                "required": ["product_id"]
            }
        },
        {
            "name": "get_product_recommendations",
            "description": "Get product recommendations based on category and price criteria",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Product category"},
                    "price_max": {"type": "number", "description": "Maximum price filter"},
                    "limit": {"type": "integer", "description": "Max recommendations (default 5)"}
                }
            }
        },
        {
            "name": "compare_products",
            "description": "Compare multiple products side by side (2-5 products)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of product IDs to compare"
                    }
                },
                "required": ["product_ids"]
            }
        },
        {
            "name": "get_return_policy",
            "description": "Get return policy information, optionally for a specific product",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Optional product ID for specific policy"}
                }
            }
        },
        # --- WRITE tools (admin only, enforced by RBAC interceptor) ---
        {
            "name": "create_product",
            "description": "Create a new product in the catalog (admin only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Unique product ID"},
                    "name": {"type": "string", "description": "Product name"},
                    "category": {"type": "string", "description": "Product category"},
                    "price": {"type": "number", "description": "Price in USD"},
                    "description": {"type": "string", "description": "Product description"},
                    "specifications": {"type": "string", "description": "Specs as JSON string"},
                    "stock_quantity": {"type": "integer", "description": "Initial stock"},
                    "warranty": {"type": "string", "description": "Warranty info"},
                    "return_policy": {"type": "string", "description": "Return policy"}
                },
                "required": ["product_id", "name", "category", "price", "description", "specifications"]
            }
        },
        {
            "name": "update_product",
            "description": "Update an existing product's information (admin only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to update"},
                    "updates": {"type": "string", "description": "JSON string with fields to update"}
                },
                "required": ["product_id", "updates"]
            }
        },
        {
            "name": "delete_product",
            "description": "Soft-delete a product by marking it as discontinued (admin only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID to delete"}
                },
                "required": ["product_id"]
            }
        },
        {
            "name": "update_inventory",
            "description": "Update inventory levels for a product (admin only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"},
                    "new_quantity": {"type": "integer", "description": "New stock quantity"},
                    "restock_date": {"type": "string", "description": "Restock date (YYYY-MM-DD)"}
                },
                "required": ["product_id", "new_quantity"]
            }
        },
        {
            "name": "update_pricing",
            "description": "Update pricing for a product, optionally set a sale price (admin only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"},
                    "new_price": {"type": "number", "description": "New regular price"},
                    "sale_price": {"type": "number", "description": "Optional sale price"},
                    "sale_end_date": {"type": "string", "description": "Sale end date (YYYY-MM-DD)"}
                },
                "required": ["product_id", "new_price"]
            }
        }
    ]
