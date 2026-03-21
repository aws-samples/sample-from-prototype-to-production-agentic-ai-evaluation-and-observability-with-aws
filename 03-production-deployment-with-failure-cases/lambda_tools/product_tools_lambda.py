"""
Product Tools Lambda Function for AgentCore Gateway MCP

Exposes 11 product tools via AgentCore Gateway:
  READ tools (customer + admin): search, details, inventory, recommendations, compare, return policy
  WRITE tools (admin only): create, update, delete, update inventory, update pricing

Each tool is routed based on the bedrockAgentCoreToolName in the Lambda context.
RBAC enforcement happens at the Gateway interceptor level, not here.
"""

import json
import logging
import os
from datetime import datetime
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def decimal_default(obj):
    """JSON serializer for DynamoDB Decimal types."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def get_products_table():
    """Get DynamoDB products table resource."""
    region = os.environ.get("AWS_REGION", "us-west-2")
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table_name = os.environ.get("PRODUCTS_TABLE_NAME", "ecommerce-workshop-products")
    return dynamodb.Table(table_name)


# ===========================================================================
# READ TOOLS - Available to all roles (customer + admin)
# ===========================================================================


def search_products(query: str, category: str = None, max_results: int = 5) -> dict:
    """Search for products in the catalog using keywords."""
    try:
        table = get_products_table()
        query_lower = query.lower()

        response = table.scan()
        items = response.get("Items", [])

        # Filter out system / discontinued items
        items = [
            i
            for i in items
            if i.get("product_id") != "POLICIES" and i.get("status") != "discontinued"
        ]

        if category:
            items = [
                i for i in items if i.get("category", "").lower() == category.lower()
            ]

        matched = []
        for item in items:
            name = item.get("name", "").lower()
            desc = item.get("description", "").lower()
            if any(term in name or term in desc for term in query_lower.split()):
                matched.append(item)

        matched = matched[:max_results]

        if not matched:
            return {
                "success": True,
                "query": query,
                "results": [],
                "message": f'No products found matching "{query}". Try different keywords.',
            }

        results = [
            {
                "product_id": p.get("product_id"),
                "name": p.get("name"),
                "price": float(p.get("price", 0)),
                "category": p.get("category"),
                "in_stock": p.get("in_stock"),
                "rating": float(p.get("rating", 0)),
                "description": p.get("description", "")[:200],
            }
            for p in matched
        ]

        return {
            "success": True,
            "query": query,
            "result_count": len(results),
            "results": results,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error searching for products: {query}",
        }


def get_product_details(product_id: str) -> dict:
    """Get detailed information about a specific product."""
    try:
        table = get_products_table()
        response = table.get_item(Key={"product_id": product_id})

        if "Item" not in response:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} not found.",
            }

        product = response["Item"]
        return {
            "success": True,
            "product_id": product_id,
            "name": product.get("name"),
            "description": product.get("description"),
            "price": float(product.get("price", 0)),
            "category": product.get("category"),
            "in_stock": product.get("in_stock"),
            "stock_quantity": int(product.get("stock_quantity", 0)),
            "rating": float(product.get("rating", 0)),
            "features": product.get("features", []),
            "specifications": product.get("specifications", {}),
            "warranty": product.get("warranty", "1 year"),
            "return_policy": "30-day return policy",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error getting product details for {product_id}",
        }


def check_inventory(product_id: str) -> dict:
    """Check inventory availability for a product."""
    try:
        table = get_products_table()
        response = table.get_item(Key={"product_id": product_id})

        if "Item" not in response:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} not found in inventory system.",
            }

        product = response["Item"]
        in_stock = product.get("in_stock", False)
        quantity = product.get("stock_quantity", 0)

        result = {
            "success": True,
            "product_id": product_id,
            "product_name": product.get("name"),
            "in_stock": in_stock,
            "quantity_available": int(quantity) if quantity else 0,
        }

        if not in_stock:
            result["restock_date"] = product.get("restock_date", "Unknown")
            result["message"] = (
                f"Product is currently out of stock. Expected restock date: {result['restock_date']}"
            )
        elif quantity and int(quantity) < 10:
            result["message"] = "Low stock - order soon!"
        else:
            result["message"] = "In stock and ready to ship"

        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error checking inventory for {product_id}",
        }


def get_product_recommendations(
    category: str = None, price_max: float = None, limit: int = 5
) -> dict:
    """Get product recommendations based on criteria."""
    try:
        table = get_products_table()
        response = table.scan()
        items = response.get("Items", [])

        items = [
            i
            for i in items
            if i.get("product_id") != "POLICIES" and i.get("status") != "discontinued"
        ]

        if category:
            items = [
                i for i in items if i.get("category", "").lower() == category.lower()
            ]
        if price_max:
            items = [i for i in items if float(i.get("price", 0)) <= price_max]

        items = [i for i in items if i.get("in_stock", False)]
        items.sort(key=lambda x: float(x.get("rating", 0)), reverse=True)
        items = items[:limit]

        if not items:
            return {
                "success": True,
                "recommendations": [],
                "message": "No products match your criteria.",
            }

        recommendations = [
            {
                "product_id": p.get("product_id"),
                "name": p.get("name"),
                "price": float(p.get("price", 0)),
                "category": p.get("category"),
                "rating": float(p.get("rating", 0)),
                "description": p.get("description", "")[:150],
            }
            for p in items
        ]

        return {
            "success": True,
            "recommendation_count": len(recommendations),
            "recommendations": recommendations,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Error getting product recommendations",
        }


def compare_products(product_ids: list) -> dict:
    """Compare multiple products side by side."""
    try:
        if len(product_ids) < 2:
            return {
                "success": False,
                "message": "Please provide at least 2 product IDs to compare.",
            }
        if len(product_ids) > 5:
            return {
                "success": False,
                "message": "Maximum 5 products can be compared at once.",
            }

        table = get_products_table()
        products = []
        for pid in product_ids:
            response = table.get_item(Key={"product_id": pid})
            if "Item" in response:
                p = response["Item"]
                products.append(
                    {
                        "product_id": pid,
                        "name": p.get("name"),
                        "price": float(p.get("price", 0)),
                        "category": p.get("category"),
                        "rating": float(p.get("rating", 0)),
                        "in_stock": p.get("in_stock"),
                        "features": p.get("features", []),
                        "warranty": p.get("warranty", "1 year"),
                    }
                )

        if len(products) < 2:
            return {
                "success": False,
                "message": "Could not find enough products to compare.",
            }

        return {
            "success": True,
            "comparison_count": len(products),
            "products": products,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Error comparing products",
        }


def get_return_policy(product_id: str = None) -> dict:
    """Get return policy information."""
    try:
        policy = {
            "success": True,
            "general_policy": {
                "return_window_days": 30,
                "condition": "Items must be unused and in original packaging",
                "refund_method": "Original payment method",
                "refund_timeline": "5-7 business days after receiving return",
            },
            "exceptions": [
                "Electronics: Must be factory sealed for full refund",
                "Clearance items: Final sale, no returns",
                "Personalized items: Non-returnable",
            ],
            "process": [
                "Initiate return request online or contact customer service",
                "Receive prepaid return shipping label via email",
                "Pack item securely in original packaging",
                "Drop off at carrier location",
                "Refund processed within 5-7 business days of receipt",
            ],
        }

        if product_id:
            table = get_products_table()
            response = table.get_item(Key={"product_id": product_id})
            if "Item" in response:
                product = response["Item"]
                policy["product_specific"] = {
                    "product_id": product_id,
                    "product_name": product.get("name"),
                    "warranty": product.get("warranty", "1 year"),
                    "returnable": True,
                }

        return policy
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Error getting return policy",
        }


# ===========================================================================
# WRITE TOOLS - Admin only (enforced by Gateway RBAC interceptor)
# ===========================================================================


def create_product(
    product_id: str,
    name: str,
    category: str,
    price: float,
    description: str,
    specifications: str,
    stock_quantity: int = 0,
    warranty: str = "1 year manufacturer warranty",
    return_policy: str = "30-day return policy",
) -> dict:
    """Create a new product in the catalog."""
    try:
        table = get_products_table()

        # Check if product already exists
        existing = table.get_item(Key={"product_id": product_id})
        if "Item" in existing:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} already exists. Use update_product to modify it.",
            }

        # Parse specifications
        try:
            specs = (
                json.loads(specifications)
                if isinstance(specifications, str)
                else specifications
            )
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Invalid specifications format. Please provide valid JSON.",
            }

        item = {
            "product_id": product_id,
            "name": name,
            "category": category,
            "price": Decimal(str(price)),
            "description": description,
            "specifications": specs,
            "in_stock": stock_quantity > 0,
            "stock_quantity": stock_quantity,
            "rating": Decimal("0"),
            "warranty": warranty,
            "return_policy": return_policy,
            "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        table.put_item(Item=item)

        return {
            "success": True,
            "product_id": product_id,
            "name": name,
            "category": category,
            "price": price,
            "stock_quantity": stock_quantity,
            "message": f"Product {product_id} ({name}) created successfully.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error creating product {product_id}",
        }


def update_product(product_id: str, updates: str) -> dict:
    """Update an existing product's information."""
    try:
        table = get_products_table()

        existing = table.get_item(Key={"product_id": product_id})
        if "Item" not in existing:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} not found.",
            }

        try:
            update_dict = json.loads(updates) if isinstance(updates, str) else updates
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Invalid updates format. Please provide valid JSON.",
            }

        allowed_fields = {
            "name",
            "description",
            "price",
            "category",
            "specifications",
            "warranty",
            "return_policy",
            "rating",
        }
        invalid_fields = set(update_dict.keys()) - allowed_fields
        if invalid_fields:
            return {
                "success": False,
                "error": f"Cannot update fields: {', '.join(invalid_fields)}. Allowed: {', '.join(allowed_fields)}",
            }

        if not update_dict:
            return {"success": False, "error": "No update fields provided."}

        update_parts = []
        expr_names = {}
        expr_values = {":updated_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        for field, value in update_dict.items():
            safe_name = f"#{field}"
            safe_value = f":{field}"
            update_parts.append(f"{safe_name} = {safe_value}")
            expr_names[safe_name] = field
            if field in ("price", "rating"):
                expr_values[safe_value] = Decimal(str(value))
            elif field == "specifications" and isinstance(value, str):
                expr_values[safe_value] = json.loads(value)
            else:
                expr_values[safe_value] = value

        update_parts.append("#updated_date = :updated_date")
        expr_names["#updated_date"] = "updated_date"

        table.update_item(
            Key={"product_id": product_id},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

        return {
            "success": True,
            "product_id": product_id,
            "updated_fields": list(update_dict.keys()),
            "message": f"Product {product_id} updated successfully. Fields changed: {', '.join(update_dict.keys())}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error updating product {product_id}",
        }


def delete_product(product_id: str) -> dict:
    """Soft-delete a product (mark as discontinued)."""
    try:
        table = get_products_table()

        existing = table.get_item(Key={"product_id": product_id})
        if "Item" not in existing:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} not found.",
            }

        product_name = existing["Item"].get("name", "Unknown")

        table.update_item(
            Key={"product_id": product_id},
            UpdateExpression="SET #status = :status, in_stock = :in_stock, stock_quantity = :qty, "
            "discontinued_date = :ddate, updated_date = :udate",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "discontinued",
                ":in_stock": False,
                ":qty": 0,
                ":ddate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ":udate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        return {
            "success": True,
            "product_id": product_id,
            "name": product_name,
            "action": "soft_delete",
            "message": f"Product {product_id} ({product_name}) has been discontinued and removed from active catalog.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error deleting product {product_id}",
        }


def update_inventory(
    product_id: str, new_quantity: int, restock_date: str = None
) -> dict:
    """Update inventory levels for a product."""
    try:
        table = get_products_table()

        existing = table.get_item(Key={"product_id": product_id})
        if "Item" not in existing:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} not found.",
            }

        if new_quantity < 0:
            return {"success": False, "error": "Stock quantity cannot be negative."}

        in_stock = new_quantity > 0

        update_expr = (
            "SET stock_quantity = :qty, in_stock = :in_stock, updated_date = :udate"
        )
        expr_values = {
            ":qty": new_quantity,
            ":in_stock": in_stock,
            ":udate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if restock_date:
            update_expr += ", restock_date = :rdate"
            expr_values[":rdate"] = restock_date
        elif in_stock:
            update_expr += " REMOVE restock_date"

        table.update_item(
            Key={"product_id": product_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )

        result = {
            "success": True,
            "product_id": product_id,
            "name": existing["Item"].get("name"),
            "new_quantity": new_quantity,
            "in_stock": in_stock,
            "message": f"Inventory updated for {product_id}. New quantity: {new_quantity}.",
        }
        if restock_date and not in_stock:
            result["restock_date"] = restock_date
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error updating inventory for {product_id}",
        }


def update_pricing(
    product_id: str,
    new_price: float,
    sale_price: float = None,
    sale_end_date: str = None,
) -> dict:
    """Update pricing for a product, optionally setting a sale price."""
    try:
        table = get_products_table()

        existing = table.get_item(Key={"product_id": product_id})
        if "Item" not in existing:
            return {
                "success": False,
                "product_id": product_id,
                "message": f"Product {product_id} not found.",
            }

        if new_price <= 0:
            return {"success": False, "error": "Price must be greater than zero."}

        if sale_price is not None and sale_price >= new_price:
            return {
                "success": False,
                "error": f"Sale price (${sale_price}) must be less than regular price (${new_price}).",
            }

        old_price = float(existing["Item"].get("price", 0))

        update_expr = "SET price = :price, updated_date = :udate"
        expr_values = {
            ":price": Decimal(str(new_price)),
            ":udate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if sale_price is not None:
            if not sale_end_date:
                return {
                    "success": False,
                    "error": "sale_end_date is required when setting a sale_price.",
                }
            update_expr += ", sale_price = :sprice, sale_end_date = :sdate"
            expr_values[":sprice"] = Decimal(str(sale_price))
            expr_values[":sdate"] = sale_end_date

        table.update_item(
            Key={"product_id": product_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )

        result = {
            "success": True,
            "product_id": product_id,
            "name": existing["Item"].get("name"),
            "old_price": old_price,
            "new_price": new_price,
            "message": f"Price updated for {product_id}. ${old_price} -> ${new_price}.",
        }
        if sale_price is not None:
            result["sale_price"] = sale_price
            result["sale_end_date"] = sale_end_date
            discount_pct = round((1 - sale_price / new_price) * 100, 1)
            result["message"] += (
                f" Sale price: ${sale_price} ({discount_pct}% off) until {sale_end_date}."
            )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error updating pricing for {product_id}",
        }


# ===========================================================================
# Tool routing
# ===========================================================================

TOOLS = {
    # READ tools
    "search": search_products,
    "get_product_details": get_product_details,
    "check_inventory": check_inventory,
    "get_product_recommendations": get_product_recommendations,
    "compare_products": compare_products,
    "get_return_policy": get_return_policy,
    # WRITE tools (admin only - enforced by Gateway interceptor)
    "create_product": create_product,
    "update_product": update_product,
    "delete_product": delete_product,
    "update_inventory": update_inventory,
    "update_pricing": update_pricing,
}


def lambda_handler(event, context):
    """
    Main Lambda handler for AgentCore Gateway MCP tools.
    Routes to appropriate tool based on bedrockAgentCoreToolName from context.
    """
    try:
        # Get tool name from Lambda context (set by AgentCore Gateway)
        tool_name = None
        if hasattr(context, "client_context") and context.client_context:
            custom = getattr(context.client_context, "custom", {}) or {}
            tool_name = custom.get("bedrockAgentCoreToolName")

        # Fallback to event for local testing
        if not tool_name:
            tool_name = event.get("tool_name") or event.get("__context__", {}).get(
                "bedrockAgentCoreToolName"
            )

        if not tool_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "No tool name specified"}),
            }

        # Strip target prefix if present (e.g., "ProductTools___search_products")
        delimiter = "___"
        if delimiter in tool_name:
            tool_name = tool_name[tool_name.index(delimiter) + len(delimiter) :]

        tool_func = TOOLS.get(tool_name)
        if not tool_func:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unknown tool: {tool_name}"}),
            }

        # Extract arguments from event
        args = event.get("arguments", event)
        if isinstance(args, str):
            args = json.loads(args)

        # Remove metadata keys
        args = {
            k: v for k, v in args.items() if not k.startswith("__") and k != "tool_name"
        }

        logger.info(f"Executing tool: {tool_name} with args: {args}")
        result = tool_func(**args)
        logger.info(f"Tool {tool_name} completed successfully: {result.get('success', True)}")

        return {"statusCode": 200, "body": json.dumps(result, default=decimal_default)}

    except Exception as e:
        logger.error(
            f"Lambda error: {type(e).__name__}: {str(e)}",
            extra={
                "error_type": type(e).__name__,
                "tool_name": tool_name if 'tool_name' in locals() else "unknown",
                "args": args if 'args' in locals() else {}
            },
            exc_info=True
        )
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "error_type": type(e).__name__
            })
        }
