"""
Utility helpers for the e-commerce agent workshop notebooks.
"""

import json
import boto3
from decimal import Decimal


def _decimal_to_python(obj):
    """Recursively convert DynamoDB Decimal values to native Python types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_python(i) for i in obj]
    return obj


def get_product_from_dynamodb(product_id: str, table_name: str, region: str) -> dict | None:
    """
    Retrieve a single product item directly from DynamoDB and return it as a
    plain Python dict (all Decimal values converted to float).

    Args:
        product_id: The product primary key, e.g. "PROD-200".
        table_name: DynamoDB table name.
        region:     AWS region string.

    Returns:
        Product dict if found, otherwise None.
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    response = table.get_item(Key={'product_id': product_id})
    item = response.get('Item')
    return _decimal_to_python(item) if item else None


def print_product(product: dict) -> None:
    """Pretty-print a product dict returned by get_product_from_dynamodb."""
    print(f"  Product ID    : {product.get('product_id')}")
    print(f"  Name          : {product.get('name')}")
    print(f"  Category      : {product.get('category')}")
    print(f"  Price         : ${product.get('price')}")
    print(f"  In Stock      : {product.get('in_stock')}")
    print(f"  Stock Qty     : {product.get('stock_quantity')}")
    print(f"  Rating        : {product.get('rating')}")
    print(f"  Warranty      : {product.get('warranty')}")
    print(f"  Return Policy : {product.get('return_policy')}")
    print(f"  Created Date  : {product.get('created_date')}")
    print(f"  Updated Date  : {product.get('updated_date')}")
    if product.get('description'):
        print(f"\n  Description   : {product.get('description')}")
    specs = product.get('specifications', {})
    if isinstance(specs, str):
        specs = json.loads(specs)
    if specs:
        print("\n  Specifications:")
        for k, v in specs.items():
            print(f"    - {k}: {v}")
    print("\nRaw item (JSON):")
    print(json.dumps(product, indent=2, default=str))
