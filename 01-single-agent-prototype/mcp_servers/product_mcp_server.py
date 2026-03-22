"""
Product Catalog MCP Server for E-Commerce Agent Workshop

Provides MCP tools for product-related operations organized by access level:

READ tools (available to all roles):
- search_products
- get_product_details
- check_inventory
- get_product_recommendations
- compare_products
- get_return_policy

ADMIN tools (restricted to admin role):
- create_product
- update_product
- delete_product
- update_inventory
- update_pricing

Run with: python product_mcp_server.py
Or: uvx mcp run product_mcp_server.py
"""

import os
import json
import boto3
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("product-service")


def get_dynamodb_table(table_name_suffix: str):
    """Get DynamoDB table resource"""
    region = os.environ.get('AWS_REGION', 'us-west-2')
    dynamodb = boto3.resource('dynamodb', region_name=region)

    # Try environment variable first
    table_name = os.environ.get(f'{table_name_suffix.upper()}_TABLE')
    if table_name:
        return dynamodb.Table(table_name)

    # Try SSM parameter
    try:
        ssm = boto3.client('ssm', region_name=region)
        response = ssm.get_parameter(Name=f'ecommerce-workshop-{table_name_suffix}-table')
        return dynamodb.Table(response['Parameter']['Value'])
    except Exception:
        # Fallback to default name
        return dynamodb.Table(f'ecommerce-workshop-{table_name_suffix}')


def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


def format_product(product: dict) -> str:
    """Format product data as readable text"""
    specs = product.get('specifications', '{}')
    if isinstance(specs, str):
        try:
            specs = json.loads(specs)
        except:
            specs = {}

    specs_text = '\n'.join([f"  - {k}: {v}" for k, v in specs.items()])

    return f"""Product: {product.get('name', 'Unknown')}
Product ID: {product.get('product_id', 'Unknown')}
Category: {product.get('category', 'Unknown')}
Price: ${product.get('price', 0)}

Description:
{product.get('description', 'No description available')}

Specifications:
{specs_text if specs_text else '  No specifications available'}

Availability: {'In Stock' if product.get('in_stock') else 'Out of Stock'}
Stock Quantity: {product.get('stock_quantity', 0)}
{f"Restock Date: {product.get('restock_date')}" if product.get('restock_date') else ''}

Rating: {product.get('rating', 'N/A')} out of 5

Warranty: {product.get('warranty', 'Standard warranty')}
Return Policy: {product.get('return_policy', 'Standard 30-day return policy')}
"""


@mcp.tool()
def search_products(query: str, category: Optional[str] = None, max_results: int = 5) -> str:
    """
    Search for products in the catalog using natural language query.

    Args:
        query: Natural language search query (e.g., "wireless headphones with noise cancellation")
        category: Optional category filter (e.g., "Audio", "Wearables", "Gaming")
        max_results: Maximum number of results to return (default 5)

    Returns:
        Search results with matching products and their details as JSON string
    """
    try:
        table = get_dynamodb_table('products')
        query_lower = query.lower()

        # Scan table with filters
        if category:
            response = table.query(
                IndexName='category-index',
                KeyConditionExpression=Key('category').eq(category)
            )
        else:
            response = table.scan()

        items = response.get('Items', [])

        # Filter out system items
        items = [item for item in items if item.get('product_id') != 'POLICIES']

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
            return json.dumps({
                'success': True,
                'query': query,
                'results': [],
                'message': f'No products found matching "{query}". Try different keywords or browse our categories.'
            })

        # Format results
        results = []
        for product in matched_products:
            results.append({
                'product_id': product.get('product_id'),
                'name': product.get('name'),
                'price': decimal_to_float(product.get('price')),
                'category': product.get('category'),
                'in_stock': product.get('in_stock'),
                'description': product.get('description', '')[:200] + '...' if len(product.get('description', '')) > 200 else product.get('description', '')
            })

        return json.dumps({
            'success': True,
            'query': query,
            'category_filter': category,
            'result_count': len(results),
            'results': results
        }, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error searching for products: {query}'
        })


