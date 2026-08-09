"""Helpers for Section 05 AgentCore A/B experiments."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.exceptions import ClientError


class ABExperimentError(RuntimeError):
    """Raised when an A/B experiment prerequisite is not satisfied."""


def _agentcore_scope_from_runtime(runtime_arn: str) -> tuple[str | None, str | None, str]:
    parts = runtime_arn.split(":")
    if len(parts) >= 6:
        region = parts[3]
        account_id = parts[4]
        return region, account_id, f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
    return None, None, "*"


def ensure_ab_gateway_role(
    iam_client,
    *,
    role_name: str,
    runtime_arn: str,
) -> dict[str, Any]:
    region, account_id, source_arn = _agentcore_scope_from_runtime(runtime_arn)
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                **(
                    {
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": account_id},
                            "ArnLike": {"aws:SourceArn": source_arn},
                        }
                    }
                    if account_id
                    else {}
                ),
            }
        ],
    }
    try:
        role = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="AgentCore Gateway role for Section 05 A/B experiments",
        )["Role"]
        time.sleep(10)
    except iam_client.exceptions.EntityAlreadyExistsException:
        role = iam_client.get_role(RoleName=role_name)["Role"]

    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName=f"{role_name}-agentcore-ab-policy",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "bedrock-agentcore:*",
                            "logs:DescribeLogGroups",
                            "logs:FilterLogEvents",
                            "logs:GetLogEvents",
                            "logs:StartQuery",
                            "logs:GetQueryResults",
                            "logs:StopQuery",
                        ],
                        "Resource": "*",
                    }
                ],
            }
        ),
    )
    return role


def wait_for_gateway_ready(ctrl_client, gateway_id: str, *, max_polls: int = 30) -> dict[str, Any]:
    last = {}
    for _ in range(max_polls):
        last = ctrl_client.get_gateway(gatewayIdentifier=gateway_id)
        if last.get("status") == "READY":
            return last
        time.sleep(5)
    return last


def wait_for_target_ready(
    ctrl_client,
    *,
    gateway_id: str,
    target_id: str,
    max_polls: int = 30,
) -> dict[str, Any]:
    last = {}
    for _ in range(max_polls):
        last = ctrl_client.get_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
        )
        if last.get("status") == "READY":
            return last
        time.sleep(5)
    return last


def create_runtime_gateway_and_target(
    ctrl_client,
    *,
    gateway_name: str,
    target_name: str,
    role_arn: str,
    runtime_arn: str,
    region: str,
    account_id: str,
) -> dict[str, Any]:
    gateway = ctrl_client.create_gateway(
        name=gateway_name,
        description="Section 05 config-bundle A/B gateway",
        authorizerType="AWS_IAM",
        roleArn=role_arn,
        clientToken=str(uuid.uuid4()),
    )
    gateway_id = gateway["gatewayId"]
    gateway = wait_for_gateway_ready(ctrl_client, gateway_id)
    gateway_arn = gateway.get("gatewayArn") or (
        f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/{gateway_id}"
    )
    gateway_url = gateway.get("gatewayUrl") or (
        f"https://{gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com"
    )

    target = ctrl_client.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name=target_name,
        description="Section 05 runtime target for config-bundle A/B",
        targetConfiguration={
            "http": {
                "agentcoreRuntime": {
                    "arn": runtime_arn,
                    "qualifier": "DEFAULT",
                }
            }
        },
        credentialProviderConfigurations=[
            {"credentialProviderType": "GATEWAY_IAM_ROLE"}
        ],
        clientToken=str(uuid.uuid4()),
    )
    target_id = target["targetId"]
    target = wait_for_target_ready(
        ctrl_client,
        gateway_id=gateway_id,
        target_id=target_id,
    )
    return {
        "gateway_id": gateway_id,
        "gateway_arn": gateway_arn,
        "gateway_url": gateway_url,
        "gateway_status": gateway.get("status"),
        "target_id": target_id,
        "target_name": target_name,
        "target_status": target.get("status"),
    }


def ensure_gateway_trace_delivery(
    logs_client,
    xray_client,
    *,
    gateway_arn: str,
    delivery_source_name: str,
) -> dict[str, Any]:
    """Configure trace delivery for the A/B Gateway, following AgentCore samples."""
    result: dict[str, Any] = {
        "delivery_source_name": delivery_source_name,
        "gateway_arn": gateway_arn,
        "status": "STARTED",
        "warnings": [],
    }
    try:
        destination = xray_client.get_trace_segment_destination()
        if destination.get("Destination") != "CloudWatchLogs":
            xray_client.update_trace_segment_destination(Destination="CloudWatchLogs")
        result["xray_destination"] = "CloudWatchLogs"
    except Exception as exc:
        result["warnings"].append(f"xray:{type(exc).__name__}")

    try:
        logs_client.put_delivery_source(
            name=delivery_source_name,
            resourceArn=gateway_arn,
            logType="TRACES",
        )
        result["delivery_source_status"] = "READY"
    except Exception as exc:
        result["warnings"].append(f"delivery_source:{type(exc).__name__}")

    try:
        destinations = logs_client.describe_delivery_destinations().get(
            "deliveryDestinations", []
        )
        xray_destination = next(
            (
                item
                for item in destinations
                if item.get("deliveryDestinationType") == "XRAY"
            ),
            None,
        )
        if not xray_destination:
            logs_client.put_delivery_destination(
                name="xray-destination",
                deliveryDestinationType="XRAY",
            )
            destinations = logs_client.describe_delivery_destinations().get(
                "deliveryDestinations", []
            )
            xray_destination = next(
                (
                    item
                    for item in destinations
                    if item.get("deliveryDestinationType") == "XRAY"
                ),
                None,
            )
        if xray_destination:
            delivery = logs_client.create_delivery(
                deliverySourceName=delivery_source_name,
                deliveryDestinationArn=xray_destination["arn"],
            )
            result["delivery_id"] = delivery.get("delivery", {}).get("id")
            result["delivery_status"] = "READY"
    except Exception as exc:
        result["warnings"].append(f"delivery:{type(exc).__name__}")

    result["status"] = "READY" if result.get("delivery_status") == "READY" else "PARTIAL"
    return result


def require_gateway_trace_delivery_ready(delivery: Mapping[str, Any]) -> None:
    """Fail when Gateway trace delivery was not fully configured."""
    if delivery.get("status") != "READY":
        raise ABExperimentError(
            "A/B Gateway trace delivery is not ready: "
            f"status={delivery.get('status')}, warnings={delivery.get('warnings')}"
        )


def create_ab_online_evaluation_config(
    ctrl_client,
    *,
    name: str,
    description: str,
    log_group_names: Sequence[str],
    service_names: Sequence[str],
    evaluation_execution_role_arn: str,
    evaluator_ids: Sequence[str] = ("Builtin.GoalSuccessRate", "Builtin.Helpfulness"),
    session_timeout_minutes: int = 1,
) -> dict[str, Any]:
    """Create an online evaluation config dedicated to a Section 05 A/B test."""
    response = ctrl_client.create_online_evaluation_config(
        onlineEvaluationConfigName=name,
        description=description,
        dataSourceConfig={
            "cloudWatchLogs": {
                "logGroupNames": list(log_group_names),
                "serviceNames": list(service_names),
            }
        },
        evaluators=[{"evaluatorId": evaluator_id} for evaluator_id in evaluator_ids],
        rule={
            "samplingConfig": {"samplingPercentage": 100.0},
            "sessionConfig": {"sessionTimeoutMinutes": session_timeout_minutes},
        },
        evaluationExecutionRoleArn=evaluation_execution_role_arn,
        enableOnCreate=True,
        clientToken=str(uuid.uuid4()),
    )
    config_id = response["onlineEvaluationConfigId"]
    config = response
    for _ in range(30):
        config = ctrl_client.get_online_evaluation_config(
            onlineEvaluationConfigId=config_id
        )
        if config.get("status") == "ACTIVE" and config.get("executionStatus") == "ENABLED":
            break
        time.sleep(5)
    return {
        **summarize_online_evaluation_config(config),
        "online_evaluation_config_name": name,
        "source": "section05_ab_specific",
        "session_timeout_minutes": session_timeout_minutes,
    }


def create_config_bundle_ab_test(
    data_client,
    *,
    name: str,
    gateway_arn: str,
    role_arn: str,
    online_evaluation_config_arn: str,
    control_bundle: Mapping[str, Any],
    treatment_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    return data_client.create_ab_test(
        name=name,
        description="Section 05 config-bundle A/B: control versus recommendation treatment",
        gatewayArn=gateway_arn,
        roleArn=role_arn,
        enableOnCreate=True,
        evaluationConfig={"onlineEvaluationConfigArn": online_evaluation_config_arn},
        variants=[
            {
                "name": "C",
                "weight": 50,
                "variantConfiguration": {
                    "configurationBundle": {
                        "bundleArn": control_bundle["bundle_arn"],
                        "bundleVersion": control_bundle["version_id"],
                    }
                },
            },
            {
                "name": "T1",
                "weight": 50,
                "variantConfiguration": {
                    "configurationBundle": {
                        "bundleArn": treatment_bundle["bundle_arn"],
                        "bundleVersion": treatment_bundle["version_id"],
                    }
                },
            },
        ],
        clientToken=str(uuid.uuid4()),
    )


def wait_for_ab_running(data_client, ab_test_id: str, *, max_polls: int = 30) -> dict[str, Any]:
    last = {}
    for _ in range(max_polls):
        last = data_client.get_ab_test(abTestId=ab_test_id)
        status = last.get("status")
        execution_status = last.get("executionStatus")
        if status == "ACTIVE" and execution_status == "RUNNING":
            return last
        if "FAILED" in str(status):
            return last
        time.sleep(5)
    return last


def require_ab_running(ab_test: Mapping[str, Any]) -> None:
    status = ab_test.get("status")
    execution_status = ab_test.get("executionStatus")
    errors = ab_test.get("errorDetails") or []
    if status != "ACTIVE" or execution_status != "RUNNING" or errors:
        raise ABExperimentError(
            "A/B test is not ready for traffic: "
            f"status={status}, executionStatus={execution_status}, errors={errors}"
        )


def summarize_online_evaluation_config(config: Mapping[str, Any]) -> dict[str, Any]:
    cloudwatch = (config.get("dataSourceConfig") or {}).get("cloudWatchLogs") or {}
    return {
        "online_evaluation_config_id": config.get("onlineEvaluationConfigId"),
        "online_evaluation_config_arn": config.get("onlineEvaluationConfigArn"),
        "status": config.get("status"),
        "execution_status": config.get("executionStatus"),
        "failure_reason": config.get("failureReason"),
        "log_group_names": list(cloudwatch.get("logGroupNames") or []),
        "service_names": list(cloudwatch.get("serviceNames") or []),
        "evaluator_ids": [
            item.get("evaluatorId") or item.get("evaluatorArn")
            for item in config.get("evaluators", [])
        ],
    }


def online_evaluation_alignment(
    config: Mapping[str, Any],
    *,
    required_service_names: Sequence[str] = (),
    required_log_group_names: Sequence[str] = (),
) -> dict[str, Any]:
    """Report whether an online-eval config watches the expected trace sources."""
    cloudwatch = (config.get("dataSourceConfig") or {}).get("cloudWatchLogs") or {}
    configured_services = list(dict.fromkeys(cloudwatch.get("serviceNames") or []))
    configured_log_groups = list(dict.fromkeys(cloudwatch.get("logGroupNames") or []))
    required_service_candidates = [
        name for name in dict.fromkeys(required_service_names) if name
    ]
    required_services = required_service_candidates[-1:]
    required_log_groups = [name for name in dict.fromkeys(required_log_group_names) if name]
    missing_services = [
        name for name in required_services if name not in configured_services
    ]
    missing_log_groups = [
        name for name in required_log_groups if name not in configured_log_groups
    ]
    return {
        "configured_service_names": configured_services,
        "configured_log_group_names": configured_log_groups,
        "required_service_names": required_services,
        "required_log_group_names": required_log_groups,
        "missing_service_names": missing_services,
        "missing_log_group_names": missing_log_groups,
        "aligned": not missing_services and not missing_log_groups,
    }


def ensure_online_evaluation_alignment(
    ctrl_client,
    config: Mapping[str, Any],
    *,
    required_service_names: Sequence[str],
    required_log_group_names: Sequence[str] = (),
) -> dict[str, Any]:
    """Update a live online-eval config so endpoint and app spans are both visible."""
    alignment = online_evaluation_alignment(
        config,
        required_service_names=required_service_names,
        required_log_group_names=required_log_group_names,
    )
    if alignment["aligned"]:
        return {"config": dict(config), "alignment": alignment, "updated": False}

    config_id = config.get("onlineEvaluationConfigId")
    if not config_id:
        raise ABExperimentError("Online evaluation config has no ID; cannot align data source")

    target_service_names = alignment["required_service_names"][-1:] or alignment[
        "configured_service_names"
    ][:1]
    merged_log_group_names = list(
        dict.fromkeys(
            alignment["configured_log_group_names"] + alignment["required_log_group_names"]
        )
    )
    params: dict[str, Any] = {
        "onlineEvaluationConfigId": config_id,
        "clientToken": str(uuid.uuid4()),
        "dataSourceConfig": {
            "cloudWatchLogs": {
                "logGroupNames": merged_log_group_names,
                "serviceNames": target_service_names,
            }
        },
    }
    for key in [
        "description",
        "rule",
        "evaluators",
        "insights",
        "clusteringConfig",
        "evaluationExecutionRoleArn",
        "executionStatus",
    ]:
        value = config.get(key)
        if value is not None:
            params[key] = value

    ctrl_client.update_online_evaluation_config(**params)
    updated = {}
    for _ in range(30):
        updated = ctrl_client.get_online_evaluation_config(onlineEvaluationConfigId=config_id)
        updated_alignment = online_evaluation_alignment(
            updated,
            required_service_names=required_service_names,
            required_log_group_names=required_log_group_names,
        )
        if (
            updated.get("status") == "ACTIVE"
            and updated.get("executionStatus") == "ENABLED"
            and updated_alignment["aligned"]
        ):
            break
        time.sleep(5)
    updated_alignment = online_evaluation_alignment(
        updated,
        required_service_names=required_service_names,
        required_log_group_names=required_log_group_names,
    )
    return {"config": updated, "alignment": updated_alignment, "updated": True}


def require_online_evaluation_ready(
    config: Mapping[str, Any],
    *,
    required_service_names: Sequence[str] = (),
    required_log_group_names: Sequence[str] = (),
) -> None:
    summary = summarize_online_evaluation_config(config)
    alignment = online_evaluation_alignment(
        config,
        required_service_names=required_service_names,
        required_log_group_names=required_log_group_names,
    )
    if (
        summary.get("status") != "ACTIVE"
        or summary.get("execution_status") != "ENABLED"
        or summary.get("failure_reason")
    ):
        raise ABExperimentError(
            "Online evaluation config is not ready for A/B scoring: "
            f"status={summary.get('status')}, "
            f"executionStatus={summary.get('execution_status')}, "
            f"failureReason={summary.get('failure_reason')}"
        )
    if not alignment["aligned"]:
        raise ABExperimentError(
            "Online evaluation config is not aligned with the required trace sources: "
            f"missingServiceNames={alignment.get('missing_service_names')}, "
            f"missingLogGroupNames={alignment.get('missing_log_group_names')}"
        )


def _parse_json_response_text(text: str) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass

    for line in str(text).splitlines():
        line = line.strip()
        if line.startswith("data:"):
            candidate = line[5:].strip()
            try:
                return json.loads(candidate)
            except ValueError:
                continue
    return None


def summarize_gateway_response(response) -> dict[str, Any]:
    """Summarize transport and runtime status for an A/B Gateway invocation."""
    text = getattr(response, "text", "") or ""
    parsed = _parse_json_response_text(text)
    status_code = getattr(response, "status_code", None)
    runtime_status = parsed.get("status") if isinstance(parsed, Mapping) else None
    metadata = parsed.get("metadata") if isinstance(parsed, Mapping) else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}

    transport_ok = status_code == 200
    runtime_ok = runtime_status in (None, "success")
    ok = transport_ok and runtime_ok
    summary: dict[str, Any] = {
        "status_code": status_code,
        "ok": ok,
        "transport_ok": transport_ok,
        "runtime_status": runtime_status,
    }
    if runtime_status:
        summary["runtime_status"] = runtime_status
    if isinstance(parsed, Mapping) and parsed.get("error"):
        summary["runtime_error"] = str(parsed.get("error"))[:240]
    if metadata:
        summary["role"] = metadata.get("role")
        summary["tools_used"] = list(metadata.get("tools_used") or [])
        summary["tools_available"] = metadata.get("tools_available")
    if isinstance(parsed, Mapping) and parsed.get("response"):
        summary["response_chars"] = len(str(parsed.get("response")))
    elif text:
        summary["response_sample"] = text[:500]
    return summary


def invoke_ab_gateway(
    *,
    gateway_url: str,
    target_name: str,
    region: str,
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    invoke_url = f"{gateway_url.rstrip('/')}/{target_name}/invocations"
    sessions = []
    success = 0
    failed = 0
    for item in payloads:
        session_id = str(item["session_id"])
        body = json.dumps(item["payload"])
        request = AWSRequest(
            method="POST",
            url=invoke_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
            },
        )
        SigV4Auth(credentials, "bedrock-agentcore", region).add_auth(request)
        record = {
            "session_id": session_id,
            "actor_role": item.get("actor_role"),
            "prompt_name": item.get("prompt_name"),
        }
        try:
            response = requests.post(
                invoke_url,
                data=body,
                headers=dict(request.headers),
                timeout=120,
            )
            record.update(summarize_gateway_response(response))
            if record["ok"]:
                success += 1
            else:
                failed += 1
        except Exception as exc:
            record["ok"] = False
            record["error_type"] = type(exc).__name__
            failed += 1
        sessions.append(record)
        time.sleep(1)
    return {
        "invoke_url_path": f"/{target_name}/invocations",
        "success": success,
        "failed": failed,
        "sessions": sessions,
    }


def require_gateway_traffic_success(
    traffic: Mapping[str, Any],
    *,
    expected_count: int | None = None,
) -> None:
    success = int(traffic.get("success") or 0)
    failed = int(traffic.get("failed") or 0)
    if failed or success == 0 or (expected_count is not None and success != expected_count):
        raise ABExperimentError(
            "A/B Gateway traffic did not complete cleanly: "
            f"success={success}, failed={failed}, expected={expected_count}"
        )


def _load_json_message(message: str) -> dict[str, Any]:
    try:
        parsed = json.loads(message)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def collect_ab_trace_evidence(
    logs_client,
    *,
    sessions: Sequence[Mapping[str, Any]],
    log_group_names: Sequence[str],
    lookback_minutes: int = 30,
    max_sessions: int = 6,
) -> dict[str, Any]:
    """Check that A/B traffic produced scoreable model spans and no MCP/bundle errors."""
    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(minutes=lookback_minutes)).timestamp() * 1000)
    end_ms = int((now + timedelta(minutes=1)).timestamp() * 1000)
    runtime_log_groups = [
        name
        for name in log_group_names
        if "/aws/bedrock-agentcore/runtimes/" in str(name)
    ]
    runtime_log_group = runtime_log_groups[0] if runtime_log_groups else None
    checked = []
    counts = {
        "model_span_sessions": 0,
        "mcp_http_span_sessions": 0,
        "mcp_400_sessions": 0,
        "bundle_access_denied_sessions": 0,
        "bundle_fetch_sessions": 0,
    }

    for record in list(sessions)[:max_sessions]:
        session_id = str(record.get("session_id") or "")
        if not session_id:
            continue
        trace_id = None
        try:
            events = logs_client.filter_log_events(
                logGroupName="aws/spans",
                startTime=start_ms,
                endTime=end_ms,
                filterPattern=f'"{session_id}"',
                limit=100,
            ).get("events", [])
            for event in events:
                trace_id = _load_json_message(event.get("message", "")).get("traceId")
                if trace_id:
                    break
        except Exception:
            events = []

        names = []
        mcp_http = False
        mcp_400 = False
        if trace_id:
            try:
                trace_events = logs_client.filter_log_events(
                    logGroupName="aws/spans",
                    startTime=start_ms,
                    endTime=end_ms,
                    filterPattern=f'"{trace_id}"',
                    limit=300,
                ).get("events", [])
            except Exception:
                trace_events = []
            for event in trace_events:
                span = _load_json_message(event.get("message", ""))
                names.append(span.get("name"))
                attrs = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
                if attrs.get("http.url") and "product-gateway" in str(attrs.get("http.url")):
                    mcp_http = True
                if attrs.get("http.status_code") == 400 or attrs.get("http.response.status_code") == 400:
                    mcp_400 = True

        app_events = []
        if runtime_log_group:
            try:
                app_events = logs_client.filter_log_events(
                    logGroupName=runtime_log_group,
                    startTime=start_ms,
                    endTime=end_ms,
                    filterPattern=f'"{session_id}"',
                    limit=80,
                ).get("events", [])
            except Exception:
                app_events = []
        denied = any(
            "AccessDeniedException" in event.get("message", "")
            or "Configuration bundle unavailable" in event.get("message", "")
            for event in app_events
        )
        fetched = any(
            "Received config bundle ref" in event.get("message", "")
            for event in app_events
        ) and not denied
        has_model = any(str(name).startswith("chat") for name in names)
        has_agent = any(
            name in {"invoke_agent Strands Agents", "product_catalog.agent_invocation"}
            for name in names
        )
        checked.append(
            {
                "session_id": session_id,
                "trace_id": trace_id,
                "has_model_span": has_model,
                "has_agent_span": has_agent,
                "has_product_gateway_http_span": mcp_http,
                "has_mcp_400": mcp_400,
                "bundle_access_denied": denied,
                "bundle_fetch_seen": fetched,
            }
        )
        counts["model_span_sessions"] += int(has_model)
        counts["mcp_http_span_sessions"] += int(mcp_http)
        counts["mcp_400_sessions"] += int(mcp_400)
        counts["bundle_access_denied_sessions"] += int(denied)
        counts["bundle_fetch_sessions"] += int(fetched)

    return {"checked_sessions": checked, **counts}


def require_ab_trace_evidence(evidence: Mapping[str, Any]) -> None:
    """Fail before metrics polling when A/B traces are not scoreable."""
    if (
        int(evidence.get("model_span_sessions") or 0) <= 0
        or int(evidence.get("mcp_400_sessions") or 0) > 0
        or int(evidence.get("bundle_access_denied_sessions") or 0) > 0
        or int(evidence.get("bundle_fetch_sessions") or 0) <= 0
    ):
        raise ABExperimentError(
            "A/B traffic did not produce clean scoreable traces: "
            f"modelSpanSessions={evidence.get('model_span_sessions')}, "
            f"mcp400Sessions={evidence.get('mcp_400_sessions')}, "
            f"bundleAccessDeniedSessions={evidence.get('bundle_access_denied_sessions')}, "
            f"bundleFetchSessions={evidence.get('bundle_fetch_sessions')}"
        )


def wait_for_ab_trace_evidence(
    logs_client,
    *,
    sessions: Sequence[Mapping[str, Any]],
    log_group_names: Sequence[str],
    timeout_seconds: int = 420,
    poll_seconds: int = 20,
    lookback_minutes: int = 30,
) -> dict[str, Any]:
    """Poll CloudWatch until A/B traffic has the spans needed for scoring."""
    deadline = time.time() + timeout_seconds
    last: dict[str, Any] = {}
    while True:
        last = collect_ab_trace_evidence(
            logs_client,
            sessions=sessions,
            log_group_names=log_group_names,
            lookback_minutes=lookback_minutes,
        )
        try:
            require_ab_trace_evidence(last)
            last["status"] = "READY"
            return last
        except ABExperimentError as exc:
            last["status"] = "WAITING"
            last["last_error"] = str(exc)
            if time.time() >= deadline:
                last["status"] = "TIMEOUT"
                return last
            time.sleep(poll_seconds)


def poll_ab_results(
    data_client,
    ab_test_id: str,
    *,
    max_polls: int = 10,
    poll_seconds: int = 60,
) -> dict[str, Any]:
    last = {}
    for poll_index in range(max_polls):
        last = data_client.get_ab_test(abTestId=ab_test_id)
        results = last.get("results") or {}
        metrics = results.get("evaluatorMetrics") or []
        if results.get("analysisTimestamp") and metrics:
            return last
        if poll_index < max_polls - 1:
            time.sleep(poll_seconds)
    return last


def stop_ab_test(data_client, ab_test_id: str) -> dict[str, Any]:
    try:
        return data_client.update_ab_test(
            abTestId=ab_test_id,
            executionStatus="STOPPED",
            clientToken=str(uuid.uuid4()),
        )
    except ClientError as exc:
        return {
            "status": "STOP_FAILED",
            "error_code": exc.response.get("Error", {}).get("Code"),
        }


def finalize_ab_test_for_decision(
    data_client,
    ab_test_id: str,
    *,
    stop_before_decision: bool,
    post_stop_polls: int = 10,
    poll_seconds: int = 60,
) -> dict[str, Any]:
    """Stop an A/B test when needed, then poll for final decision metrics."""
    initial = data_client.get_ab_test(abTestId=ab_test_id)
    initial_summary = summarize_ab_test(initial)
    finalization: dict[str, Any] = {
        "stop_before_decision": stop_before_decision,
        "stopped_by_notebook": False,
        "post_stop_polls": post_stop_polls,
        "poll_seconds": poll_seconds,
        "initial_execution_status": initial_summary.get("execution_status"),
    }
    if initial_summary.get("has_results") or initial_summary.get("service_error"):
        finalization["reason"] = "A/B already had terminal decision evidence"
        if (
            stop_before_decision
            and initial_summary.get("has_results")
            and initial_summary.get("execution_status") == "RUNNING"
        ):
            finalization["stop_response"] = stop_ab_test(data_client, ab_test_id)
            finalization["stopped_by_notebook"] = True
            final = poll_ab_results(
                data_client,
                ab_test_id,
                max_polls=post_stop_polls,
                poll_seconds=poll_seconds,
            )
            final_summary = summarize_ab_test(final)
            finalization["final_execution_status"] = final_summary.get("execution_status")
            finalization["has_results_after_stop"] = final_summary.get("has_results")
            finalization["metric_count_after_stop"] = final_summary.get("metric_count")
            return {"summary": final_summary, "finalization": finalization}
        return {"summary": initial_summary, "finalization": finalization}

    if stop_before_decision and initial_summary.get("execution_status") == "RUNNING":
        finalization["stop_response"] = stop_ab_test(data_client, ab_test_id)
        finalization["stopped_by_notebook"] = True
        final = poll_ab_results(
            data_client,
            ab_test_id,
            max_polls=post_stop_polls,
            poll_seconds=poll_seconds,
        )
        final_summary = summarize_ab_test(final)
        finalization["final_execution_status"] = final_summary.get("execution_status")
        finalization["has_results_after_stop"] = final_summary.get("has_results")
        finalization["metric_count_after_stop"] = final_summary.get("metric_count")
        return {"summary": final_summary, "finalization": finalization}

    finalization["reason"] = (
        "A/B test was not stopped before decision; final metrics may not be available "
        "until the test is stopped or maxDurationExpiresAt is reached"
    )
    return {"summary": initial_summary, "finalization": finalization}


def _metric_value(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percent_change(control_mean: Any, treatment_mean: Any, percent_change: Any) -> float | None:
    explicit = _metric_value(percent_change)
    if explicit is not None:
        return explicit
    control = _metric_value(control_mean)
    treatment = _metric_value(treatment_mean)
    if control in (None, 0) or treatment is None:
        return None
    return ((treatment - control) / control) * 100


def summarize_ab_test(ab_test: Mapping[str, Any]) -> dict[str, Any]:
    results = ab_test.get("results") or {}
    metrics = results.get("evaluatorMetrics") or []
    status = ab_test.get("status")
    execution_status = ab_test.get("executionStatus")
    error_details = ab_test.get("errorDetails") or []
    service_error = (
        bool(error_details)
        or "FAILED" in str(status or "").upper()
        or "FAILED" in str(execution_status or "").upper()
    )
    metric_summaries = []
    winners = []
    regressions = []
    for metric in metrics:
        evaluator_arn = metric.get("evaluatorArn")
        evaluator_id = str(evaluator_arn).split("/")[-1] if evaluator_arn else metric.get("evaluatorId")
        control_stats = dict(metric.get("controlStats") or {})
        variant_summaries = []
        for item in metric.get("variantResults") or []:
            variant_name = (
                item.get("name")
                or item.get("variantName")
                or item.get("variant")
                or item.get("variantId")
            )
            pct = _percent_change(
                control_stats.get("mean"),
                item.get("mean"),
                item.get("percentChange"),
            )
            significant = item.get("isSignificant")
            variant = {
                "variant_name": variant_name,
                "mean": item.get("mean"),
                "sample_size": item.get("sampleSize") or item.get("n"),
                "p_value": item.get("pValue"),
                "is_significant": significant,
                "percent_change": pct,
            }
            if significant is True and pct is not None and pct < 0:
                regressions.append({"evaluator_id": evaluator_id, **variant})
            elif significant is True and pct is not None and pct > 0:
                winners.append({"evaluator_id": evaluator_id, **variant})
            variant_summaries.append(variant)
        metric_summaries.append(
            {
                "evaluator_id": evaluator_id,
                "evaluator_arn": evaluator_arn,
                "control_stats": control_stats,
                "variant_results": variant_summaries,
            }
        )

    if service_error:
        derived_decision = "ERROR"
        promotion_candidate = None
    elif not (results.get("analysisTimestamp") and metrics):
        derived_decision = "NO_RESULTS"
        promotion_candidate = None
    elif regressions:
        derived_decision = "REGRESSION"
        promotion_candidate = None
    elif winners:
        derived_decision = "COMPLETED_WITH_WINNER"
        promotion_candidate = winners[0].get("variant_name")
    else:
        derived_decision = "NO_WINNER"
        promotion_candidate = None

    return {
        "ab_test_id": ab_test.get("abTestId"),
        "ab_test_arn": ab_test.get("abTestArn"),
        "status": status,
        "execution_status": execution_status,
        "current_run_id": ab_test.get("currentRunId"),
        "started_at": ab_test.get("startedAt"),
        "stopped_at": ab_test.get("stoppedAt"),
        "max_duration_expires_at": ab_test.get("maxDurationExpiresAt"),
        "error_details": error_details,
        "service_error": service_error,
        "has_results": bool(results.get("analysisTimestamp") and metrics),
        "analysis_timestamp": results.get("analysisTimestamp"),
        "metric_count": len(metrics),
        "evaluator_metrics": metric_summaries,
        "derived_decision": derived_decision,
        "promotion_candidate": promotion_candidate,
        "regressions": regressions,
        "winners": winners,
    }


def derive_config_bundle_ab_status(
    ab_summary: Mapping[str, Any],
    *,
    keep_ab_running: bool,
) -> str:
    """Map raw A/B service state to the notebook's release-decision status."""
    if ab_summary.get("derived_decision") == "ERROR":
        return "ERROR"
    if ab_summary.get("has_results"):
        return str(ab_summary.get("derived_decision") or "NO_RESULTS")
    if keep_ab_running:
        return "RUNNING_NO_RESULTS_YET"
    return "TRAFFIC_ROUTED_NO_RESULTS_STOPPED"


