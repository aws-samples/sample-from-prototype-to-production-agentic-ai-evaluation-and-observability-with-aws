"""
Account Management Tools for E-Commerce Customer Service Agent

These tools interact with DynamoDB to manage customer accounts.
"""

import boto3
import os
from strands import tool
from datetime import datetime
from typing import Optional
import json
import uuid


def get_dynamodb_table():
    """Get DynamoDB table resource for accounts"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('ACCOUNTS_TABLE_NAME', 'ecommerce-workshop-accounts')
    return dynamodb.Table(table_name)


@tool
def get_account_info(customer_email: str) -> dict:
    """
    Get customer account information by email.

    Args:
        customer_email: Customer's email address

    Returns:
        dict: Account details including membership tier, preferences, and contact info
    """
    try:
        table = get_dynamodb_table()

        # Scan with email filter (in production, use GSI)
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        items = response.get('Items', [])

        if not items:
            return {
                'success': False,
                'error': f'No account found for {customer_email}',
                'message': 'Account not found. Please verify the email address or create a new account.'
            }

        account = items[0]

        # Don't expose sensitive info
        return {
            'success': True,
            'customer_id': account['customer_id'],
            'email': account['email'],
            'first_name': account['first_name'],
            'last_name': account['last_name'],
            'phone': account.get('phone', 'Not provided'),
            'account_status': account['account_status'],
            'membership_tier': account['membership_tier'],
            'member_since': account['created_date'],
            'total_orders': account.get('total_orders', 0),
            'total_spent': float(account.get('total_spent', 0)),
            'preferences': account.get('preferences', {}),
            'default_shipping_address': account.get('default_shipping_address', {})
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error retrieving account for {customer_email}'
        }


@tool
def update_shipping_address(customer_email: str, new_address: dict) -> dict:
    """
    Update customer's default shipping address.

    Args:
        customer_email: Customer's email address
        new_address: New address with fields: street, city, state, zip, country

    Returns:
        dict: Confirmation of address update
    """
    try:
        table = get_dynamodb_table()

        # Find customer by email
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        items = response.get('Items', [])

        if not items:
            return {
                'success': False,
                'error': f'Account not found for {customer_email}'
            }

        customer_id = items[0]['customer_id']

        # Validate address fields
        required_fields = ['street', 'city', 'state', 'zip']
        if isinstance(new_address, str):
            try:
                new_address = json.loads(new_address)
            except json.JSONDecodeError:
                return {
                    'success': False,
                    'error': 'Invalid address format. Please provide a valid JSON object.'
                }

        missing_fields = [f for f in required_fields if f not in new_address]
        if missing_fields:
            return {
                'success': False,
                'error': f'Missing required address fields: {", ".join(missing_fields)}'
            }

        # Add country if not provided
        if 'country' not in new_address:
            new_address['country'] = 'USA'

        # Update address
        table.update_item(
            Key={'customer_id': customer_id},
            UpdateExpression='SET default_shipping_address = :addr',
            ExpressionAttributeValues={':addr': new_address}
        )

        return {
            'success': True,
            'customer_email': customer_email,
            'new_address': new_address,
            'message': 'Shipping address updated successfully.'
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error updating address for {customer_email}'
        }


@tool
def update_notification_preferences(customer_email: str, email_notifications: Optional[bool] = None,
                                    sms_notifications: Optional[bool] = None,
                                    marketing_emails: Optional[bool] = None) -> dict:
    """
    Update customer notification preferences.

    Args:
        customer_email: Customer's email address
        email_notifications: Enable/disable email notifications for orders
        sms_notifications: Enable/disable SMS notifications
        marketing_emails: Enable/disable marketing emails

    Returns:
        dict: Updated preferences confirmation
    """
    try:
        table = get_dynamodb_table()

        # Find customer
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        items = response.get('Items', [])

        if not items:
            return {
                'success': False,
                'error': f'Account not found for {customer_email}'
            }

        customer_id = items[0]['customer_id']
        current_prefs = items[0].get('preferences', {})

        # Update only provided preferences
        if email_notifications is not None:
            current_prefs['email_notifications'] = email_notifications
        if sms_notifications is not None:
            current_prefs['sms_notifications'] = sms_notifications
        if marketing_emails is not None:
            current_prefs['marketing_emails'] = marketing_emails

        table.update_item(
            Key={'customer_id': customer_id},
            UpdateExpression='SET preferences = :prefs',
            ExpressionAttributeValues={':prefs': current_prefs}
        )

        return {
            'success': True,
            'customer_email': customer_email,
            'updated_preferences': current_prefs,
            'message': 'Notification preferences updated successfully.'
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error updating preferences for {customer_email}'
        }


@tool
def get_payment_methods(customer_email: str) -> dict:
    """
    Get customer's saved payment methods (masked for security).

    Args:
        customer_email: Customer's email address

    Returns:
        dict: List of saved payment methods with masked details
    """
    try:
        table = get_dynamodb_table()

        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        items = response.get('Items', [])

        if not items:
            return {
                'success': False,
                'error': f'Account not found for {customer_email}'
            }

        payment_methods = items[0].get('payment_methods', [])

        # Mask sensitive data
        masked_methods = []
        for pm in payment_methods:
            masked = {
                'type': pm['type'],
                'is_default': pm.get('is_default', False)
            }
            if pm['type'] == 'credit_card':
                masked['last_four'] = pm.get('last_four', '****')
                masked['brand'] = pm.get('brand', 'Unknown')
            elif pm['type'] == 'paypal':
                email = pm.get('email', '')
                masked['email'] = email[:3] + '***' + email[email.index('@'):] if '@' in email else '***'

            masked_methods.append(masked)

        return {
            'success': True,
            'customer_email': customer_email,
            'payment_methods': masked_methods,
            'count': len(masked_methods)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error retrieving payment methods for {customer_email}'
        }


@tool
def initiate_password_reset(customer_email: str) -> dict:
    """
    Initiate password reset process for customer account.

    Args:
        customer_email: Customer's email address

    Returns:
        dict: Password reset confirmation
    """
    try:
        table = get_dynamodb_table()

        # Verify account exists
        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        items = response.get('Items', [])

        if not items:
            # Security: Don't reveal if account exists
            return {
                'success': True,
                'message': 'If an account exists with this email, a password reset link will be sent.'
            }

        account = items[0]

        # Check if account is active
        if account['account_status'] != 'active':
            return {
                'success': False,
                'message': f'Account is currently {account["account_status"]}. Please contact customer support.'
            }

        # Generate reset token (simulated)
        reset_token = str(uuid.uuid4())[:8]

        # In production, would send email and store token
        # Here we just simulate the process
        table.update_item(
            Key={'customer_id': account['customer_id']},
            UpdateExpression='SET password_reset_token = :token, password_reset_expiry = :expiry',
            ExpressionAttributeValues={
                ':token': reset_token,
                ':expiry': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        )

        return {
            'success': True,
            'message': f'Password reset link sent to {customer_email}. Please check your email (including spam folder). Link expires in 1 hour.',
            'note': 'For security, we cannot confirm if an account exists with this email.'
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Error initiating password reset'
        }


@tool
def get_membership_benefits(membership_tier: str) -> dict:
    """
    Get benefits information for a membership tier.

    Args:
        membership_tier: Tier name (standard, gold, platinum)

    Returns:
        dict: Benefits and perks for the membership tier
    """
    benefits = {
        'standard': {
            'tier': 'Standard',
            'free_shipping_threshold': 50.00,
            'return_window_days': 30,
            'exclusive_sales': False,
            'priority_support': False,
            'points_multiplier': 1.0,
            'benefits': [
                'Free shipping on orders over $50',
                '30-day return window',
                'Standard customer support',
                'Earn 1 point per $1 spent'
            ]
        },
        'gold': {
            'tier': 'Gold',
            'free_shipping_threshold': 25.00,
            'return_window_days': 45,
            'exclusive_sales': True,
            'priority_support': False,
            'points_multiplier': 1.5,
            'benefits': [
                'Free shipping on orders over $25',
                '45-day return window',
                'Early access to sales',
                'Earn 1.5 points per $1 spent',
                'Birthday discount (15% off)'
            ]
        },
        'platinum': {
            'tier': 'Platinum',
            'free_shipping_threshold': 0,
            'return_window_days': 60,
            'exclusive_sales': True,
            'priority_support': True,
            'points_multiplier': 2.0,
            'benefits': [
                'Free shipping on all orders',
                '60-day return window',
                'Priority customer support',
                'Exclusive member-only sales',
                'Earn 2 points per $1 spent',
                'Birthday discount (25% off)',
                'Free gift wrapping'
            ]
        }
    }

    tier_lower = membership_tier.lower()

    if tier_lower not in benefits:
        return {
            'success': False,
            'error': f'Unknown membership tier: {membership_tier}',
            'available_tiers': list(benefits.keys())
        }

    return {
        'success': True,
        **benefits[tier_lower]
    }


@tool
def check_account_status(customer_email: str) -> dict:
    """
    Check if a customer account is active and in good standing.

    Args:
        customer_email: Customer's email address

    Returns:
        dict: Account status and any issues
    """
    try:
        table = get_dynamodb_table()

        response = table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        items = response.get('Items', [])

        if not items:
            return {
                'success': False,
                'error': f'Account not found for {customer_email}'
            }

        account = items[0]
        status = account['account_status']

        result = {
            'success': True,
            'customer_email': customer_email,
            'account_status': status,
            'membership_tier': account['membership_tier']
        }

        if status == 'active':
            result['message'] = 'Account is active and in good standing.'
            result['can_place_orders'] = True
        elif status == 'suspended':
            result['message'] = f'Account is suspended. Reason: {account.get("suspension_reason", "Contact support")}'
            result['can_place_orders'] = False
            result['resolution'] = 'Please contact customer support to resolve this issue.'
        elif status == 'inactive':
            result['message'] = 'Account is inactive. Please log in to reactivate.'
            result['can_place_orders'] = False

        return result

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error checking account status for {customer_email}'
        }