@mcp.tool()
def get_product_details(product_id: str) -> str:
    """
    Get detailed information about a specific product.

    Args:
        product_id: Product ID (e.g., PROD-001)

    Returns:
        Detailed product information including specs, price, availability as JSON string
    """
    try:
        table = get_dynamodb_table('products')
        response = table.get_item(Key={'product_id': product_id})

        if 'Item' not in response:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found in catalog.'
            })

        product = response['Item']

        # Format product details as text
        details = format_product(product)

        return json.dumps({
            'success': True,
            'product_id': product_id,
            'details': details,
            'product_data': decimal_to_float(product),
            'source': 'product_catalog'
        }, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error retrieving product {product_id}'
        })


@mcp.tool()
def check_inventory(product_id: str) -> str:
    """
    Check inventory availability for a product.

    Args:
        product_id: Product ID to check

    Returns:
        Inventory status including stock level and restock date if applicable as JSON string
    """
    try:
        table = get_dynamodb_table('products')
        response = table.get_item(Key={'product_id': product_id})

        if 'Item' not in response:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found in inventory system.'
            })

        product = response['Item']
        in_stock = product.get('in_stock', False)
        quantity = product.get('stock_quantity', 0)

        result = {
            'success': True,
            'product_id': product_id,
            'in_stock': in_stock,
            'quantity_available': decimal_to_float(quantity)
        }

        if not in_stock:
            result['restock_date'] = product.get('restock_date', 'Unknown')
            result['message'] = f'Product is currently out of stock. Expected restock date: {result["restock_date"]}'
        elif quantity < 10:
            result['message'] = 'Low stock - order soon!'
        else:
            result['message'] = 'In stock and ready to ship'

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error checking inventory for {product_id}'
        })


@mcp.tool()
def get_product_recommendations(context: str, max_recommendations: int = 3) -> str:
    """
    Get product recommendations based on user context or previous purchases.

    Args:
        context: Context for recommendations (e.g., "customer bought wireless headphones", "looking for gaming accessories")
        max_recommendations: Maximum number of recommendations (default 3)

    Returns:
        List of recommended products with reasons as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Simple recommendation logic based on context keywords
        context_lower = context.lower()

        # Determine likely categories from context
        category_keywords = {
            'audio': ['headphones', 'speaker', 'earbuds', 'audio'],
            'wearables': ['watch', 'smartwatch', 'fitness', 'tracker'],
            'gaming': ['gaming', 'keyboard', 'mouse', 'game'],
            'monitors': ['monitor', 'display', 'screen'],
            'accessories': ['cable', 'hub', 'stand', 'accessory'],
            'cameras': ['camera', 'webcam', 'video']
        }

        # Find matching category
        target_category = None
        for cat, keywords in category_keywords.items():
            if any(kw in context_lower for kw in keywords):
                target_category = cat.title()
                break

        # Query products
        if target_category:
            response = table.query(
                IndexName='category-index',
                KeyConditionExpression=Key('category').eq(target_category),
                Limit=max_recommendations + 2
            )
        else:
            response = table.scan(Limit=max_recommendations + 2)

        items = response.get('Items', [])

        # Filter out system items and limit results
        items = [item for item in items if item.get('product_id') != 'POLICIES'][:max_recommendations]

        if not items:
            return json.dumps({
                'success': True,
                'context': context,
                'recommendations': [],
                'message': 'No specific recommendations available. Browse our popular categories!'
            })

        recommendations = []
        for product in items:
            recommendations.append({
                'product_id': product.get('product_id'),
                'name': product.get('name'),
                'price': decimal_to_float(product.get('price')),
                'category': product.get('category'),
                'description': product.get('description', '')[:150] + '...' if len(product.get('description', '')) > 150 else product.get('description', '')
            })

        return json.dumps({
            'success': True,
            'context': context,
            'recommendation_count': len(recommendations),
            'recommendations': recommendations
        }, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error generating recommendations'
        })


@mcp.tool()
def compare_products(product_ids: str) -> str:
    """
    Compare multiple products side by side.

    Args:
        product_ids: Comma-separated list of product IDs to compare (e.g., "PROD-001,PROD-055")

    Returns:
        Comparison table with features and specifications as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Parse product IDs from comma-separated string
        product_id_list = [pid.strip() for pid in product_ids.split(',')]
        comparisons = []

        for product_id in product_id_list:
            response = table.get_item(Key={'product_id': product_id})

            if 'Item' in response:
                product = response['Item']
                comparisons.append({
                    'product_id': product_id,
                    'name': product.get('name'),
                    'price': decimal_to_float(product.get('price')),
                    'category': product.get('category'),
                    'rating': decimal_to_float(product.get('rating')),
                    'in_stock': product.get('in_stock'),
                    'specifications': json.loads(product.get('specifications', '{}')) if isinstance(product.get('specifications'), str) else product.get('specifications', {}),
                    'warranty': product.get('warranty'),
                    'description': product.get('description')
                })
            else:
                comparisons.append({
                    'product_id': product_id,
                    'error': 'Product not found'
                })

        return json.dumps({
            'success': True,
            'products_compared': len(comparisons),
            'comparison': decimal_to_float(comparisons)
        }, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': 'Error comparing products'
        })


