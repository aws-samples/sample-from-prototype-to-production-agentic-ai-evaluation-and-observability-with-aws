"""
Workshop Cleanup Script

Removes all AWS resources created during the E-Commerce Agent Workshop (Modules 0-5).
Run this after completing all modules.

Resource inventory:
  Module 0: DynamoDB table (products), SSM parameters
  Module 3: IAM roles (5), ECR repo, Lambda functions (2), Cognito user pool,
            AgentCore gateway + runtime, CloudWatch log groups
  Module 4: Evaluation IAM role, online eval config, CloudWatch dashboard
  Module 5: S3 buckets (2), Firehose stream, Firehose IAM role
"""

import boto3
import sys
import time

WORKSHOP_PREFIX = "ecommerce-workshop"


def get_region():
    session = boto3.Session()
    return session.region_name or "us-west-2"


def get_account_id():
    sts = boto3.client("sts")
    return sts.get_caller_identity()["Account"]


# ── 1. AgentCore Runtime & Gateway ──────────────────────────────────────────


def cleanup_agentcore(region):
    """Delete AgentCore runtime and gateway."""
    print("\n1. Cleaning up AgentCore runtime and gateway...")

    try:
        control = boto3.client("bedrock-agentcore-control", region_name=region)

        # Find and delete the workshop runtime
        runtime_name = "ecommerce_workshop_product_catalog_agent"
        try:
            next_token = None
            while True:
                params = {}
                if next_token:
                    params["nextToken"] = next_token
                resp = control.list_agent_runtimes(**params)
                for rt in resp.get("agentRuntimes", []):
                    if rt.get("agentRuntimeName") == runtime_name:
                        rt_id = rt["agentRuntimeId"]
                        print(f"   Deleting runtime: {rt_id}")
                        control.delete_agent_runtime(agentRuntimeId=rt_id)
                        print(f"   Deleted runtime: {runtime_name}")
                next_token = resp.get("nextToken")
                if not next_token:
                    break
        except Exception as e:
            print(f"   Runtime cleanup: {e}")

        # Find and delete the workshop gateway
        gateway_name = f"{WORKSHOP_PREFIX}-product-gateway"
        try:
            next_token = None
            while True:
                params = {}
                if next_token:
                    params["nextToken"] = next_token
                resp = control.list_gateways(**params)
                for gw in resp.get("gateways", []):
                    if gw.get("name", "").startswith(gateway_name):
                        gw_id = gw["gatewayId"]
                        # Delete gateway targets first
                        try:
                            targets = control.list_gateway_targets(gatewayId=gw_id)
                            for tgt in targets.get("gatewayTargets", []):
                                control.delete_gateway_target(
                                    gatewayId=gw_id,
                                    targetId=tgt["targetId"],
                                )
                                print(f"   Deleted gateway target: {tgt['targetId']}")
                        except Exception:
                            pass
                        control.delete_gateway(gatewayId=gw_id)
                        print(f"   Deleted gateway: {gw_id}")
                next_token = resp.get("nextToken")
                if not next_token:
                    break
        except Exception as e:
            print(f"   Gateway cleanup: {e}")

    except Exception as e:
        print(f"   AgentCore cleanup error: {e}")


# ── 2. Online Evaluation Config ─────────────────────────────────────────────


def cleanup_evaluation_config(region):
    """Delete online evaluation configuration."""
    print("\n2. Cleaning up online evaluation config...")

    try:
        control = boto3.client("bedrock-agentcore-control", region_name=region)
        config_name = "ecommerce_workshop_product_catalog_eval"

        configs = control.list_online_evaluation_configs()
        for config in configs.get("items", configs.get("onlineEvaluationConfigs", [])):
            if config.get("onlineEvaluationConfigName") == config_name:
                config_id = config["onlineEvaluationConfigId"]
                control.delete_online_evaluation_config(
                    onlineEvaluationConfigId=config_id
                )
                print(f"   Deleted eval config: {config_id}")
                return

        print(f"   Eval config not found (skipping)")
    except Exception as e:
        print(f"   Error: {e}")


# ── 3. Cognito User Pool ────────────────────────────────────────────────────


def cleanup_cognito(region):
    """Delete Cognito user pool and associated resources."""
    print("\n3. Cleaning up Cognito user pool...")

    cognito = boto3.client("cognito-idp", region_name=region)
    pool_name = f"{WORKSHOP_PREFIX}-user-pool"

    try:
        pools = cognito.list_user_pools(MaxResults=60)
        for pool in pools.get("UserPools", []):
            if pool["Name"] == pool_name:
                pool_id = pool["Id"]
                # Delete domain first (required before pool deletion)
                try:
                    pool_desc = cognito.describe_user_pool(UserPoolId=pool_id)
                    domain = pool_desc["UserPool"].get("Domain")
                    if domain:
                        cognito.delete_user_pool_domain(
                            UserPoolId=pool_id, Domain=domain
                        )
                        print(f"   Deleted domain: {domain}")
                except Exception:
                    pass

                cognito.delete_user_pool(UserPoolId=pool_id)
                print(f"   Deleted user pool: {pool_name} ({pool_id})")
                return

        print(f"   User pool not found (skipping)")
    except Exception as e:
        print(f"   Error: {e}")


