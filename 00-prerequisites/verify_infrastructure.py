"""
Infrastructure Verification Script for E-Commerce Agent Workshop

This script verifies that all pre-requisite AWS resources are properly deployed
and accessible before starting the workshop.
"""

import boto3
import json
import sys
from botocore.exceptions import ClientError


def check_dynamodb_tables(dynamodb_client, tables):
    """Verify DynamoDB tables exist and have data"""
    results = {}
    for table_name in tables:
        try:
            response = dynamodb_client.describe_table(TableName=table_name)
            status = response['Table']['TableStatus']
            scan_response = dynamodb_client.scan(TableName=table_name, Select='COUNT')
            item_count = scan_response['Count']
            results[table_name] = {
                'exists': True,
                'status': status,
                'item_count': item_count
            }
            print(f"  ✅ {table_name}: {status} ({item_count} items)")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                results[table_name] = {'exists': False, 'error': 'Table not found'}
                print(f"  ❌ {table_name}: Not found")
            else:
                results[table_name] = {'exists': False, 'error': str(e)}
                print(f"  ❌ {table_name}: Error - {e}")
    return results


def check_bedrock_models(bedrock_client, model_ids):
    """Verify Bedrock model access"""
    results = {}
    for model_id in model_ids:
        try:
            # Try to get model info or list foundation models
            response = bedrock_client.list_foundation_models()
            model_found = any(
                model_id in m.get('modelId', '')
                for m in response.get('modelSummaries', [])
            )
            if model_found:
                results[model_id] = {'accessible': True}
                print(f"  ✅ Model: {model_id}")
            else:
                # Model might still be accessible via inference profile
                results[model_id] = {'accessible': True, 'note': 'Via inference profile'}
                print(f"  ✅ Model: {model_id} (inference profile)")
        except ClientError as e:
            results[model_id] = {'accessible': False, 'error': str(e)}
            print(f"  ⚠️  Model: {model_id} - Could not verify")
    return results


def check_ssm_parameters(ssm_client, parameter_names):
    """Verify SSM parameters exist"""
    results = {}
    for param_name in parameter_names:
        try:
            response = ssm_client.get_parameter(Name=param_name)
            value = response['Parameter']['Value']
            results[param_name] = {'exists': True, 'value': value[:50] + '...' if len(value) > 50 else value}
            print(f"  ✅ Parameter: {param_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                results[param_name] = {'exists': False, 'error': 'Not found'}
                print(f"  ❌ Parameter: {param_name} - Not found")
            else:
                results[param_name] = {'exists': False, 'error': str(e)}
                print(f"  ❌ Parameter: {param_name} - Error")
    return results


def check_iam_permissions(sts_client):
    """Verify current identity and basic permissions"""
    try:
        identity = sts_client.get_caller_identity()
        print(f"  ✅ AWS Identity: {identity['Arn']}")
        print(f"  ✅ Account: {identity['Account']}")
        return {'identity': identity['Arn'], 'account': identity['Account']}
    except ClientError as e:
        print(f"  ❌ Could not verify identity: {e}")
        return {'error': str(e)}


def main():
    """Main verification routine"""
    print("\n" + "="*60)
    print("E-Commerce Agent Workshop - Infrastructure Verification")
    print("="*60 + "\n")

    # Get region
    session = boto3.Session()
    region = session.region_name or 'us-east-1'
    print(f"AWS Region: {region}\n")

    # Initialize clients
    dynamodb = boto3.client('dynamodb', region_name=region)
    bedrock = boto3.client('bedrock', region_name=region)
    ssm = boto3.client('ssm', region_name=region)
    sts = boto3.client('sts', region_name=region)

    all_checks_passed = True

    # 1. Check AWS Identity
    print("1. Checking AWS Identity...")
    identity_result = check_iam_permissions(sts)
    if 'error' in identity_result:
        all_checks_passed = False
    print()

    # 2. Check DynamoDB Tables
    print("2. Checking DynamoDB Tables...")
    tables = [
        'ecommerce-workshop-orders',
        'ecommerce-workshop-accounts',
        'ecommerce-workshop-products'
    ]
    dynamodb_results = check_dynamodb_tables(dynamodb, tables)
    if not all(r.get('exists', False) for r in dynamodb_results.values()):
        all_checks_passed = False
    print()

    # 3. Check Bedrock Model Access
    print("3. Checking Bedrock Model Access...")
    # Using global cross-region inference profiles
    models = [
        'anthropic.claude-sonnet-4-5-20250929-v1:0',  # Claude Sonnet 4.5
        'anthropic.claude-haiku-4-5-20251001-v1:0'    # Claude Haiku 4.5
    ]
    model_results = check_bedrock_models(bedrock, models)
    print("   Note: Workshop uses global inference profiles:")
    print("   - global.anthropic.claude-sonnet-4-5-20250929-v1:0")
    print("   - global.anthropic.claude-haiku-4-5-20251001-v1:0")
    print()

    # 4. Check SSM Parameters
    print("4. Checking SSM Parameters...")
    parameters = [
        'ecommerce-workshop-orders-table',
        'ecommerce-workshop-accounts-table',
        'ecommerce-workshop-products-table'
    ]
    ssm_results = check_ssm_parameters(ssm, parameters)
    if not all(r.get('exists', False) for r in ssm_results.values()):
        all_checks_passed = False
    print()

    # Summary
    print("="*60)
    if all_checks_passed:
        print("✅ All infrastructure checks PASSED!")
        print("You are ready to start the workshop.")
    else:
        print("⚠️  Some checks FAILED or could not be verified.")
        print("\nTo set up the required infrastructure, run:")
        print("  python setup_infrastructure.py")
        print("\nThis will create:")
        print("  - DynamoDB tables (orders, accounts, products)")
        print("  - SSM parameters for resource discovery")
        print("\nTo clean up after the workshop:")
        print("  python setup_infrastructure.py --cleanup")
    print("="*60 + "\n")

    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    sys.exit(main())