@mcp.tool()
def get_return_policy(product_id: Optional[str] = None) -> str:
    """
    Get return policy information, optionally for a specific product.

    Args:
        product_id: Optional product ID for product-specific return policy

    Returns:
        Return policy details as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Get policies from POLICIES item
        response = table.get_item(Key={'product_id': 'POLICIES'})

        if 'Item' in response:
            policies = json.loads(response['Item'].get('policies', '{}'))
            policy_text = policies.get('general_return_policy', '')

            if product_id:
                # Also get product-specific policy
                prod_response = table.get_item(Key={'product_id': product_id})
                if 'Item' in prod_response:
                    product = prod_response['Item']
                    product_policy = product.get('return_policy', '')
                    policy_text = f"{product_policy}\n\nGeneral Policy:\n{policy_text}"

            return json.dumps({
                'success': True,
                'product_id': product_id,
                'policy': policy_text,
                'all_policies': policies
            })
        else:
            # Default policy
            return json.dumps({
                'success': True,
                'product_id': product_id,
                'policy': '''Standard Return Policy:
- 45-day return window from delivery date (updated January 2025)
- Items must be in original condition with packaging
- Free returns for defective items
- Customer pays return shipping for non-defective returns
- Refund processed within 5-7 business days after receipt

Membership tiers have extended return windows:
- Standard/Gold: 45 days
- Platinum: 60 days'''
            })

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': 'Error retrieving return policy'
        })


# =============================================================================
# ADMIN TOOLS - These tools modify the product catalog.
# In production, access is restricted to admin roles via RBAC.
# =============================================================================


@mcp.tool()
def create_product(
    product_id: str,
    name: str,
    category: str,
    price: float,
    description: str,
    specifications: str,
    stock_quantity: int = 0,
    warranty: str = "1 year manufacturer warranty",
    return_policy: str = "30-day return policy"
) -> str:
    """
    Create a new product in the catalog. Requires admin privileges.

    Args:
        product_id: Unique product ID (e.g., PROD-200)
        name: Product name
        category: Product category (e.g., Audio, Wearables, Gaming, Monitors, Accessories, Cameras, Furniture)
        price: Product price in USD
        description: Product description
        specifications: Product specifications as JSON string (e.g., '{"weight": "250g", "color": "black"}')
        stock_quantity: Initial stock quantity (default 0)
        warranty: Warranty information (default "1 year manufacturer warranty")
        return_policy: Return policy (default "30-day return policy")

    Returns:
        Confirmation of product creation as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Check if product already exists
        existing = table.get_item(Key={'product_id': product_id})
        if 'Item' in existing:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} already exists. Use update_product to modify it.'
            })

        # Parse specifications
        try:
            specs = json.loads(specifications) if isinstance(specifications, str) else specifications
        except json.JSONDecodeError:
            return json.dumps({
                'success': False,
                'error': 'Invalid specifications format. Please provide valid JSON.'
            })

        # Create product item
        item = {
            'product_id': product_id,
            'name': name,
            'category': category,
            'price': Decimal(str(price)),
            'description': description,
            'specifications': specs,
            'in_stock': stock_quantity > 0,
            'stock_quantity': stock_quantity,
            'rating': Decimal('0'),
            'warranty': warranty,
            'return_policy': return_policy,
            'created_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        table.put_item(Item=item)

        return json.dumps({
            'success': True,
            'product_id': product_id,
            'name': name,
            'category': category,
            'price': price,
            'stock_quantity': stock_quantity,
            'message': f'Product {product_id} ({name}) created successfully.'
        })

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error creating product {product_id}'
        })