# ── 4. Lambda Functions ─────────────────────────────────────────────────────


def cleanup_lambda_functions(region):
    """Delete workshop Lambda functions."""
    print("\n4. Cleaning up Lambda functions...")

    lam = boto3.client("lambda", region_name=region)
    functions = [
        f"{WORKSHOP_PREFIX}-product-tools",
        f"{WORKSHOP_PREFIX}-rbac-interceptor",
    ]

    for fn_name in functions:
        try:
            lam.delete_function(FunctionName=fn_name)
            print(f"   Deleted: {fn_name}")
        except lam.exceptions.ResourceNotFoundException:
            print(f"   Not found (skipping): {fn_name}")
        except Exception as e:
            print(f"   Error deleting {fn_name}: {e}")


# ── 5. ECR Repository ───────────────────────────────────────────────────────


def cleanup_ecr_repository(region):
    """Delete workshop ECR repository."""
    print("\n5. Cleaning up ECR repository...")

    ecr = boto3.client("ecr", region_name=region)
    repo_name = f"{WORKSHOP_PREFIX}-product-catalog-agent"

    try:
        ecr.delete_repository(repositoryName=repo_name, force=True)
        print(f"   Deleted repository: {repo_name}")
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"   Not found (skipping): {repo_name}")
    except Exception as e:
        print(f"   Error: {e}")


# ── 6. DynamoDB Table ────────────────────────────────────────────────────────


def cleanup_dynamodb_tables(region):
    """Delete workshop DynamoDB table."""
    print("\n6. Cleaning up DynamoDB tables...")

    dynamodb = boto3.client("dynamodb", region_name=region)
    # Only the products table is created by this workshop architecture
    tables = [f"{WORKSHOP_PREFIX}-products"]

    for table_name in tables:
        try:
            dynamodb.delete_table(TableName=table_name)
            print(f"   Deleted: {table_name}")
        except dynamodb.exceptions.ResourceNotFoundException:
            print(f"   Not found (skipping): {table_name}")
        except Exception as e:
            print(f"   Error deleting {table_name}: {e}")


# ── 7. S3 Buckets ───────────────────────────────────────────────────────────


def cleanup_s3_buckets(region, account_id):
    """Delete workshop S3 buckets."""
    print("\n7. Cleaning up S3 buckets...")

    s3 = boto3.client("s3", region_name=region)
    s3_resource = boto3.resource("s3", region_name=region)

    buckets = [
        f"{WORKSHOP_PREFIX}-traces-{account_id}-{region}",
        f"{WORKSHOP_PREFIX}-eval-{account_id}-{region}",
    ]

    for bucket_name in buckets:
        try:
            bucket = s3_resource.Bucket(bucket_name)
            bucket.object_versions.delete()
            bucket.objects.all().delete()
            s3.delete_bucket(Bucket=bucket_name)
            print(f"   Deleted: {bucket_name}")
        except s3.exceptions.NoSuchBucket:
            print(f"   Not found (skipping): {bucket_name}")
        except Exception as e:
            print(f"   Error deleting {bucket_name}: {e}")


# ── 8. Firehose Delivery Stream ─────────────────────────────────────────────


def cleanup_firehose(region):
    """Delete Firehose delivery stream."""
    print("\n8. Cleaning up Firehose delivery stream...")

    firehose = boto3.client("firehose", region_name=region)
    stream_name = f"{WORKSHOP_PREFIX}-traces-stream"

    try:
        firehose.delete_delivery_stream(DeliveryStreamName=stream_name)
        print(f"   Deleted: {stream_name}")
    except Exception as e:
        if "ResourceNotFoundException" in str(e):
            print(f"   Not found (skipping): {stream_name}")
        else:
            print(f"   Error: {e}")


# ── 9. IAM Roles ────────────────────────────────────────────────────────────


