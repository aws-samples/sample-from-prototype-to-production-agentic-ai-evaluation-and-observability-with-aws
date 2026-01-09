"""
Order Management Tools for E-Commerce Customer Service Agent

These tools interact with DynamoDB to manage customer orders.
"""

import boto3
import os
from strands import tool
from datetime import datetime, timedelta
from typing import Optional
import json


# Initialize DynamoDB resource
def get_dynamodb_table():
    """Get DynamoDB table resource"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)

    # Get table name from SSM or environment
    table_name = os.environ.get('ORDERS_TABLE_NAME', 'ecommerce-workshop-orders')
    return dynamodb.Table(table_name)


@tool
def get_order_status(order_id: str) -> dict:
    """
    Get the current status and details of an order.

    Args:
        order_id: The order ID (e.g., ORD-2024-10001)

    Returns:
        dict: Order details including status, items, and shipping information
    """
    try:
        table = get_dynamodb_table()

        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {
                'success': False,
                'error': f'Order {order_id} not found',
                'message': f'No order found with ID {order_id}. Please verify the order number.'
            }

        order = response['Item']

        # Format response
        result = {
            'success': True,
            'order_id': order['order_id'],
            'status': order['status'],
            'order_date': order['order_date'],
            'customer_email': order.get('customer_email', 'N/A'),
            'items': order.get('items', []),
            'total': float(order.get('total', 0)),
            'shipping_address': order.get('shipping_address', {})
        }

        # Add status-specific information
        if order['status'] == 'shipped':
            result['shipping_carrier'] = order.get('shipping_carrier', 'N/A')
            result['tracking_number'] = order.get('tracking_number', 'N/A')
            result['estimated_delivery'] = order.get('estimated_delivery', 'N/A')
        elif order['status'] == 'delivered':
            result['delivery_date'] = order.get('delivery_date', 'N/A')
        elif order['status'] == 'return_requested':
            result['return_reason'] = order.get('return_reason', 'N/A')
            result['return_status'] = order.get('return_status', 'N/A')
        elif order['status'] == 'refunded':
            result['refund_amount'] = float(order.get('refund_amount', 0))
            result['refund_date'] = order.get('refund_date', 'N/A')

        return result

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error retrieving order {order_id}'
        }


@tool
def track_shipment(order_id: str) -> dict:
    """
    Get detailed tracking information for a shipped order.

    Args:
        order_id: The order ID to track

    Returns:
        dict: Tracking information including carrier, tracking number, and estimated delivery
    """
    try:
        table = get_dynamodb_table()

        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {
                'success': False,
                'error': f'Order {order_id} not found'
            }

        order = response['Item']
        status = order['status']

        if status not in ['shipped', 'delivered']:
            return {
                'success': False,
                'order_id': order_id,
                'status': status,
                'message': f'Order is currently in "{status}" status and not yet shipped.'
            }

        result = {
            'success': True,
            'order_id': order_id,
            'status': status,
            'shipping_carrier': order.get('shipping_carrier', 'N/A'),
            'tracking_number': order.get('tracking_number', 'N/A')
        }

        if status == 'shipped':
            result['estimated_delivery'] = order.get('estimated_delivery', 'N/A')
            result['tracking_url'] = _generate_tracking_url(
                order.get('shipping_carrier'),
                order.get('tracking_number')
            )
        elif status == 'delivered':
            result['delivery_date'] = order.get('delivery_date', 'N/A')
            result['message'] = 'Package has been delivered.'

        return result

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error tracking order {order_id}'
        }


def _generate_tracking_url(carrier: str, tracking_number: str) -> str:
    """Generate tracking URL based on carrier"""
    carrier_urls = {
        'FedEx': f'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
        'UPS': f'https://www.ups.com/track?tracknum={tracking_number}',
        'USPS': f'https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking_number}',
        'DHL': f'https://www.dhl.com/en/express/tracking.html?AWB={tracking_number}'
    }
    return carrier_urls.get(carrier, f'Tracking number: {tracking_number}')


@tool
def process_return(order_id: str, reason: str) -> dict:
    """
    Initiate a return request for an order.

    Args:
        order_id: The order ID to return
        reason: Reason for the return (e.g., "Item not as described", "Defective", "Wrong item")

    Returns:
        dict: Return request confirmation with instructions
    """
    try:
        table = get_dynamodb_table()

        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {
                'success': False,
                'error': f'Order {order_id} not found'
            }

        order = response['Item']

        # Check if return is allowed based on status and date
        if order['status'] not in ['delivered', 'shipped']:
            return {
                'success': False,
                'order_id': order_id,
                'message': f'Cannot process return. Order status is "{order["status"]}". Returns can only be initiated for delivered or shipped orders.'
            }

        # Check 30-day return window
        order_date = datetime.strptime(order['order_date'], '%Y-%m-%d')
        days_since_order = (datetime.now() - order_date).days

        if days_since_order > 30:
            return {
                'success': False,
                'order_id': order_id,
                'message': f'Return window has expired. Orders can only be returned within 30 days. This order was placed {days_since_order} days ago.'
            }

        # Update order status to return_requested
        table.update_item(
            Key={'order_id': order_id},
            UpdateExpression='SET #status = :status, return_reason = :reason, return_status = :rstatus, return_requested_date = :rdate',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'return_requested',
                ':reason': reason,
                ':rstatus': 'pending_approval',
                ':rdate': datetime.now().strftime('%Y-%m-%d')
            }
        )

        return {
            'success': True,
            'order_id': order_id,
            'return_status': 'pending_approval',
            'return_reason': reason,
            'message': f'Return request submitted for order {order_id}. You will receive an email with return shipping label within 24 hours.',
            'next_steps': [
                'Wait for return approval email with shipping label',
                'Pack items in original packaging if possible',
                'Drop off at designated carrier location',
                'Refund will be processed within 5-7 business days after we receive the return'
            ]
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error processing return for order {order_id}'
        }


@tool
def modify_order(order_id: str, modification_type: str, new_value: str) -> dict:
    """
    Modify an existing order (shipping address, cancel order).

    Args:
        order_id: The order ID to modify
        modification_type: Type of modification - "shipping_address" or "cancel"
        new_value: For shipping_address: new address as JSON string. For cancel: reason for cancellation.

    Returns:
        dict: Modification confirmation
    """
    try:
        table = get_dynamodb_table()

        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {
                'success': False,
                'error': f'Order {order_id} not found'
            }

        order = response['Item']

        # Only pending or processing orders can be modified
        if order['status'] not in ['pending', 'processing']:
            return {
                'success': False,
                'order_id': order_id,
                'message': f'Cannot modify order. Order status is "{order["status"]}". Only pending or processing orders can be modified.'
            }

        if modification_type == 'cancel':
            table.update_item(
                Key={'order_id': order_id},
                UpdateExpression='SET #status = :status, cancellation_reason = :reason, cancellation_date = :cdate',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'cancelled',
                    ':reason': new_value,
                    ':cdate': datetime.now().strftime('%Y-%m-%d')
                }
            )
            return {
                'success': True,
                'order_id': order_id,
                'modification': 'cancelled',
                'message': f'Order {order_id} has been cancelled. Refund will be processed within 3-5 business days.'
            }

        elif modification_type == 'shipping_address':
            try:
                new_address = json.loads(new_value) if isinstance(new_value, str) else new_value
            except json.JSONDecodeError:
                return {
                    'success': False,
                    'error': 'Invalid address format. Please provide address as JSON.'
                }

            table.update_item(
                Key={'order_id': order_id},
                UpdateExpression='SET shipping_address = :addr',
                ExpressionAttributeValues={':addr': new_address}
            )
            return {
                'success': True,
                'order_id': order_id,
                'modification': 'shipping_address_updated',
                'new_address': new_address,
                'message': f'Shipping address for order {order_id} has been updated.'
            }

        else:
            return {
                'success': False,
                'error': f'Unknown modification type: {modification_type}. Supported types: "shipping_address", "cancel"'
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error modifying order {order_id}'
        }


@tool
def get_customer_orders(customer_email: str, limit: int = 5) -> dict:
    """
    Get recent orders for a customer by their email.

    Args:
        customer_email: Customer's email address
        limit: Maximum number of orders to return (default 5)

    Returns:
        dict: List of customer's recent orders
    """
    try:
        table = get_dynamodb_table()

        # Scan with filter (in production, use GSI for email)
        response = table.scan(
            FilterExpression='customer_email = :email',
            ExpressionAttributeValues={':email': customer_email}
        )

        orders = response.get('Items', [])

        if not orders:
            return {
                'success': True,
                'customer_email': customer_email,
                'orders': [],
                'message': f'No orders found for {customer_email}'
            }

        # Sort by order_date descending and limit
        orders.sort(key=lambda x: x.get('order_date', ''), reverse=True)
        orders = orders[:limit]

        # Format orders
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                'order_id': order['order_id'],
                'order_date': order['order_date'],
                'status': order['status'],
                'total': float(order.get('total', 0)),
                'items_count': len(order.get('items', []))
            })

        return {
            'success': True,
            'customer_email': customer_email,
            'order_count': len(formatted_orders),
            'orders': formatted_orders
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error retrieving orders for {customer_email}'
        }
