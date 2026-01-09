#!/usr/bin/env python3
"""
E-Commerce Agent Workshop - Infrastructure Setup Script

This script provisions all required AWS infrastructure:
1. DynamoDB tables (orders, accounts, products)
2. SSM Parameters for resource discovery

Prerequisites:
- AWS credentials configured
- Bedrock model access enabled for Claude models

Usage:
    python setup_infrastructure.py [--region REGION] [--cleanup]
"""

import boto3
import json
import time
import argparse
import os
from decimal import Decimal
from botocore.exceptions import ClientError


def convert_floats_to_decimal(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    return obj


class InfrastructureSetup:
    """Setup infrastructure for E-Commerce Agent Workshop"""

    def __init__(self, region: str = None):
        self.session = boto3.Session()
        self.region = region or self.session.region_name or 'us-west-2'
        self.account_id = boto3.client('sts').get_caller_identity()['Account']

        # Resource naming
        self.prefix = 'ecommerce-workshop'
        self.orders_table = f'{self.prefix}-orders'
        self.accounts_table = f'{self.prefix}-accounts'
        self.products_table = f'{self.prefix}-products'

        # Initialize clients
        self.dynamodb = boto3.client('dynamodb', region_name=self.region)
        self.dynamodb_resource = boto3.resource('dynamodb', region_name=self.region)
        self.ssm = boto3.client('ssm', region_name=self.region)

        print(f"Infrastructure Setup initialized")
        print(f"  Region: {self.region}")
        print(f"  Account: {self.account_id}")
        print(f"  Prefix: {self.prefix}")

    def setup_all(self):
        """Run complete infrastructure setup"""
        print("\n" + "="*60)
        print("Starting Infrastructure Setup")
        print("="*60)

        try:
            # 1. DynamoDB Tables
            self.create_dynamodb_tables()
            self.load_sample_data()

            # 2. Products table
            self.create_products_table()
            self.load_products_data()

            # 3. SSM Parameters
            self.create_ssm_parameters()

            print("\n" + "="*60)
            print("INFRASTRUCTURE SETUP COMPLETE!")
            print("="*60)
            print(f"\nResources created:")
            print(f"  - DynamoDB: {self.orders_table}")
            print(f"  - DynamoDB: {self.accounts_table}")
            print(f"  - DynamoDB: {self.products_table}")
            print(f"\nRun verify_infrastructure.py to confirm setup")

        except Exception as e:
            print(f"\nERROR: Setup failed - {e}")
            raise

    def create_dynamodb_tables(self):
        """Create DynamoDB tables for orders and accounts"""
        print("\n1. Creating DynamoDB Tables...")

        # Orders table
        self._create_table(
            table_name=self.orders_table,
            key_schema=[
                {'AttributeName': 'order_id', 'KeyType': 'HASH'}
            ],
            attribute_definitions=[
                {'AttributeName': 'order_id', 'AttributeType': 'S'},
                {'AttributeName': 'customer_email', 'AttributeType': 'S'}
            ],
            gsi=[{
                'IndexName': 'customer-email-index',
                'KeySchema': [
                    {'AttributeName': 'customer_email', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }]
        )

        # Accounts table
        self._create_table(
            table_name=self.accounts_table,
            key_schema=[
                {'AttributeName': 'customer_id', 'KeyType': 'HASH'}
            ],
            attribute_definitions=[
                {'AttributeName': 'customer_id', 'AttributeType': 'S'},
                {'AttributeName': 'email', 'AttributeType': 'S'}
            ],
            gsi=[{
                'IndexName': 'email-index',
                'KeySchema': [
                    {'AttributeName': 'email', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }]
        )

    def _create_table(self, table_name: str, key_schema: list,
                      attribute_definitions: list, gsi: list = None):
        """Create a single DynamoDB table"""
        try:
            self.dynamodb.describe_table(TableName=table_name)
            print(f"  ✅ {table_name}: Already exists")
            return
        except self.dynamodb.exceptions.ResourceNotFoundException:
            pass

        params = {
            'TableName': table_name,
            'KeySchema': key_schema,
            'AttributeDefinitions': attribute_definitions,
            'BillingMode': 'PAY_PER_REQUEST'
        }

        if gsi:
            params['GlobalSecondaryIndexes'] = gsi

        self.dynamodb.create_table(**params)
        print(f"  ⏳ {table_name}: Creating...")

        waiter = self.dynamodb.get_waiter('table_exists')
        waiter.wait(TableName=table_name)
        print(f"  ✅ {table_name}: Created")

    def load_sample_data(self):
        """Load sample data into DynamoDB tables"""
        print("\n2. Loading Sample Data...")

        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Load orders
        orders_file = os.path.join(script_dir, 'sample_data', 'orders.json')
        with open(orders_file, 'r') as f:
            orders_data = json.load(f)

        orders_table = self.dynamodb_resource.Table(self.orders_table)
        for order in orders_data['orders']:
            order = convert_floats_to_decimal(order)
            orders_table.put_item(Item=order)
        print(f"  ✅ Loaded {len(orders_data['orders'])} orders")

        # Load accounts
        accounts_file = os.path.join(script_dir, 'sample_data', 'accounts.json')
        with open(accounts_file, 'r') as f:
            accounts_data = json.load(f)

        accounts_table = self.dynamodb_resource.Table(self.accounts_table)
        for account in accounts_data['accounts']:
            account = convert_floats_to_decimal(account)
            accounts_table.put_item(Item=account)
        print(f"  ✅ Loaded {len(accounts_data['accounts'])} accounts")

    def create_products_table(self):
        """Create DynamoDB table for products"""
        print("\n3. Creating Products Table...")

        self._create_table(
            table_name=self.products_table,
            key_schema=[
                {'AttributeName': 'product_id', 'KeyType': 'HASH'}
            ],
            attribute_definitions=[
                {'AttributeName': 'product_id', 'AttributeType': 'S'},
                {'AttributeName': 'category', 'AttributeType': 'S'}
            ],
            gsi=[{
                'IndexName': 'category-index',
                'KeySchema': [
                    {'AttributeName': 'category', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }]
        )

    def load_products_data(self):
        """Load product data into DynamoDB"""
        print("\n4. Loading Product Data...")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        products_file = os.path.join(script_dir, 'sample_data', 'products.json')

        with open(products_file, 'r') as f:
            products_data = json.load(f)

        products_table = self.dynamodb_resource.Table(self.products_table)
        for product in products_data['products']:
            product = convert_floats_to_decimal(product)
            # Convert specifications to JSON string
            if 'specifications' in product and isinstance(product['specifications'], dict):
                product['specifications'] = json.dumps(product['specifications'])
            products_table.put_item(Item=product)
        print(f"  ✅ Loaded {len(products_data['products'])} products")

        # Store policies as a separate item
        policies = products_data.get('policies', {})
        if policies:
            products_table.put_item(Item={
                'product_id': 'POLICIES',
                'category': 'SYSTEM',
                'policies': json.dumps(policies)
            })
            print(f"  ✅ Loaded store policies")

    def create_ssm_parameters(self):
        """Create SSM parameters for resource discovery"""
        print("\n5. Creating SSM Parameters...")

        parameters = {
            f'{self.prefix}-orders-table': self.orders_table,
            f'{self.prefix}-accounts-table': self.accounts_table,
            f'{self.prefix}-products-table': self.products_table,
        }

        for name, value in parameters.items():
            try:
                self.ssm.put_parameter(
                    Name=name,
                    Value=value,
                    Type='String',
                    Overwrite=True,
                    Description=f'E-Commerce Workshop: {name}'
                )
                print(f"  ✅ {name}: {value}")
            except Exception as e:
                print(f"  ❌ {name}: {e}")

    def cleanup(self):
        """Remove all workshop infrastructure"""
        print("\n" + "="*60)
        print("Cleaning Up Infrastructure")
        print("="*60)

        # Delete SSM parameters
        print("\n1. Deleting SSM Parameters...")
        for name in [f'{self.prefix}-orders-table', f'{self.prefix}-accounts-table',
                     f'{self.prefix}-products-table']:
            try:
                self.ssm.delete_parameter(Name=name)
                print(f"  ✅ Deleted: {name}")
            except:
                print(f"  ⚠️ Not found: {name}")

        # Delete DynamoDB tables
        print("\n2. Deleting DynamoDB Tables...")
        for table in [self.orders_table, self.accounts_table, self.products_table]:
            try:
                self.dynamodb.delete_table(TableName=table)
                print(f"  ✅ Deleting: {table}")
            except:
                print(f"  ⚠️ Not found: {table}")

        print("\n" + "="*60)
        print("CLEANUP COMPLETE!")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description='E-Commerce Workshop Infrastructure Setup')
    parser.add_argument('--region', type=str, help='AWS region', default=None)
    parser.add_argument('--cleanup', action='store_true', help='Remove all infrastructure')
    args = parser.parse_args()

    setup = InfrastructureSetup(region=args.region)

    if args.cleanup:
        setup.cleanup()
    else:
        setup.setup_all()


if __name__ == '__main__':
    main()