def cleanup_iam_roles(region):
    """Delete workshop IAM roles."""
    print("\n9. Cleaning up IAM roles...")

    iam = boto3.client("iam")
    roles = [
        f"{WORKSHOP_PREFIX}-lambda-role",
        f"{WORKSHOP_PREFIX}-gateway-role",
        f"{WORKSHOP_PREFIX}-runtime-role",
        f"{WORKSHOP_PREFIX}-evaluation-role",
        f"{WORKSHOP_PREFIX}-firehose-role",
        f"{WORKSHOP_PREFIX}-cw-logs-role",
    ]

    for role_name in roles:
        try:
            # Delete inline policies
            policies = iam.list_role_policies(RoleName=role_name)
            for policy_name in policies.get("PolicyNames", []):
                iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)

            # Detach managed policies
            attached = iam.list_attached_role_policies(RoleName=role_name)
            for policy in attached.get("AttachedPolicies", []):
                iam.detach_role_policy(
                    RoleName=role_name, PolicyArn=policy["PolicyArn"]
                )

            iam.delete_role(RoleName=role_name)
            print(f"   Deleted: {role_name}")
        except iam.exceptions.NoSuchEntityException:
            print(f"   Not found (skipping): {role_name}")
        except Exception as e:
            print(f"   Error deleting {role_name}: {e}")


# ── 10. SSM Parameters ──────────────────────────────────────────────────────


def cleanup_ssm_parameters(region):
    """Delete workshop SSM parameters."""
    print("\n10. Cleaning up SSM parameters...")

    ssm = boto3.client("ssm", region_name=region)
    params = [
        f"{WORKSHOP_PREFIX}-products-table",
    ]

    for param_name in params:
        try:
            ssm.delete_parameter(Name=param_name)
            print(f"   Deleted: {param_name}")
        except ssm.exceptions.ParameterNotFoundException:
            print(f"   Not found (skipping): {param_name}")
        except Exception as e:
            print(f"   Error deleting {param_name}: {e}")


# ── 11. CloudWatch Resources ────────────────────────────────────────────────


def cleanup_cloudwatch(region):
    """Delete workshop CloudWatch log groups and dashboards."""
    print("\n11. Cleaning up CloudWatch resources...")

    logs = boto3.client("logs", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)

    # Delete dashboard
    dashboard_name = "EcommerceWorkshop-ProductCatalogAgent"
    try:
        cw.delete_dashboards(DashboardNames=[dashboard_name])
        print(f"   Deleted dashboard: {dashboard_name}")
    except Exception as e:
        print(f"   Dashboard: {e}")

    # Delete log groups matching workshop patterns
    prefixes = [
        "/aws/bedrock-agentcore/runtimes/ecommerce_workshop",
        "/aws/bedrock-agentcore/evaluations/",
        "/aws/vendedlogs/bedrock-agentcore/ecommerce_workshop",
        f"/aws/lambda/{WORKSHOP_PREFIX}",
    ]

    for prefix in prefixes:
        try:
            paginator = logs.get_paginator("describe_log_groups")
            for page in paginator.paginate(logGroupNamePrefix=prefix):
                for lg in page.get("logGroups", []):
                    lg_name = lg["logGroupName"]
                    logs.delete_log_group(logGroupName=lg_name)
                    print(f"   Deleted log group: {lg_name}")
        except Exception as e:
            print(f"   Error with prefix {prefix}: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("E-Commerce Agent Workshop - Cleanup Script")
    print("=" * 60)

    region = get_region()
    account_id = get_account_id()
    print(f"\nRegion: {region}")
    print(f"Account: {account_id}")

    print("\nThis will delete ALL workshop resources. This cannot be undone.")
    print("\nResources to delete:")
    print("  - AgentCore runtime + gateway")
    print("  - Online evaluation config")
    print("  - Cognito user pool")
    print("  - Lambda functions (2)")
    print("  - ECR repository")
    print("  - DynamoDB table (products)")
    print("  - S3 buckets (traces, eval)")
    print("  - Firehose delivery stream")
    print("  - IAM roles (5)")
    print("  - SSM parameters")
    print("  - CloudWatch dashboard + log groups")

    response = input("\nType 'DELETE' to confirm: ")
    if response != "DELETE":
        print("Cleanup cancelled.")
        sys.exit(0)

    print("\nStarting cleanup...")

    # Delete in dependency order (dependents first, then dependencies)
    cleanup_evaluation_config(region)  # depends on runtime
    cleanup_agentcore(region)  # depends on gateway, IAM roles
    cleanup_firehose(region)  # depends on S3, IAM
    cleanup_lambda_functions(region)  # depends on IAM roles
    cleanup_cognito(region)
    cleanup_ecr_repository(region)
    cleanup_dynamodb_tables(region)
    cleanup_s3_buckets(region, account_id)
    cleanup_ssm_parameters(region)
    cleanup_cloudwatch(region)

    # IAM roles last (other resources may depend on them)
    print("\n   Waiting 10s for resource deletions to propagate before removing IAM roles...")
    time.sleep(10)
    cleanup_iam_roles(region)

    print("\n" + "=" * 60)
    print("Cleanup complete!")
    print("=" * 60)
    print("\nNote: Some resources may take a few minutes to fully delete.")
    print("Check the AWS Console to verify all resources are removed.")


if __name__ == "__main__":
    main()
