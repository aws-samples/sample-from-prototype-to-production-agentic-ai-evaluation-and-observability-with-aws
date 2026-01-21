"""
Product Tools Lambda Function for AgentCore Gateway MCP

This Lambda function exposes product-related tools via AgentCore Gateway.
Each tool is routed based on the bedrockagentcoreToolName in the context.
"""

import json
import os
import boto3
from decimal import Decimal


# Helper to convert Decimal to float for JSON serialization
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def get_products_table():
    """Get DynamoDB products table"""
    region = os.environ.get('AWS_REGION', 'us-west-2')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.environ.get('PRODUCTS_TABLE_NAME', 'ecommerce-workshop-products')
    return dynamodb.Table(table_name)


def search_products(query: str, category: str = None, max_results: int = 5) -> dict:
    """Search for products in the catalog using keywords."""
    try:
        table = get_products_table()
        query_lower = query.lower()

        # Scan table to get all products
        response = table.scan()
        items = response.get('Items', [])

        # Filter out system items
        items = [item for item in items if item.get('product_id') != 'POLICIES']

        # Filter by category if specified
        if category:
            items = [item for item in items if item.get('category', '').lower() == category.lower()]

        # Simple text matching on name and description
        matched_products = []
        for item in items:
            name = item.get('name', '').lower()
            description = item.get('description', '').lower()

            # Check if query terms are in name or description
            if any(term in name or term in description for term in query_lower.split()):
                matched_products.append(item)

        # Limit results
        matched_products = matched_products[:max_results]

        if not matched_products:
            return {
                'success': True,
                'query': query,
                'results': [],
                'message': f'No products found matching "{query}". Try different keywords.'
            }

        # Format results
        results = []
        for product in matched_products:
            results.append({
                'product_id': product.get('product_id'),
                'name': product.get('name'),
                'price': float(product.get('price', 0)),
                'category': product.get('category'),
                'in_stock': product.get('in_stock'),
                'rating': float(product.get('rating', 0)),
                'description': product.get('description', '')[:200]
            })

        return {
            'success': True,
            'query': query,
            'result_count': len(results),
            'results': results
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error searching for products: {query}'
        }


def get_product_details(product_id: str) -> dict:
    """Get detailed information about a specific product."""
    try:
        table = get_products_table()
        response = table.get_item(Key={'product_id': product_id})

        if 'Item' not in response:
            return {
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found.'
            }

        product = response['Item']

        return {
            'success': True,
            'product_id': product_id,
            'name': product.get('name'),
            'description': product.get('description'),
            'price': float(product.get('price', 0)),
            'category': product.get('category'),
            'in_stock': product.get('in_stock'),
            'stock_quantity': int(product.get('stock_quantity', 0)),
            'rating': float(product.get('rating', 0)),
            'features': product.get('features', []),
            'specifications': product.get('specifications', {}),
            'warranty': product.get('warranty', '1 year'),
            'return_policy': '30-day return policy'
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error getting product details for {product_id}'
        }


def check_inventory(product_id: str) -> dict:
    """Check inventory availability for a product."""
    try:
        table = get_products_table()
        response = table.get_item(Key={'product_id': product_id})

        if 'Item' not in response:
            return {
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found in inventory system.'
            }

        product = response['Item']
        in_stock = product.get('in_stock', False)
        quantity = product.get('stock_quantity', 0)

        result = {
            'success': True,
            'product_id': product_id,
            'product_name': product.get('name'),
            'in_stock': in_stock,
            'quantity_available': int(quantity) if quantity else 0
        }

        if not in_stock:
            result['restock_date'] = product.get('restock_date', 'Unknown')
            result['message'] = f'Product is currently out of stock. Expected restock date: {result["restock_date"]}'
        elif quantity < 10:
            result['message'] = 'Low stock - order soon!'
        else:
            result['message'] = 'In stock and ready to ship'

        return result

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Error checking inventory for {product_id}'
        }


