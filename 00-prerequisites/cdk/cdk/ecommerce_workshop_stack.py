"""
E-Commerce Agent Workshop - Infrastructure Stack

Creates:
- DynamoDB Tables (orders, accounts, products) with GSIs
- SSM Parameters for resource discovery
- Custom Resource Lambda to load sample data
"""
import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    CustomResource,
    aws_dynamodb as dynamodb,
    aws_ssm as ssm,
    aws_lambda as lambda_,
    custom_resources as cr,
)
from constructs import Construct


class EcommerceWorkshopStack(Stack):
    """Infrastructure stack for E-Commerce Agent Workshop."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Resource naming prefix
        self.prefix = "ecommerce-workshop"

        # Create DynamoDB tables
        orders_table = self._create_orders_table()
        accounts_table = self._create_accounts_table()
        products_table = self._create_products_table()

        # Create SSM Parameters for resource discovery
        self._create_ssm_parameters(orders_table, accounts_table, products_table)

        # Create custom resource to load sample data
        self._create_data_loader(orders_table, accounts_table, products_table)

        # Outputs
        CfnOutput(self, "OrdersTableName", value=orders_table.table_name)
        CfnOutput(self, "AccountsTableName", value=accounts_table.table_name)
        CfnOutput(self, "ProductsTableName", value=products_table.table_name)

    def _create_orders_table(self) -> dynamodb.Table:
        """Create Orders DynamoDB table with customer email GSI."""
        table = dynamodb.Table(
            self,
            "OrdersTable",
            table_name=f"{self.prefix}-orders",
            partition_key=dynamodb.Attribute(
                name="order_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Add GSI for querying by customer email
        table.add_global_secondary_index(
            index_name="customer-email-index",
            partition_key=dynamodb.Attribute(
                name="customer_email",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    def _create_accounts_table(self) -> dynamodb.Table:
        """Create Accounts DynamoDB table with email GSI."""
        table = dynamodb.Table(
            self,
            "AccountsTable",
            table_name=f"{self.prefix}-accounts",
            partition_key=dynamodb.Attribute(
                name="customer_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Add GSI for querying by email
        table.add_global_secondary_index(
            index_name="email-index",
            partition_key=dynamodb.Attribute(
                name="email",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    def _create_products_table(self) -> dynamodb.Table:
        """Create Products DynamoDB table with category GSI."""
        table = dynamodb.Table(
            self,
            "ProductsTable",
            table_name=f"{self.prefix}-products",
            partition_key=dynamodb.Attribute(
                name="product_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Add GSI for querying by category
        table.add_global_secondary_index(
            index_name="category-index",
            partition_key=dynamodb.Attribute(
                name="category",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    def _create_ssm_parameters(
        self,
        orders_table: dynamodb.Table,
        accounts_table: dynamodb.Table,
        products_table: dynamodb.Table,
    ) -> None:
        """Create SSM Parameters for resource discovery."""
        ssm.StringParameter(
            self,
            "OrdersTableParam",
            parameter_name=f"{self.prefix}-orders-table",
            string_value=orders_table.table_name,
            description="E-Commerce Workshop: Orders table name",
        )

        ssm.StringParameter(
            self,
            "AccountsTableParam",
            parameter_name=f"{self.prefix}-accounts-table",
            string_value=accounts_table.table_name,
            description="E-Commerce Workshop: Accounts table name",
        )

        ssm.StringParameter(
            self,
            "ProductsTableParam",
            parameter_name=f"{self.prefix}-products-table",
            string_value=products_table.table_name,
            description="E-Commerce Workshop: Products table name",
        )

    def _create_data_loader(
        self,
        orders_table: dynamodb.Table,
        accounts_table: dynamodb.Table,
        products_table: dynamodb.Table,
    ) -> None:
        """Create Custom Resource Lambda to load sample data into DynamoDB."""
        # Lambda function for loading data
        data_loader_fn = lambda_.Function(
            self,
            "DataLoaderFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "lambda", "data_loader")
            ),
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "ORDERS_TABLE": orders_table.table_name,
                "ACCOUNTS_TABLE": accounts_table.table_name,
                "PRODUCTS_TABLE": products_table.table_name,
            },
        )

        # Grant write permissions to all tables
        orders_table.grant_write_data(data_loader_fn)
        accounts_table.grant_write_data(data_loader_fn)
        products_table.grant_write_data(data_loader_fn)

        # Create custom resource provider
        provider = cr.Provider(
            self,
            "DataLoaderProvider",
            on_event_handler=data_loader_fn,
        )

        # Custom resource that triggers data loading
        CustomResource(
            self,
            "DataLoaderResource",
            service_token=provider.service_token,
            properties={
                # Change this value to force re-loading data on stack update
                "Version": "1.0",
            },
        )
