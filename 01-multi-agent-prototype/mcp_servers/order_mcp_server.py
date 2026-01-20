"""
Order Management MCP Server for E-Commerce Customer Service

Provides MCP tools for order-related operations:
- get_order_status
- track_shipment
- process_return
- modify_order
- get_customer_orders

Run with: python order_mcp_server.py
Or: uvx mcp run order_mcp_server.py
"""

import os
import json
import boto3
from datetime import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("order-service")


# Initialize DynamoDB resource
def get_dynamodb_table():
    """Get DynamoDB table resource"""
    region = os.environ.get('AWS_REGION', 'us-west-2')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('ORDERS_TABLE_NAME', 'ecommerce-workshop-orders')
    return dynamodb.Table(table_name)


def _generate_tracking_url(carrier: str, tracking_number: str) -> str:
    """Generate tracking URL based on carrier"""
    carrier_urls = {
        'FedEx': f'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
        'UPS': f'https://www.ups.com/track?tracknum={tracking_number}',
        'USPS': f'https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking_number}',
        'DHL': f'https://www.dhl.com/en/express/tracking.html?AWB={tracking_number}'
    }
    return carrier_urls.get(carrier, f'Tracking number: {tracking_number}')


@mcp.tool()
def get_order_status(order_id: str) -> str:
    """
    Get the current status and details of an order.

    Args:
        order_id: The order ID (e.g., ORD-2024-10001)

    Returns:
        Order details including status, items, and shipping information as JSON string
    """
    try:
        table = get_dynamodb_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return json.dumps({
                'success': False,
                'error': f'Order {order_id} not found',
                'message': f'No order found with ID {order_id}. Please verify the order number.'
            })

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

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error retrieving order {order_id}'
        })


@mcp.tool()
def track_shipment(order_id: str) -> str:
    """
    Get detailed tracking information for a shipped order.

    Args:
        order_id: The order ID to track

    Returns:
        Tracking information including carrier, tracking number, and estimated delivery as JSON string
    """
    try:
        table = get_dynamodb_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return json.dumps({
                'success': False,
                'error': f'Order {order_id} not found'
            })

        order = response['Item']
        status = order['status']

        if status not in ['shipped', 'delivered']:
            return json.dumps({
                'success': False,
                'order_id': order_id,
                'status': status,
                'message': f'Order is currently in "{status}" status and not yet shipped.'
            })

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

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error tracking order {order_id}'
        })


@mcp.tool()
def process_return(order_id: str, reason: str) -> str:
    """
    Initiate a return request for an order.

    Args:
        order_id: The order ID to return
        reason: Reason for the return (e.g., "Item not as described", "Defective", "Wrong item")

    Returns:
        Return request confirmation with instructions as JSON string
    """
    try:
        table = get_dynamodb_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return json.dumps({
                'success': False,
                'error': f'Order {order_id} not found'
            })

        order = response['Item']

        # Check if return is allowed based on status and date
        if order['status'] not in ['delivered', 'shipped']:
            return json.dumps({
                'success': False,
                'order_id': order_id,
                'message': f'Cannot process return. Order status is "{order["status"]}". Returns can only be initiated for delivered or shipped orders.'
            })

        # Check 30-day return window
        order_date = datetime.strptime(order['order_date'], '%Y-%m-%d')
        days_since_order = (datetime.now() - order_date).days

        if days_since_order > 30:
            return json.dumps({
                'success': False,
                'order_id': order_id,
                'message': f'Return window has expired. Orders can only be returned within 30 days. This order was placed {days_since_order} days ago.'
            })

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

        return json.dumps({
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
        })

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error processing return for order {order_id}'
        })


@mcp.tool()
def modify_order(order_id: str, modification_type: str, new_value: str) -> str:
    """
    Modify an existing order (shipping address, cancel order).

    Args:
        order_id: The order ID to modify
        modification_type: Type of modification - "shipping_address" or "cancel"
        new_value: For shipping_address: new address as JSON string. For cancel: reason for cancellation.

    Returns:
        Modification confirmation as JSON string
    """
    try:
        table = get_dynamodb_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return json.dumps({
                'success': False,
                'error': f'Order {order_id} not found'
            })

        order = response['Item']

        # Only pending or processing orders can be modified
        if order['status'] not in ['pending', 'processing']:
            return json.dumps({
                'success': False,
                'order_id': order_id,
                'message': f'Cannot modify order. Order status is "{order["status"]}". Only pending or processing orders can be modified.'
            })

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
            return json.dumps({
                'success': True,
                'order_id': order_id,
                'modification': 'cancelled',
                'message': f'Order {order_id} has been cancelled. Refund will be processed within 3-5 business days.'
            })

        elif modification_type == 'shipping_address':
            try:
                new_address = json.loads(new_value) if isinstance(new_value, str) else new_value
            except json.JSONDecodeError:
                return json.dumps({
                    'success': False,
                    'error': 'Invalid address format. Please provide address as JSON.'
                })

            table.update_item(
                Key={'order_id': order_id},
                UpdateExpression='SET shipping_address = :addr',
                ExpressionAttributeValues={':addr': new_address}
            )
            return json.dumps({
                'success': True,
                'order_id': order_id,
                'modification': 'shipping_address_updated',
                'new_address': new_address,
                'message': f'Shipping address for order {order_id} has been updated.'
            })

        else:
            return json.dumps({
                'success': False,
                'error': f'Unknown modification type: {modification_type}. Supported types: "shipping_address", "cancel"'
            })

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error modifying order {order_id}'
        })


@mcp.tool()
def get_customer_orders(customer_email: str, limit: int = 5) -> str:
    """
    Get recent orders for a customer by their email.

    Args:
        customer_email: Customer's email address
        limit: Maximum number of orders to return (default 5)

    Returns:
        List of customer's recent orders as JSON string
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
            return json.dumps({
                'success': True,
                'customer_email': customer_email,
                'orders': [],
                'message': f'No orders found for {customer_email}'
            })

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

        return json.dumps({
            'success': True,
            'customer_email': customer_email,
            'order_count': len(formatted_orders),
            'orders': formatted_orders
        }, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error retrieving orders for {customer_email}'
        })


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