@mcp.tool()
def update_product(product_id: str, updates: str) -> str:
    """
    Update an existing product's information. Requires admin privileges.

    Args:
        product_id: Product ID to update (e.g., PROD-001)
        updates: JSON string with fields to update (e.g., '{"name": "New Name", "description": "New desc", "price": 99.99}')
                 Supported fields: name, description, price, category, specifications, warranty, return_policy, rating

    Returns:
        Confirmation of update with changed fields as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Check product exists
        existing = table.get_item(Key={'product_id': product_id})
        if 'Item' not in existing:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found.'
            })

        # Parse updates
        try:
            update_dict = json.loads(updates) if isinstance(updates, str) else updates
        except json.JSONDecodeError:
            return json.dumps({
                'success': False,
                'error': 'Invalid updates format. Please provide valid JSON.'
            })

        # Allowed fields for update
        allowed_fields = {'name', 'description', 'price', 'category', 'specifications',
                          'warranty', 'return_policy', 'rating'}
        invalid_fields = set(update_dict.keys()) - allowed_fields
        if invalid_fields:
            return json.dumps({
                'success': False,
                'error': f'Cannot update fields: {", ".join(invalid_fields)}. Allowed: {", ".join(allowed_fields)}'
            })

        if not update_dict:
            return json.dumps({
                'success': False,
                'error': 'No update fields provided.'
            })

        # Build update expression
        update_parts = []
        expr_names = {}
        expr_values = {':updated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        for field, value in update_dict.items():
            safe_name = f'#{field}'
            safe_value = f':{field}'
            update_parts.append(f'{safe_name} = {safe_value}')
            expr_names[safe_name] = field

            if field == 'price':
                expr_values[safe_value] = Decimal(str(value))
            elif field == 'rating':
                expr_values[safe_value] = Decimal(str(value))
            elif field == 'specifications' and isinstance(value, str):
                expr_values[safe_value] = json.loads(value)
            else:
                expr_values[safe_value] = value

        update_parts.append('#updated_date = :updated_date')
        expr_names['#updated_date'] = 'updated_date'

        update_expression = 'SET ' + ', '.join(update_parts)

        table.update_item(
            Key={'product_id': product_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )

        return json.dumps({
            'success': True,
            'product_id': product_id,
            'updated_fields': list(update_dict.keys()),
            'message': f'Product {product_id} updated successfully. Fields changed: {", ".join(update_dict.keys())}'
        })

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error updating product {product_id}'
        })


@mcp.tool()
def delete_product(product_id: str) -> str:
    """
    Delete a product from the catalog. Requires admin privileges.

    This performs a soft delete by setting the product status to 'discontinued'
    and removing it from active inventory. The product record is retained for
    order history purposes.

    Args:
        product_id: Product ID to delete (e.g., PROD-001)

    Returns:
        Confirmation of deletion as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Check product exists
        existing = table.get_item(Key={'product_id': product_id})
        if 'Item' not in existing:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found.'
            })

        product_name = existing['Item'].get('name', 'Unknown')

        # Soft delete: mark as discontinued and zero out inventory
        table.update_item(
            Key={'product_id': product_id},
            UpdateExpression='SET #status = :status, in_stock = :in_stock, stock_quantity = :qty, discontinued_date = :ddate, updated_date = :udate',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'discontinued',
                ':in_stock': False,
                ':qty': 0,
                ':ddate': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ':udate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        )

        return json.dumps({
            'success': True,
            'product_id': product_id,
            'name': product_name,
            'action': 'soft_delete',
            'message': f'Product {product_id} ({product_name}) has been discontinued and removed from active catalog.'
        })

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error deleting product {product_id}'
        })


