"""
Lambda function to load sample data into DynamoDB tables.
Triggered as a CloudFormation Custom Resource during stack creation.
"""
import os
import json
import boto3
from decimal import Decimal


def convert_floats_to_decimal(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    return obj


def load_json_file(filename: str) -> dict:
    """Load JSON data from a file in the same directory as this Lambda."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    with open(file_path, "r") as f:
        return json.load(f)


def load_data_to_table(table_name: str, items: list) -> int:
    """Load items into a DynamoDB table."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    count = 0
    for item in items:
        item = convert_floats_to_decimal(item)
        table.put_item(Item=item)
        count += 1

    return count


def load_products_to_table(table_name: str, products_data: dict) -> int:
    """Load products and policies into the products table."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    count = 0

    # Load products
    for product in products_data.get("products", []):
        product = convert_floats_to_decimal(product)
        # Convert specifications to JSON string if it's a dict
        if "specifications" in product and isinstance(product["specifications"], dict):
            product["specifications"] = json.dumps(product["specifications"])
        table.put_item(Item=product)
        count += 1

    # Load policies as a special item
    policies = products_data.get("policies", {})
    if policies:
        table.put_item(Item={
            "product_id": "POLICIES",
            "category": "SYSTEM",
            "policies": json.dumps(policies)
        })
        count += 1

    return count


def handler(event, context):
    """CloudFormation Custom Resource handler."""
    request_type = event.get("RequestType")

    print(f"Request type: {request_type}")
    print(f"Event: {json.dumps(event)}")

    # Only load data on Create
    if request_type == "Create":
        orders_table = os.environ["ORDERS_TABLE"]
        accounts_table = os.environ["ACCOUNTS_TABLE"]
        products_table = os.environ["PRODUCTS_TABLE"]

        # Load JSON data files
        orders_data = load_json_file("orders.json")
        accounts_data = load_json_file("accounts.json")
        products_data = load_json_file("products.json")

        # Load data into tables
        orders_count = load_data_to_table(orders_table, orders_data.get("orders", []))
        print(f"Loaded {orders_count} orders")

        accounts_count = load_data_to_table(accounts_table, accounts_data.get("accounts", []))
        print(f"Loaded {accounts_count} accounts")

        products_count = load_products_to_table(products_table, products_data)
        print(f"Loaded {products_count} products")

        return {
            "PhysicalResourceId": "DataLoaderResource",
            "Data": {
                "OrdersLoaded": str(orders_count),
                "AccountsLoaded": str(accounts_count),
                "ProductsLoaded": str(products_count),
            }
        }

    # For Update and Delete, just return success
    return {
        "PhysicalResourceId": event.get("PhysicalResourceId", "DataLoaderResource"),
    }
