"""
Account Tools Lambda Function for AgentCore Gateway MCP

This Lambda function exposes account-related tools via AgentCore Gateway.
Each tool is routed based on the bedrockagentcoreToolName in the context.
"""

import json
import os
import boto3
import uuid
from datetime import datetime
from decimal import Decimal


# Helper to convert Decimal to float for JSON serialization
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def get_accounts_table():
    """Get DynamoDB accounts table"""
    region = os.environ.get('AWS_REGION', 'us-west-2')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('ACCOUNTS_TABLE_NAME', 'ecommerce-workshop-accounts')
    return dynamodb.Table(table_name)


def get_account_info(customer_email: str) -> dict:
    """Get customer account information."""
    try:
        table = get_accounts_table()

        # Scan for account by email
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        if not response.get('Items'):
            return {
                'success': False,
                'message': f'Account not found for {customer_email}'
            }

        account = response['Items'][0]

        # Return safe account info (no sensitive data)
        return {
            'success': True,
            'email': account['email'],
            'name': f"{account.get('first_name', '')} {account.get('last_name', '')}".strip(),
            'membership_tier': account.get('membership_tier', 'standard'),
            'account_status': account.get('account_status', 'active'),
            'member_since': account.get('created_at', 'Unknown'),
            'reward_points': int(account.get('reward_points', 0)),
            'default_shipping_address': account.get('shipping_address', {})
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def update_shipping_address(customer_email: str, address: dict) -> dict:
    """Update customer's default shipping address."""
    try:
        table = get_accounts_table()

        # Find account by email
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        if not response.get('Items'):
            return {
                'success': False,
                'message': f'Account not found for {customer_email}'
            }

        account = response['Items'][0]
        customer_id = account['customer_id']

        # Validate address fields
        required_fields = ['street', 'city', 'state', 'zip_code', 'country']
        missing_fields = [f for f in required_fields if f not in address]
        if missing_fields:
            return {
                'success': False,
                'message': f'Missing required address fields: {", ".join(missing_fields)}'
            }

        # Update address
        table.update_item(
            Key={'customer_id': customer_id},
            UpdateExpression='SET shipping_address = :addr, updated_at = :updated',
            ExpressionAttributeValues={
                ':addr': address,
                ':updated': datetime.now().isoformat()
            }
        )

        return {
            'success': True,
            'message': 'Shipping address updated successfully',
            'new_address': address
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_membership_benefits(tier: str) -> dict:
    """Get membership tier benefits and comparison."""
    benefits = {
        'standard': {
            'tier': 'Standard',
            'free_shipping_threshold': 50,
            'points_multiplier': 1.0,
            'return_window_days': 30,
            'exclusive_access': False,
            'priority_support': False,
            'birthday_discount': '10%',
            'annual_fee': 0
        },
        'gold': {
            'tier': 'Gold',
            'free_shipping_threshold': 25,
            'points_multiplier': 1.5,
            'return_window_days': 45,
            'exclusive_access': True,
            'priority_support': False,
            'birthday_discount': '15%',
            'annual_fee': 49
        },
        'platinum': {
            'tier': 'Platinum',
            'free_shipping_threshold': 0,
            'points_multiplier': 2.0,
            'return_window_days': 60,
            'exclusive_access': True,
            'priority_support': True,
            'birthday_discount': '20%',
            'annual_fee': 99
        }
    }

    tier_lower = tier.lower()
    if tier_lower in benefits:
        result = {
            'success': True,
            'requested_tier': benefits[tier_lower],
            'all_tiers': benefits
        }

        # Add upgrade recommendation
        if tier_lower == 'standard':
            result['upgrade_recommendation'] = 'Upgrade to Gold for lower free shipping threshold and 1.5x points!'
        elif tier_lower == 'gold':
            result['upgrade_recommendation'] = 'Upgrade to Platinum for free shipping on all orders and 2x points!'

        return result

    return {
        'success': False,
        'error': f'Unknown tier: {tier}. Valid tiers: standard, gold, platinum'
    }


def initiate_password_reset(customer_email: str) -> dict:
    """Initiate a password reset request."""
    try:
        table = get_accounts_table()

        # Verify account exists (but don't reveal this to prevent enumeration)
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        # Always return success message for security (don't reveal if account exists)
        reset_token = str(uuid.uuid4())[:8]

        # If account exists, update with reset token
        if response.get('Items'):
            account = response['Items'][0]
            table.update_item(
                Key={'customer_id': account['customer_id']},
                UpdateExpression='SET password_reset_token = :token, password_reset_expires = :expires',
                ExpressionAttributeValues={
                    ':token': reset_token,
                    ':expires': datetime.now().isoformat()
                }
            )

        return {
            'success': True,
            'message': f'If an account exists for {customer_email}, a password reset link has been sent.',
            'instructions': [
                'Check your email for the reset link',
                'The link will expire in 1 hour',
                'If you don\'t receive the email, check your spam folder'
            ]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def update_notification_preferences(customer_email: str, preferences: dict) -> dict:
    """Update customer notification preferences."""
    try:
        table = get_accounts_table()

        # Find account by email
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        if not response.get('Items'):
            return {
                'success': False,
                'message': f'Account not found for {customer_email}'
            }

        account = response['Items'][0]
        customer_id = account['customer_id']

        # Validate preference keys
        valid_preferences = ['email_marketing', 'order_updates', 'promotions', 'newsletter', 'sms_alerts']
        invalid_keys = [k for k in preferences.keys() if k not in valid_preferences]
        if invalid_keys:
            return {
                'success': False,
                'message': f'Invalid preference keys: {", ".join(invalid_keys)}. Valid keys: {", ".join(valid_preferences)}'
            }

        # Update preferences
        table.update_item(
            Key={'customer_id': customer_id},
            UpdateExpression='SET notification_preferences = :prefs, updated_at = :updated',
            ExpressionAttributeValues={
                ':prefs': preferences,
                ':updated': datetime.now().isoformat()
            }
        )

        return {
            'success': True,
            'message': 'Notification preferences updated successfully',
            'preferences': preferences
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_reward_points(customer_email: str) -> dict:
    """Get customer's reward points balance and history."""
    try:
        table = get_accounts_table()

        # Find account by email
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        if not response.get('Items'):
            return {
                'success': False,
                'message': f'Account not found for {customer_email}'
            }

        account = response['Items'][0]
        points = int(account.get('reward_points', 0))
        tier = account.get('membership_tier', 'standard')

        # Calculate points value ($1 per 100 points)
        points_value = points / 100

        return {
            'success': True,
            'current_points': points,
            'points_value': f'${points_value:.2f}',
            'membership_tier': tier,
            'points_multiplier': {'standard': 1.0, 'gold': 1.5, 'platinum': 2.0}.get(tier, 1.0),
            'points_to_next_reward': max(0, 500 - (points % 500)),
            'redemption_info': {
                'minimum_redemption': 500,
                'points_per_dollar': 100
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# Tool routing map
TOOLS = {
    'get_account_info': get_account_info,
    'update_shipping_address': update_shipping_address,
    'get_membership_benefits': get_membership_benefits,
    'initiate_password_reset': initiate_password_reset,
    'update_notification_preferences': update_notification_preferences,
    'get_reward_points': get_reward_points
}


def lambda_handler(event, context):
    """
    Main Lambda handler for AgentCore Gateway MCP tools.

    Routes to appropriate tool based on bedrockAgentCoreToolName from context.
    """
    try:
        # Get tool name from context (set by AgentCore Gateway)
        tool_name = None
        if hasattr(context, 'client_context') and context.client_context:
            custom = getattr(context.client_context, 'custom', {}) or {}
            # AgentCore Gateway uses camelCase key
            tool_name = custom.get('bedrockAgentCoreToolName')

        # Fallback to event for testing
        if not tool_name:
            tool_name = event.get('tool_name') or event.get('__context__', {}).get('bedrockAgentCoreToolName')

        if not tool_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No tool name specified'})
            }

        # Strip target prefix if present (e.g., "AccountTools___get_account_info" -> "get_account_info")
        delimiter = "___"
        if delimiter in tool_name:
            tool_name = tool_name[tool_name.index(delimiter) + len(delimiter):]

        # Get the tool function
        tool_func = TOOLS.get(tool_name)
        if not tool_func:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unknown tool: {tool_name}'})
            }

        # Extract arguments from event
        args = event.get('arguments', event)
        if isinstance(args, str):
            args = json.loads(args)

        # Remove metadata keys
        args = {k: v for k, v in args.items() if not k.startswith('__') and k != 'tool_name'}

        # Execute tool
        result = tool_func(**args)

        return {
            'statusCode': 200,
            'body': json.dumps(result, default=decimal_default)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
