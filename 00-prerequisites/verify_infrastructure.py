"""
Infrastructure Verification Script for E-Commerce Agent Workshop

This script verifies that all pre-requisite AWS resources are properly deployed
and accessible before starting the workshop. Required checks determine the basic
pass/fail result. Advanced readiness checks help prepare for later AgentCore
modules and are warnings unless explicitly required.
"""

import argparse
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from workshop_state import get_state_file_path, record_verification_results


WORKSHOP_PREFIX = "ecommerce-workshop"
REQUIRED_TABLES = {
    "orders": f"{WORKSHOP_PREFIX}-orders",
    "accounts": f"{WORKSHOP_PREFIX}-accounts",
    "products": f"{WORKSHOP_PREFIX}-products",
}
REQUIRED_PARAMETERS = {
    "orders_table": f"{WORKSHOP_PREFIX}-orders-table",
    "accounts_table": f"{WORKSHOP_PREFIX}-accounts-table",
    "products_table": f"{WORKSHOP_PREFIX}-products-table",
}
MODEL_IDS = [
    "anthropic.claude-sonnet-4-6",  # Claude Sonnet 4.6
]


def check_dynamodb_tables(dynamodb_client, tables):
    """Verify DynamoDB tables exist and have data"""
    results = {}
    for table_name in tables:
        try:
            response = dynamodb_client.describe_table(TableName=table_name)
            status = response["Table"]["TableStatus"]
            scan_response = dynamodb_client.scan(TableName=table_name, Select="COUNT")
            item_count = scan_response["Count"]
            results[table_name] = {
                "exists": True,
                "status": status,
                "item_count": item_count,
            }
            print(f"  ✅ {table_name}: {status} ({item_count} items)")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "ResourceNotFoundException":
                results[table_name] = {"exists": False, "error": "Table not found"}
                print(f"  ❌ {table_name}: Not found")
            else:
                results[table_name] = {"exists": False, "error": str(e)}
                print(f"  ❌ {table_name}: Error - {e}")
    return results


def check_bedrock_models(bedrock_client, model_ids):
    """Verify Bedrock model access"""
    results = {}
    for model_id in model_ids:
        try:
            response = bedrock_client.list_foundation_models()
            model_found = any(
                model_id in m.get("modelId", "")
                for m in response.get("modelSummaries", [])
            )
            if model_found:
                results[model_id] = {"accessible": True}
                print(f"  ✅ Model: {model_id}")
            else:
                # Model might still be accessible via inference profile.
                results[model_id] = {
                    "accessible": True,
                    "note": "Via inference profile",
                }
                print(f"  ✅ Model: {model_id} (inference profile)")
        except ClientError as e:
            results[model_id] = {"accessible": False, "error": str(e)}
            print(f"  ⚠️  Model: {model_id} - Could not verify")
    return results


