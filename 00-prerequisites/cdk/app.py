#!/usr/bin/env python3
"""
E-Commerce Agent Workshop - CDK Application

This CDK app provisions all required AWS infrastructure:
1. DynamoDB tables (orders, accounts, products) with GSIs
2. SSM Parameters for resource discovery
3. Custom Resource to load sample data

Usage:
    cdk synth    # Synthesize CloudFormation template
    cdk deploy   # Deploy to AWS
    cdk destroy  # Clean up all resources
"""
import os
import aws_cdk as cdk

from cdk.ecommerce_workshop_stack import EcommerceWorkshopStack


app = cdk.App()
EcommerceWorkshopStack(
    app,
    "EcommerceWorkshopStack",
    description="E-Commerce Agent Workshop Infrastructure - DynamoDB tables, SSM parameters, and sample data",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION'),
    ),
)

app.synth()