def flatten_ab_metric_rows(
    ab_summary: Mapping[str, Any],
    *,
    treatment_variant_names: Sequence[str] = ("T1", "treatment"),
    min_variant_sample_size: int = 1,
) -> list[dict[str, Any]]:
    """Create learner-friendly rows from AgentCore A/B evaluator metrics."""
    treatment_names = {str(name) for name in treatment_variant_names}
    rows: list[dict[str, Any]] = []
    for metric in ab_summary.get("evaluator_metrics") or []:
        control_stats = dict(metric.get("control_stats") or {})
        control_sample_size = (
            control_stats.get("sampleSize")
            or control_stats.get("sample_size")
            or control_stats.get("n")
        )
        for variant in metric.get("variant_results") or []:
            variant_name = str(variant.get("variant_name") or "")
            treatment_sample_size = variant.get("sample_size")
            sample_sizes = [
                size
                for size in [
                    _metric_value(control_sample_size),
                    _metric_value(treatment_sample_size),
                ]
                if size is not None
            ]
            effective_sample_size = min(sample_sizes) if sample_sizes else None
            percent_change = _metric_value(variant.get("percent_change"))
            is_significant = variant.get("is_significant") is True
            if is_significant and percent_change is not None and percent_change < 0:
                signal = "significant_regression"
            elif is_significant and percent_change is not None and percent_change > 0:
                signal = "significant_improvement"
            elif is_significant:
                signal = "significant_no_change"
            else:
                signal = "not_significant"
            rows.append(
                {
                    "evaluator_id": metric.get("evaluator_id"),
                    "variant_name": variant_name,
                    "is_treatment_variant": variant_name in treatment_names,
                    "control_mean": control_stats.get("mean"),
                    "treatment_mean": variant.get("mean"),
                    "percent_change": percent_change,
                    "p_value": variant.get("p_value"),
                    "is_significant": is_significant,
                    "control_sample_size": control_sample_size,
                    "treatment_sample_size": treatment_sample_size,
                    "effective_sample_size": effective_sample_size,
                    "meets_min_sample_size": (
                        effective_sample_size is not None
                        and effective_sample_size >= min_variant_sample_size
                    ),
                    "signal": signal,
                }
            )
    return rows