@mcp.tool()
def update_inventory(product_id: str, new_quantity: int, restock_date: Optional[str] = None) -> str:
    """
    Update inventory levels for a product. Requires admin privileges.

    Args:
        product_id: Product ID to update (e.g., PROD-001)
        new_quantity: New stock quantity
        restock_date: Optional expected restock date for out-of-stock items (format: YYYY-MM-DD)

    Returns:
        Updated inventory status as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Check product exists
        existing = table.get_item(Key={'product_id': product_id})
        if 'Item' not in existing:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found.'
            })

        if new_quantity < 0:
            return json.dumps({
                'success': False,
                'error': 'Stock quantity cannot be negative.'
            })

        in_stock = new_quantity > 0

        update_expr = 'SET stock_quantity = :qty, in_stock = :in_stock, updated_date = :udate'
        expr_values = {
            ':qty': new_quantity,
            ':in_stock': in_stock,
            ':udate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        if restock_date:
            update_expr += ', restock_date = :rdate'
            expr_values[':rdate'] = restock_date
        elif in_stock:
            # Remove restock_date if item is back in stock
            update_expr += ' REMOVE restock_date'

        table.update_item(
            Key={'product_id': product_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )

        result = {
            'success': True,
            'product_id': product_id,
            'name': existing['Item'].get('name'),
            'new_quantity': new_quantity,
            'in_stock': in_stock,
            'message': f'Inventory updated for {product_id}. New quantity: {new_quantity}.'
        }

        if restock_date and not in_stock:
            result['restock_date'] = restock_date
            result['message'] += f' Expected restock: {restock_date}.'

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error updating inventory for {product_id}'
        })


@mcp.tool()
def update_pricing(product_id: str, new_price: float, sale_price: Optional[float] = None, sale_end_date: Optional[str] = None) -> str:
    """
    Update pricing for a product, optionally setting a sale price. Requires admin privileges.

    Args:
        product_id: Product ID to update (e.g., PROD-001)
        new_price: New regular price in USD
        sale_price: Optional temporary sale price in USD
        sale_end_date: Optional sale end date (format: YYYY-MM-DD), required if sale_price is set

    Returns:
        Updated pricing information as JSON string
    """
    try:
        table = get_dynamodb_table('products')

        # Check product exists
        existing = table.get_item(Key={'product_id': product_id})
        if 'Item' not in existing:
            return json.dumps({
                'success': False,
                'product_id': product_id,
                'message': f'Product {product_id} not found.'
            })

        if new_price <= 0:
            return json.dumps({
                'success': False,
                'error': 'Price must be greater than zero.'
            })

        if sale_price is not None and sale_price >= new_price:
            return json.dumps({
                'success': False,
                'error': f'Sale price (${sale_price}) must be less than regular price (${new_price}).'
            })

        old_price = float(existing['Item'].get('price', 0))

        update_expr = 'SET price = :price, updated_date = :udate'
        expr_values = {
            ':price': Decimal(str(new_price)),
            ':udate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        if sale_price is not None:
            if not sale_end_date:
                return json.dumps({
                    'success': False,
                    'error': 'sale_end_date is required when setting a sale_price.'
                })
            update_expr += ', sale_price = :sprice, sale_end_date = :sdate'
            expr_values[':sprice'] = Decimal(str(sale_price))
            expr_values[':sdate'] = sale_end_date

        table.update_item(
            Key={'product_id': product_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )

        result = {
            'success': True,
            'product_id': product_id,
            'name': existing['Item'].get('name'),
            'old_price': old_price,
            'new_price': new_price,
            'message': f'Price updated for {product_id}. ${old_price} -> ${new_price}.'
        }

        if sale_price is not None:
            result['sale_price'] = sale_price
            result['sale_end_date'] = sale_end_date
            discount_pct = round((1 - sale_price / new_price) * 100, 1)
            result['message'] += f' Sale price: ${sale_price} ({discount_pct}% off) until {sale_end_date}.'

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e),
            'message': f'Error updating pricing for {product_id}'
        })


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