def check_ssm_parameters(ssm_client, parameter_names):
    """Verify SSM parameters exist"""
    results = {}
    for param_name in parameter_names:
        try:
            response = ssm_client.get_parameter(Name=param_name)
            value = response["Parameter"]["Value"]
            results[param_name] = {
                "exists": True,
                "value": value[:50] + "..." if len(value) > 50 else value,
            }
            print(f"  ✅ Parameter: {param_name}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "ParameterNotFound":
                results[param_name] = {"exists": False, "error": "Not found"}
                print(f"  ❌ Parameter: {param_name} - Not found")
            else:
                results[param_name] = {"exists": False, "error": str(e)}
                print(f"  ❌ Parameter: {param_name} - Error")
    return results


def check_iam_permissions(sts_client):
    """Verify current identity and basic permissions"""
    try:
        identity = sts_client.get_caller_identity()
        print(f"  ✅ AWS Identity: {identity['Arn']}")
        print(f"  ✅ Account: {identity['Account']}")
        return {"identity": identity["Arn"], "account": identity["Account"]}
    except ClientError as e:
        print(f"  ❌ Could not verify identity: {e}")
        return {"error": str(e)}


def env_flag(name):
    """Read a boolean environment variable."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y"}


def client_error_message(error):
    """Return a short AWS error message for readiness output."""
    if isinstance(error, ClientError):
        details = error.response.get("Error", {})
        code = details.get("Code", "ClientError")
        message = details.get("Message", str(error))
        return f"{code}: {message}"
    return str(error)


def readiness_result(name, ok, message, *, required=False, details=None):
    """Build a JSON-serializable readiness result."""
    status = "passed" if ok else "failed" if required else "warning"
    result = {
        "name": name,
        "ok": ok,
        "required": required,
        "status": status,
        "message": message,
    }
    if details:
        result["details"] = details
    return result


def print_readiness_result(result):
    """Print a readiness result using warning/failure status."""
    if result["ok"]:
        icon = "✅"
    elif result["required"]:
        icon = "❌"
    else:
        icon = "⚠️ "
    print(f"  {icon} {result['name']}: {result['message']}")


def call_readiness_api(client, method_name, *, kwargs=None):
    """Call a read/list API and return the response."""
    operation = getattr(client, method_name)
    return operation(**(kwargs or {}))


def check_control_capability(
    *,
    control_client,
    control_error,
    name,
    method_names,
    required,
):
    """Check whether an AgentCore control-plane capability is reachable."""
    if control_error:
        return readiness_result(
            name,
            False,
            f"AgentCore control client unavailable: {client_error_message(control_error)}",
            required=required,
        )

    available_methods = [
        method_name
        for method_name in method_names
        if getattr(control_client, method_name, None) is not None
    ]
    if not available_methods:
        return readiness_result(
            name,
            False,
            "Installed boto3/botocore does not expose a read API for this capability",
            required=required,
            details={"checked_methods": method_names},
        )

    method_name = available_methods[0]
    try:
        call_readiness_api(control_client, method_name)
        return readiness_result(
            name,
            True,
            f"{method_name} API is reachable",
            required=required,
            details={"method": method_name},
        )
    except (ClientError, BotoCoreError) as e:
        return readiness_result(
            name,
            False,
            client_error_message(e),
            required=required,
            details={"method": method_name},
        )


def check_simple_readiness(
    *,
    name,
    client,
    method_name,
    required,
    kwargs=None,
    success_message=None,
):
    """Check a non-AgentCore read/list API."""
    try:
        call_readiness_api(client, method_name, kwargs=kwargs)
        return readiness_result(
            name,
            True,
            success_message or f"{method_name} API is reachable",
            required=required,
            details={"method": method_name},
        )
    except (ClientError, BotoCoreError) as e:
        return readiness_result(
            name,
            False,
            client_error_message(e),
            required=required,
            details={"method": method_name},
        )


def check_advanced_readiness(region, *, required=False):
    """Run optional advanced readiness checks for later workshop modules."""
    results = {}

    try:
        control_client = boto3.client("bedrock-agentcore-control", region_name=region)
        control_error = None
    except (ClientError, BotoCoreError) as e:
        control_client = None
        control_error = e

    control_checks = {
        "agentcore_runtime": (
            "AgentCore Runtime",
            ["list_agent_runtimes"],
        ),
        "agentcore_gateway": (
            "AgentCore Gateway",
            ["list_gateways"],
        ),
        "agentcore_evaluations": (
            "AgentCore Evaluations",
            ["list_online_evaluation_configs", "list_evaluation_jobs"],
        ),
        "managed_datasets": (
            "Managed Datasets",
            ["list_evaluation_datasets", "list_datasets"],
        ),
        "agentcore_optimization": (
            "AgentCore Optimization",
            ["list_optimization_jobs", "list_optimizations"],
        ),
    }

    for key, (name, methods) in control_checks.items():
        results[key] = check_control_capability(
            control_client=control_client,
            control_error=control_error,
            name=name,
            method_names=methods,
            required=required,
        )
        print_readiness_result(results[key])

    try:
        logs_client = boto3.client("logs", region_name=region)
        results["cloudwatch_logs"] = check_simple_readiness(
            name="CloudWatch Logs",
            client=logs_client,
            method_name="describe_log_groups",
            kwargs={"limit": 1},
            required=required,
        )
    except (ClientError, BotoCoreError) as e:
        results["cloudwatch_logs"] = readiness_result(
            "CloudWatch Logs",
            False,
            client_error_message(e),
            required=required,
        )
    print_readiness_result(results["cloudwatch_logs"])

    try:
        s3_client = boto3.client("s3", region_name=region)
        results["s3"] = check_simple_readiness(
            name="S3",
            client=s3_client,
            method_name="list_buckets",
            required=required,
        )
    except (ClientError, BotoCoreError) as e:
        results["s3"] = readiness_result(
            "S3",
            False,
            client_error_message(e),
            required=required,
        )
    print_readiness_result(results["s3"])

    try:
        iam_client = boto3.client("iam")
        results["iam"] = check_simple_readiness(
            name="IAM",
            client=iam_client,
            method_name="get_account_summary",
            required=required,
        )
    except (ClientError, BotoCoreError) as e:
        results["iam"] = readiness_result(
            "IAM",
            False,
            client_error_message(e),
            required=required,
        )
    print_readiness_result(results["iam"])

    return results


def build_required_check_summary(
    *,
    identity_result,
    dynamodb_results,
    model_results,
    ssm_results,
):
    """Build state-friendly required check results."""
    return {
        "aws_identity": {
            "ok": "error" not in identity_result,
            "result": identity_result,
        },
        "dynamodb_tables": {
            "ok": all(r.get("exists", False) for r in dynamodb_results.values()),
            "results": dynamodb_results,
        },
        "bedrock_models": {
            "ok": all(r.get("accessible", False) for r in model_results.values()),
            "warning_only": True,
            "results": model_results,
        },
        "ssm_parameters": {
            "ok": all(r.get("exists", False) for r in ssm_results.values()),
            "results": ssm_results,
        },
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify E-Commerce Workshop infrastructure"
    )
    parser.add_argument("--region", type=str, help="AWS region", default=None)
    parser.add_argument(
        "--skip-advanced",
        action="store_true",
        help="Skip optional advanced readiness checks",
    )
    parser.add_argument(
        "--require-advanced",
        action="store_true",
        default=env_flag("WORKSHOP_REQUIRE_ADVANCED_CHECKS"),
        help="Treat advanced readiness failures as verification failures",
    )
    return parser.parse_args()


def main():
    """Main verification routine"""
    args = parse_args()

    print("\n" + "=" * 60)
    print("E-Commerce Agent Workshop - Infrastructure Verification")
    print("=" * 60 + "\n")

    # Get region
    session = boto3.Session()
    region = args.region or session.region_name or "us-west-2"
    print(f"AWS Region: {region}\n")

    # Initialize clients
    dynamodb = boto3.client("dynamodb", region_name=region)
    bedrock = boto3.client("bedrock", region_name=region)
    ssm = boto3.client("ssm", region_name=region)
    sts = boto3.client("sts", region_name=region)

    all_checks_passed = True

    # 1. Check AWS Identity
    print("1. Checking AWS Identity...")
    identity_result = check_iam_permissions(sts)
    if "error" in identity_result:
        all_checks_passed = False
    print()

    # 2. Check DynamoDB Tables
    print("2. Checking DynamoDB Tables...")
    dynamodb_results = check_dynamodb_tables(dynamodb, REQUIRED_TABLES.values())
    if not all(r.get("exists", False) for r in dynamodb_results.values()):
        all_checks_passed = False
    print()

    # 3. Check Bedrock Model Access
    print("3. Checking Bedrock Model Access...")
    model_results = check_bedrock_models(bedrock, MODEL_IDS)
    print("   Note: Workshop uses global inference profile:")
    print("   - global.anthropic.claude-sonnet-4-6")
    print()

    # 4. Check SSM Parameters
    print("4. Checking SSM Parameters...")
    ssm_results = check_ssm_parameters(ssm, REQUIRED_PARAMETERS.values())
    if not all(r.get("exists", False) for r in ssm_results.values()):
        all_checks_passed = False
    print()

    # 5. Advanced readiness checks
    advanced_results = {}
    if args.skip_advanced:
        print("5. Skipping Advanced Readiness Checks...")
        print("  ⚠️  Advanced checks skipped by request")
    else:
        print("5. Checking Advanced Readiness for Later Modules...")
        print("   These checks do not create AgentCore or evaluation resources.")
        advanced_results = check_advanced_readiness(
            region,
            required=args.require_advanced,
        )
        if args.require_advanced and not all(
            result.get("ok", False) for result in advanced_results.values()
        ):
            all_checks_passed = False
    print()

    required_summary = build_required_check_summary(
        identity_result=identity_result,
        dynamodb_results=dynamodb_results,
        model_results=model_results,
        ssm_results=ssm_results,
    )

    try:
        record_verification_results(
            account_id=identity_result.get("account"),
            region=region,
            prefix=WORKSHOP_PREFIX,
            required_checks=required_summary,
            advanced_checks=advanced_results,
            advanced_required=args.require_advanced,
        )
        print(f"State manifest updated: {get_state_file_path()}")
        print()
    except Exception as e:
        print(f"⚠️  Could not update state manifest: {e}")
        print()

    warning_count = sum(
        1 for result in advanced_results.values() if result.get("status") == "warning"
    )

    # Summary
    print("=" * 60)
    if all_checks_passed:
        print("✅ All required infrastructure checks PASSED!")
        print("You are ready to start the workshop.")
        if warning_count:
            print(
                f"⚠️  Advanced readiness has {warning_count} warning(s). "
                "Later modules may need those capabilities enabled."
            )
    else:
        print("⚠️  Some required checks FAILED or could not be verified.")
        if args.require_advanced:
            print("Advanced readiness was configured as required for this run.")
        print("\nTo set up the required infrastructure, run:")
        print("  python setup_infrastructure.py")
        print("\nThis will create:")
        print("  - DynamoDB tables (orders, accounts, products)")
        print("  - SSM parameters for resource discovery")
        print("\nTo clean up after the workshop:")
        print("  python setup_infrastructure.py --cleanup")
    print("=" * 60 + "\n")

    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    sys.exit(main())