def build_ab_metric_review(
    ab_summary: Mapping[str, Any],
    *,
    treatment_variant_names: Sequence[str] = ("T1", "treatment"),
    min_variant_sample_size: int = 1,
) -> dict[str, Any]:
    """Derive the release-decision recommendation from A/B evaluator metrics."""
    rows = flatten_ab_metric_rows(
        ab_summary,
        treatment_variant_names=treatment_variant_names,
        min_variant_sample_size=min_variant_sample_size,
    )
    treatment_rows = [row for row in rows if row["is_treatment_variant"]]
    low_sample_rows = [
        row
        for row in treatment_rows
        if not row["meets_min_sample_size"]
    ]
    regressions = [
        row
        for row in treatment_rows
        if row["signal"] == "significant_regression"
    ]
    improvements = [
        row
        for row in treatment_rows
        if row["signal"] == "significant_improvement"
    ]
    decision_rules = [
        "Do not promote when the A/B service reports errors.",
        "Do not promote until evaluator metrics and an analysis timestamp are present.",
        "Do not promote when treatment sample size is below the configured minimum.",
        "Do not promote when any treatment evaluator shows a significant regression.",
        "Promote only after a significant treatment improvement and explicit operator approval.",
    ]

    if ab_summary.get("service_error"):
        status = "ERROR"
        recommended_decision = "investigate"
        rationale = "A/B service errors are present; evaluator evidence is not clean."
        next_action = "Inspect error_details, fix the service issue, and rerun the experiment."
        promotion_ready = False
    elif not ab_summary.get("has_results"):
        stopped_without_results = (
            ab_summary.get("execution_status") == "STOPPED"
            or bool(ab_summary.get("stopped_at"))
        )
        status = "NO_RESULTS_AFTER_STOP" if stopped_without_results else "NO_RESULTS"
        recommended_decision = "continue"
        if stopped_without_results:
            rationale = "A/B was finalized, but evaluator metrics were not produced."
            next_action = (
                "Do not promote; rerun with more representative A/B traffic or "
                "investigate the online evaluation and A/B scoring configuration."
            )
        else:
            rationale = "A/B evaluator metrics are not available yet."
            next_action = "Keep the test running or poll again before making a promotion decision."
        promotion_ready = False
    elif regressions:
        status = "REGRESSION"
        recommended_decision = "investigate"
        rationale = "At least one treatment evaluator shows a significant regression."
        next_action = "Do not promote; inspect the regressed evaluator and revise the treatment."
        promotion_ready = False
    elif low_sample_rows:
        status = "INSUFFICIENT_SAMPLE"
        recommended_decision = "continue"
        rationale = "Evaluator metrics are present, but treatment sample size is below the configured minimum."
        next_action = "Continue the experiment until each treatment evaluator has enough samples."
        promotion_ready = False
    elif improvements:
        status = "COMPLETED_WITH_WINNER"
        recommended_decision = "promote"
        rationale = "Treatment has a significant improvement and no significant regression."
        next_action = "Review the metric table, then set SECTION05_OPERATOR_DECISION=promote for an explicit promotion decision."
        promotion_ready = True
    else:
        status = "NO_WINNER"
        recommended_decision = "continue"
        rationale = "Evaluator metrics are present, but the treatment did not produce a significant win."
        next_action = "Continue collecting traffic or revise the treatment candidate."
        promotion_ready = False

    return {
        "status": status,
        "recommended_release_decision": recommended_decision,
        "promotion_candidate_ready": promotion_ready,
        "promotion_candidate": ab_summary.get("promotion_candidate") if promotion_ready else None,
        "min_variant_sample_size": min_variant_sample_size,
        "metric_rows": rows,
        "decision_rules": decision_rules,
        "rationale": rationale,
        "next_action": next_action,
        "regressions": regressions,
        "improvements": improvements,
        "low_sample_rows": low_sample_rows,
    }
