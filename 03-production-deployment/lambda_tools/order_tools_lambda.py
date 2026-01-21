"""
Order Tools Lambda Function for AgentCore Gateway MCP

This Lambda function exposes order-related tools via AgentCore Gateway.
Each tool is routed based on the bedrockagentcoreToolName in the context.
"""

import json
import os
import boto3
from datetime import datetime
from decimal import Decimal


# Helper to convert Decimal to float for JSON serialization
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def get_orders_table():
    """Get DynamoDB orders table"""
    region = os.environ.get('AWS_REGION', 'us-west-2')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('ORDERS_TABLE_NAME', 'ecommerce-workshop-orders')
    return dynamodb.Table(table_name)


def get_order_status(order_id: str) -> dict:
    """Get the current status and details of an order."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']
        result = {
            'success': True,
            'order_id': order['order_id'],
            'status': order['status'],
            'order_date': order['order_date'],
            'items': order.get('items', []),
            'total': float(order.get('total', 0)),
            'shipping_address': order.get('shipping_address', {})
        }

        if order['status'] == 'shipped':
            result['tracking_number'] = order.get('tracking_number', 'N/A')
            result['shipping_carrier'] = order.get('shipping_carrier', 'N/A')
            result['estimated_delivery'] = order.get('estimated_delivery', 'N/A')

        return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


def track_shipment(order_id: str) -> dict:
    """Get tracking information for a shipped order."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']
        if order['status'] not in ['shipped', 'delivered']:
            return {'success': False, 'message': f'Order is in "{order["status"]}" status, not yet shipped'}

        carrier = order.get('shipping_carrier', 'N/A')
        tracking_number = order.get('tracking_number', 'N/A')

        # Generate tracking URL based on carrier
        tracking_urls = {
            'UPS': f'https://www.ups.com/track?tracknum={tracking_number}',
            'DHL': f'https://www.dhl.com/en/express/tracking.html?AWB={tracking_number}',
            'FedEx': f'https://www.fedex.com/fedextrack/?trknbr={tracking_number}'
        }

        return {
            'success': True,
            'order_id': order_id,
            'status': order['status'],
            'carrier': carrier,
            'tracking_number': tracking_number,
            'tracking_url': tracking_urls.get(carrier, 'N/A'),
            'estimated_delivery': order.get('estimated_delivery', order.get('delivery_date', 'N/A'))
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def process_return(order_id: str, reason: str) -> dict:
    """Initiate a return request for an order."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']

        # Check if order is in returnable status
        if order['status'] not in ['delivered', 'shipped']:
            return {'success': False, 'message': f'Cannot return order in "{order["status"]}" status'}

        # Check return window (30 days)
        order_date = datetime.strptime(order['order_date'], '%Y-%m-%d')
        days_since_order = (datetime.now() - order_date).days

        if days_since_order > 30:
            return {
                'success': False,
                'message': f'Return window expired. Order was placed {days_since_order} days ago. Our return policy allows returns within 30 days.'
            }

        # Process return
        table.update_item(
            Key={'order_id': order_id},
            UpdateExpression='SET #status = :status, return_reason = :reason, return_requested_date = :date',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'return_requested',
                ':reason': reason,
                ':date': datetime.now().isoformat()
            }
        )

        return {
            'success': True,
            'order_id': order_id,
            'return_status': 'return_requested',
            'message': 'Return request submitted successfully. You will receive a return shipping label via email within 24 hours.'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def modify_order(order_id: str, modification_type: str, new_value: str) -> dict:
    """Modify an order (shipping address, cancel, etc.)."""
    try:
        table = get_orders_table()
        response = table.get_item(Key={'order_id': order_id})

        if 'Item' not in response:
            return {'success': False, 'error': f'Order {order_id} not found'}

        order = response['Item']

        # Only pending/processing orders can be modified
        if order['status'] not in ['pending', 'processing']:
            return {
                'success': False,
                'message': f'Cannot modify order in "{order["status"]}" status. Only pending or processing orders can be modified.'
            }

        if modification_type == 'cancel':
            table.update_item(
                Key={'order_id': order_id},
                UpdateExpression='SET #status = :status, cancelled_date = :date',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'cancelled',
                    ':date': datetime.now().isoformat()
                }
            )
            return {
                'success': True,
                'order_id': order_id,
                'message': 'Order cancelled successfully. Any charges will be refunded within 5-7 business days.'
            }

        elif modification_type == 'shipping_address':
            table.update_item(
                Key={'order_id': order_id},
                UpdateExpression='SET shipping_address = :addr',
                ExpressionAttributeValues={':addr': new_value}
            )
            return {
                'success': True,
                'order_id': order_id,
                'message': f'Shipping address updated successfully to: {new_value}'
            }

        else:
            return {'success': False, 'error': f'Unknown modification type: {modification_type}'}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_customer_orders(customer_email: str, limit: int = 10) -> dict:
    """Get order history for a customer."""
    try:
        table = get_orders_table()

        # Scan for orders by customer email
        response = table.scan(
            FilterExpression='customer_email = :email',
            ExpressionAttributeValues={':email': customer_email},
            Limit=limit
        )

        orders = response.get('Items', [])

        if not orders:
            return {
                'success': True,
                'customer_email': customer_email,
                'orders': [],
                'message': 'No orders found for this customer.'
            }

        # Format orders
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                'order_id': order['order_id'],
                'order_date': order['order_date'],
                'status': order['status'],
                'total': float(order.get('total', 0)),
                'item_count': len(order.get('items', []))
            })

        # Sort by date descending
        formatted_orders.sort(key=lambda x: x['order_date'], reverse=True)

        return {
            'success': True,
            'customer_email': customer_email,
            'order_count': len(formatted_orders),
            'orders': formatted_orders[:limit]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# Tool routing map
TOOLS = {
    'get_order_status': get_order_status,
    'track_shipment': track_shipment,
    'process_return': process_return,
    'modify_order': modify_order,
    'get_customer_orders': get_customer_orders
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

        # Strip target prefix if present (e.g., "OrderTools___get_order_status" -> "get_order_status")
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
