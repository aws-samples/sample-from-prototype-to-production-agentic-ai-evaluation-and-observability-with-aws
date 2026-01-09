"""
Workshop Cleanup Script

Removes all AWS resources created during the workshop.
Run this after completing all modules.
"""

import boto3
import json
import time
import sys

def get_region():
    session = boto3.Session()
    return session.region_name or 'us-east-1'

def cleanup_dynamodb_tables(region):
    """Delete workshop DynamoDB tables"""
    dynamodb = boto3.client('dynamodb', region_name=region)

    tables_to_delete = [
        'ecommerce-workshop-orders',
        'ecommerce-workshop-accounts',
        'ecommerce-workshop-products'
    ]

    print("\n1. Cleaning up DynamoDB tables...")
    for table_name in tables_to_delete:
        try:
            dynamodb.delete_table(TableName=table_name)
            print(f"   Deleted: {table_name}")
        except dynamodb.exceptions.ResourceNotFoundException:
            print(f"   Not found (skipping): {table_name}")
        except Exception as e:
            print(f"   Error deleting {table_name}: {e}")

def cleanup_knowledge_base(region):
    """Delete Bedrock Knowledge Base"""
    bedrock_agent = boto3.client('bedrock-agent', region_name=region)
    ssm = boto3.client('ssm', region_name=region)

    print("\n2. Cleaning up Bedrock Knowledge Base...")

    # Get KB ID from SSM
    try:
        response = ssm.get_parameter(Name='/ecommerce-workshop/knowledge-base-id')
        kb_id = response['Parameter']['Value']

        # Delete Knowledge Base
        bedrock_agent.delete_knowledge_base(knowledgeBaseId=kb_id)
        print(f"   Deleted Knowledge Base: {kb_id}")

        # Delete SSM parameter
        ssm.delete_parameter(Name='/ecommerce-workshop/knowledge-base-id')
        print("   Deleted SSM parameter")

    except ssm.exceptions.ParameterNotFound:
        print("   Knowledge Base ID not found in SSM (skipping)")
    except Exception as e:
        print(f"   Error: {e}")

def cleanup_s3_bucket(region):
    """Delete workshop S3 bucket"""
    s3 = boto3.client('s3', region_name=region)
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']

    bucket_name = f"ecommerce-workshop-kb-{account_id}-{region}"

    print("\n3. Cleaning up S3 bucket...")

    try:
        # First, delete all objects
        s3_resource = boto3.resource('s3', region_name=region)
        bucket = s3_resource.Bucket(bucket_name)
        bucket.object_versions.delete()
        bucket.objects.all().delete()
        print(f"   Emptied bucket: {bucket_name}")

        # Then delete bucket
        s3.delete_bucket(Bucket=bucket_name)
        print(f"   Deleted bucket: {bucket_name}")

    except s3.exceptions.NoSuchBucket:
        print(f"   Bucket not found (skipping): {bucket_name}")
    except Exception as e:
        print(f"   Error: {e}")

def cleanup_agentcore_runtime(region):
    """Delete AgentCore Runtime deployment"""

    print("\n4. Cleaning up AgentCore Runtime...")

    try:
        from bedrock_agentcore_starter_toolkit import Runtime

        runtime = Runtime()

        # List and delete agent runtimes
        # Note: This is a simplified cleanup - actual implementation depends on toolkit API
        print("   AgentCore cleanup requires manual intervention or toolkit support")
        print("   Check AWS Console: Bedrock > AgentCore > Runtimes")

    except ImportError:
        print("   AgentCore toolkit not installed (skipping)")
    except Exception as e:
        print(f"   Error: {e}")

def cleanup_iam_role(region):
    """Delete workshop IAM role"""
    iam = boto3.client('iam')

    role_name = 'AgentCore-ecommerce-customer-service-role'

    print("\n5. Cleaning up IAM role...")

    try:
        # Delete inline policies
        policies = iam.list_role_policies(RoleName=role_name)
        for policy_name in policies.get('PolicyNames', []):
            iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            print(f"   Deleted policy: {policy_name}")

        # Delete role
        iam.delete_role(RoleName=role_name)
        print(f"   Deleted role: {role_name}")

    except iam.exceptions.NoSuchEntityException:
        print(f"   Role not found (skipping): {role_name}")
    except Exception as e:
        print(f"   Error: {e}")

def cleanup_cloudwatch_logs(region):
    """Delete workshop CloudWatch log groups"""
    logs = boto3.client('logs', region_name=region)

    print("\n6. Cleaning up CloudWatch log groups...")

    prefixes = [
        '/aws/bedrock-agentcore/ecommerce',
        '/aws/lambda/ecommerce-workshop'
    ]

    try:
        for prefix in prefixes:
            paginator = logs.get_paginator('describe_log_groups')
            for page in paginator.paginate(logGroupNamePrefix=prefix):
                for lg in page.get('logGroups', []):
                    logs.delete_log_group(logGroupName=lg['logGroupName'])
                    print(f"   Deleted: {lg['logGroupName']}")
    except Exception as e:
        print(f"   Error: {e}")

def cleanup_ecr_repository(region):
    """Delete workshop ECR repository"""
    ecr = boto3.client('ecr', region_name=region)

    print("\n7. Cleaning up ECR repository...")

    repo_name = 'ecommerce-customer-service'

    try:
        # Delete all images first
        response = ecr.list_images(repositoryName=repo_name)
        image_ids = response.get('imageIds', [])

        if image_ids:
            ecr.batch_delete_image(repositoryName=repo_name, imageIds=image_ids)
            print(f"   Deleted {len(image_ids)} images")

        # Delete repository
        ecr.delete_repository(repositoryName=repo_name, force=True)
        print(f"   Deleted repository: {repo_name}")

    except ecr.exceptions.RepositoryNotFoundException:
        print(f"   Repository not found (skipping): {repo_name}")
    except Exception as e:
        print(f"   Error: {e}")

def main():
    print("="*60)
    print("E-Commerce Agent Workshop - Cleanup Script")
    print("="*60)

    region = get_region()
    print(f"\nRegion: {region}")

    # Confirm before proceeding
    print("\nThis will delete ALL workshop resources. This cannot be undone.")
    response = input("Type 'DELETE' to confirm: ")

    if response != 'DELETE':
        print("Cleanup cancelled.")
        sys.exit(0)

    print("\nStarting cleanup...")

    # Run cleanup in order (dependent resources first)
    cleanup_agentcore_runtime(region)
    cleanup_knowledge_base(region)
    cleanup_dynamodb_tables(region)
    cleanup_s3_bucket(region)
    cleanup_ecr_repository(region)
    cleanup_cloudwatch_logs(region)
    cleanup_iam_role(region)

    print("\n" + "="*60)
    print("Cleanup complete!")
    print("="*60)
    print("\nNote: Some resources may take a few minutes to fully delete.")
    print("Check the AWS Console to verify all resources are removed.")

if __name__ == "__main__":
    main()