def get_product_recommendations(category: str = None, price_max: float = None, limit: int = 5) -> dict:
    """Get product recommendations based on criteria."""
    try:
        table = get_products_table()

        # Scan table to get all products
        response = table.scan()
        items = response.get('Items', [])

        # Filter out system items
        items = [item for item in items if item.get('product_id') != 'POLICIES']

        # Filter by category
        if category:
            items = [item for item in items if item.get('category', '').lower() == category.lower()]

        # Filter by price
        if price_max:
            items = [item for item in items if float(item.get('price', 0)) <= price_max]

        # Filter in-stock only
        items = [item for item in items if item.get('in_stock', False)]

        # Sort by rating (descending)
        items.sort(key=lambda x: float(x.get('rating', 0)), reverse=True)

        # Limit results
        items = items[:limit]

        if not items:
            return {
                'success': True,
                'recommendations': [],
                'message': 'No products match your criteria.'
            }

        # Format recommendations
        recommendations = []
        for product in items:
            recommendations.append({
                'product_id': product.get('product_id'),
                'name': product.get('name'),
                'price': float(product.get('price', 0)),
                'category': product.get('category'),
                'rating': float(product.get('rating', 0)),
                'description': product.get('description', '')[:150]
            })

        return {
            'success': True,
            'recommendation_count': len(recommendations),
            'recommendations': recommendations
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Error getting product recommendations'
        }


def compare_products(product_ids: list) -> dict:
    """Compare multiple products side by side."""
    try:
        if len(product_ids) < 2:
            return {
                'success': False,
                'message': 'Please provide at least 2 product IDs to compare.'
            }

        if len(product_ids) > 5:
            return {
                'success': False,
                'message': 'Maximum 5 products can be compared at once.'
            }

        table = get_products_table()
        products = []

        for product_id in product_ids:
            response = table.get_item(Key={'product_id': product_id})
            if 'Item' in response:
                product = response['Item']
                products.append({
                    'product_id': product_id,
                    'name': product.get('name'),
                    'price': float(product.get('price', 0)),
                    'category': product.get('category'),
                    'rating': float(product.get('rating', 0)),
                    'in_stock': product.get('in_stock'),
                    'features': product.get('features', []),
                    'warranty': product.get('warranty', '1 year')
                })

        if len(products) < 2:
            return {
                'success': False,
                'message': 'Could not find enough products to compare.'
            }

        return {
            'success': True,
            'comparison_count': len(products),
            'products': products
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Error comparing products'
        }


def get_return_policy(product_id: str = None) -> dict:
    """Get return policy information."""
    try:
        # Default policy
        policy = {
            'success': True,
            'general_policy': {
                'return_window_days': 30,
                'condition': 'Items must be unused and in original packaging',
                'refund_method': 'Original payment method',
                'refund_timeline': '5-7 business days after receiving return'
            },
            'exceptions': [
                'Electronics: Must be factory sealed for full refund',
                'Clearance items: Final sale, no returns',
                'Personalized items: Non-returnable'
            ],
            'process': [
                'Initiate return request online or contact customer service',
                'Receive prepaid return shipping label via email',
                'Pack item securely in original packaging',
                'Drop off at carrier location',
                'Refund processed within 5-7 business days of receipt'
            ]
        }

        # Get product-specific policy if product_id provided
        if product_id:
            table = get_products_table()
            response = table.get_item(Key={'product_id': product_id})
            if 'Item' in response:
                product = response['Item']
                policy['product_specific'] = {
                    'product_id': product_id,
                    'product_name': product.get('name'),
                    'warranty': product.get('warranty', '1 year'),
                    'returnable': True
                }

        return policy

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Error getting return policy'
        }


# Tool routing map
TOOLS = {
    'search_products': search_products,
    'get_product_details': get_product_details,
    'check_inventory': check_inventory,
    'get_product_recommendations': get_product_recommendations,
    'compare_products': compare_products,
    'get_return_policy': get_return_policy
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

        # Strip target prefix if present (e.g., "ProductTools___search_products" -> "search_products")
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
