#!/usr/bin/env python3
"""
Section 03 deployment-contract helpers.

These helpers keep deployment evidence, grounded post-deploy evaluation inputs,
and optional observability hardening records in predictable JSON artifacts.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SECTION_DIR = Path(__file__).resolve().parent
REPO_ROOT = SECTION_DIR.parent
DATASET_MANIFEST_PATH = SECTION_DIR / "dataset_manifest.json"
DEPLOYMENT_MANIFEST_PATH = SECTION_DIR / "deployment_manifest.json"
BATCH_EVALUATION_MANIFEST_PATH = SECTION_DIR / "batch_evaluation_manifest.json"
POSTDEPLOY_GROUND_TRUTH_PATH = SECTION_DIR / "postdeploy_ground_truth.json"
POSTDEPLOY_GATE_CONFIG_PATH = SECTION_DIR / "postdeploy_gate_config.json"

VALID_GATE_MODES = {"blocking", "review_only"}

DENYLIST_KEY_FRAGMENTS = {
    "authorization",
    "bearer",
    "jwt",
    "id_token",
    "access_token",
    "refresh_token",
    "client_secret",
    "password",
    "secret",
    "credential",
    "email",
}

SAFE_RUNTIME_ENV_KEYS = {
    "DEPLOYMENT_ID",
    "AGENT_VERSION",
    "MODEL_ID",
    "OTEL_SERVICE_NAME",
    "PROMPT_VERSION",
    "TOOL_POLICY_VERSION",
}

SAFE_TRACE_ATTRIBUTE_KEYS = {
    "deployment.id",
    "agent.version",
    "agent.model_id",
    "agent.prompt_version",
    "agent.tool_policy_version",
    "runtime.role",
    "runtime.session_id",
    "runtime.region",
    "gateway.url_host",
    "tools.available_count",
    "tools.allowed_count",
    "tools.used_count",
    "operation.status",
    "error.type",
}

PII_OR_SECRET_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(authorization|bearer|jwt|token|password|secret|credential)\b"),
]


class DeploymentContractError(ValueError):
    """Raised when Section 03 deployment artifacts are invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def make_deployment_id(prefix: str = "section03") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


def load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.is_file():
        raise DeploymentContractError(f"Missing JSON artifact: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DeploymentContractError(f"JSON artifact must contain an object: {json_path}")
    return data


def save_json(data: Mapping[str, Any], path: str | os.PathLike[str]) -> Path:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return json_path


def load_dataset_manifest(path: Path = DATASET_MANIFEST_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return load_json(path)


def assert_dataset_manifest_ready(dataset_manifest: Mapping[str, Any] | None) -> None:
    """Require the Section 03a managed dataset before deployment starts."""
    if not dataset_manifest:
        raise DeploymentContractError(
            "Section 03a dataset manifest is missing. Run 03a-ground-truth-dataset.ipynb first."
        )

    status = dataset_manifest.get("dataset_client_status") or {}
    status_value = status.get("status")
    if status_value != "CREATED_AND_PUBLISHED":
        reason = status.get("reason") or "managed dataset was not created and published"
        raise DeploymentContractError(
            "Section 03a managed dataset is not ready. "
            f"status={status_value or 'UNKNOWN'} reason={reason}. "
            "Do not continue to deployment until DatasetClient has created and published the dataset."
        )

    managed = dataset_manifest.get("managed_datasets") or {}
    for name in ["predefined", "simulated"]:
        pointer = managed.get(name) or {}
        if not pointer.get("dataset_id"):
            raise DeploymentContractError(f"Managed {name} dataset is missing dataset_id")
        if not pointer.get("baseline_dataset_version"):
            raise DeploymentContractError(
                f"Managed {name} dataset is missing baseline_dataset_version"
            )


def load_postdeploy_ground_truth(
    path: Path = POSTDEPLOY_GROUND_TRUTH_PATH,
) -> dict[str, Any]:
    artifact = load_json(path)
    scenarios = artifact.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise DeploymentContractError("postdeploy_ground_truth.json has no scenarios")
    return artifact


def endpoint_otel_service_name(runtime_name: str, endpoint_name: str = "DEFAULT") -> str:
    """Return the AgentCore endpoint service name used by observability/evaluation."""
    runtime = str(runtime_name or "").strip()
    endpoint = str(endpoint_name or "DEFAULT").strip() or "DEFAULT"
    if not runtime:
        raise DeploymentContractError("runtime_name is required for OTEL service name")
    return f"{runtime}.{endpoint}"


def build_release_metadata_env(
    *,
    deployment_id: str,
    agent_version: str,
    model_id: str,
    otel_service_name: str,
    prompt_version: str | None = None,
    tool_policy_version: str | None = None,
) -> dict[str, str]:
    env = {
        "DEPLOYMENT_ID": deployment_id,
        "AGENT_VERSION": agent_version,
        "MODEL_ID": model_id,
        "OTEL_SERVICE_NAME": otel_service_name,
    }
    if prompt_version:
        env["PROMPT_VERSION"] = prompt_version
    if tool_policy_version:
        env["TOOL_POLICY_VERSION"] = tool_policy_version
    validate_release_metadata_env(env)
    return env


def validate_release_metadata_env(env: Mapping[str, Any]) -> None:
    for key, value in env.items():
        if key not in SAFE_RUNTIME_ENV_KEYS:
            raise DeploymentContractError(f"Unsafe runtime env key: {key}")
        validate_no_sensitive_values({key: value})


def ecr_image_evidence(
    ecr_client: Any,
    *,
    repository: str,
    tag: str,
    image_uri: str,
    latest_uri: str | None = None,
) -> dict[str, Any]:
    evidence = {
        "repository": repository,
        "tag": tag,
        "image_uri": image_uri,
        "latest_uri": latest_uri,
        "digest": None,
        "digest_source": "unavailable",
    }
    try:
        response = ecr_client.describe_images(
            repositoryName=repository,
            imageIds=[{"imageTag": tag}],
        )
        details = response.get("imageDetails") or []
        if details:
            evidence["digest"] = details[0].get("imageDigest")
            evidence["digest_source"] = "ecr.describe_images"
    except Exception as exc:
        evidence["digest_error"] = f"{type(exc).__name__}: {exc}"
    validate_no_sensitive_values(evidence)
    return evidence


def scenario_runtime_payload(
    scenario: Mapping[str, Any],
    *,
    session_id: str,
    role_tokens: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    role = str(scenario.get("role", "customer"))
    tokens = role_tokens.get(role) or {}
    return {
        "prompt": scenario.get("prompt", ""),
        "bearer_token": tokens.get("id_token", ""),
        "access_token": tokens.get("access_token", ""),
        "session_id": session_id,
    }


def reference_inputs_kwargs(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Return kwargs accepted by bedrock_agentcore.evaluation.ReferenceInputs."""
    kwargs: dict[str, Any] = {}
    expected_response = scenario.get("expected_response")
    expected_trajectory = scenario.get("expected_trajectory") or []
    assertions = scenario.get("assertions") or []
    if expected_response:
        kwargs["expected_response"] = expected_response
    if expected_trajectory:
        kwargs["expected_trajectory"] = list(expected_trajectory)
    if assertions:
        kwargs["assertions"] = list(assertions)
    validate_no_sensitive_values(kwargs)
    return kwargs


def gateway_qualified_tool_names(
    tool_names: Sequence[str],
    *,
    gateway_target_prefix: str = "ProductTools___",
) -> list[str]:
    """Return tool names in the form used by Gateway tool spans."""
    qualified = []
    for tool_name in tool_names:
        text = str(tool_name)
        qualified.append(text if "___" in text else f"{gateway_target_prefix}{text}")
    return qualified


def batch_dataset_from_ground_truth(
    ground_truth_artifact: Mapping[str, Any],
    *,
    gateway_target_prefix: str = "ProductTools___",
) -> Any:
    """Build a BatchEvaluationRunner Dataset from Section 03 ground truth."""
    from bedrock_agentcore.evaluation import Dataset, PredefinedScenario, Turn

    scenarios = []
    for scenario in ground_truth_artifact.get("scenarios") or []:
        turns = []
        role = scenario.get("role", "customer")
        for setup_turn in scenario.get("setup_turns") or []:
            if setup_turn.get("role") == "user" and setup_turn.get("content"):
                turns.append(Turn(input={"prompt": setup_turn["content"], "role": role}))
        turns.append(
            Turn(
                input={"prompt": scenario.get("prompt", ""), "role": role},
                expected_response=scenario.get("expected_response"),
            )
        )
        expected_trajectory = gateway_qualified_tool_names(
            scenario.get("expected_trajectory") or [],
            gateway_target_prefix=gateway_target_prefix,
        )
        scenarios.append(
            PredefinedScenario(
                scenario_id=str(scenario["scenario_id"]),
                turns=turns,
                expected_trajectory=expected_trajectory or None,
                assertions=list(scenario.get("assertions") or []) or None,
                metadata={
                    "role": role,
                    "source_test_case_id": scenario.get("source_test_case_id"),
                    "category": scenario.get("category"),
                },
            )
        )

    if not scenarios:
        raise DeploymentContractError("Batch evaluation dataset has no scenarios")
    return Dataset(scenarios=scenarios)


def evaluator_ids_for_scenario(scenario: Mapping[str, Any]) -> list[str]:
    evaluator_ids = scenario.get("evaluator_ids") or []
    if evaluator_ids:
        return [str(evaluator_id) for evaluator_id in evaluator_ids]
    ids = ["Builtin.GoalSuccessRate", "Builtin.Helpfulness"]
    if scenario.get("expected_response"):
        ids.insert(0, "Builtin.Correctness")
    if scenario.get("expected_trajectory"):
        ids.append("Builtin.TrajectoryAnyOrderMatch")
    return ids


def validate_safe_trace_attributes(attrs: Mapping[str, Any]) -> None:
    for key, value in attrs.items():
        if key not in SAFE_TRACE_ATTRIBUTE_KEYS:
            raise DeploymentContractError(f"Unsafe trace attribute key: {key}")
        validate_no_sensitive_values({key: value})


def threshold_for_evaluator(
    evaluator_id: str,
    scenario: Mapping[str, Any],
    default: float = 0.7,
) -> float:
    policy = scenario.get("threshold_policy") or {}
    value = policy.get(evaluator_id)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def load_postdeploy_gate_config(
    path: Path = POSTDEPLOY_GATE_CONFIG_PATH,
) -> dict[str, Any]:
    """Load the Step 14 quality gate policy."""
    if not path.is_file():
        return {
            "version": "default",
            "artifact_type": "section_03_postdeploy_gate_config",
            "default_gate_mode": "blocking",
            "default_evaluator_thresholds": {},
            "source_case_overrides": {},
            "scenario_overrides": {},
        }
    config = load_json(path)
    validate_postdeploy_gate_config(config)
    return config


def validate_postdeploy_gate_config(config: Mapping[str, Any]) -> None:
    if config.get("artifact_type") != "section_03_postdeploy_gate_config":
        raise DeploymentContractError(
            "postdeploy gate config has wrong artifact_type"
        )
    default_mode = str(config.get("default_gate_mode", "blocking"))
    if default_mode not in VALID_GATE_MODES:
        raise DeploymentContractError(f"Invalid default_gate_mode: {default_mode}")

    for evaluator_id, threshold in (config.get("default_evaluator_thresholds") or {}).items():
        if not isinstance(evaluator_id, str) or not isinstance(threshold, (int, float)):
            raise DeploymentContractError("default_evaluator_thresholds must map strings to numbers")

    for override_group in ["source_case_overrides", "scenario_overrides"]:
        overrides = config.get(override_group) or {}
        if not isinstance(overrides, Mapping):
            raise DeploymentContractError(f"{override_group} must be an object")
        for override_key, override in overrides.items():
            if not isinstance(override_key, str) or not isinstance(override, Mapping):
                raise DeploymentContractError(f"{override_group} entries must be objects")
            evaluator_overrides = override.get("evaluator_overrides") or {}
            if not isinstance(evaluator_overrides, Mapping):
                raise DeploymentContractError(
                    f"{override_group}.{override_key}.evaluator_overrides must be an object"
                )
            for evaluator_id, evaluator_override in evaluator_overrides.items():
                if not isinstance(evaluator_id, str) or not isinstance(evaluator_override, Mapping):
                    raise DeploymentContractError("evaluator override entries must be objects")
                threshold = evaluator_override.get("threshold")
                if threshold is not None and not isinstance(threshold, (int, float)):
                    raise DeploymentContractError("evaluator override threshold must be numeric")
                gate_mode = evaluator_override.get("gate_mode")
                if gate_mode is not None and str(gate_mode) not in VALID_GATE_MODES:
                    raise DeploymentContractError(f"Invalid evaluator gate_mode: {gate_mode}")

    validate_no_sensitive_values(config)


def gate_policy_for_evaluator(
    evaluator_id: str,
    scenario: Mapping[str, Any],
    gate_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve threshold and blocking policy for a scenario/evaluator pair."""
    config = gate_config or {}
    threshold = threshold_for_evaluator(evaluator_id, scenario)
    default_thresholds = config.get("default_evaluator_thresholds") or {}
    if isinstance(default_thresholds.get(evaluator_id), (int, float)):
        threshold = float(default_thresholds[evaluator_id])

    gate_mode = str(config.get("default_gate_mode", "blocking"))
    rationale = None

    for override_group, key in [
        ("source_case_overrides", scenario.get("source_test_case_id")),
        ("scenario_overrides", scenario.get("scenario_id")),
    ]:
        if not key:
            continue
        override = (config.get(override_group) or {}).get(str(key)) or {}
        if override.get("rationale"):
            rationale = str(override["rationale"])
        evaluator_override = (override.get("evaluator_overrides") or {}).get(evaluator_id) or {}
        if isinstance(evaluator_override.get("threshold"), (int, float)):
            threshold = float(evaluator_override["threshold"])
        if evaluator_override.get("gate_mode"):
            gate_mode = str(evaluator_override["gate_mode"])
        if evaluator_override.get("rationale"):
            rationale = str(evaluator_override["rationale"])

    if gate_mode not in VALID_GATE_MODES:
        raise DeploymentContractError(f"Invalid resolved gate_mode: {gate_mode}")

    return {
        "threshold": threshold,
        "gate_mode": gate_mode,
        "rationale": rationale,
    }


def summarize_postdeploy_scores(
    scenario_results: Sequence[Mapping[str, Any]],
    *,
    invocation_failures: Sequence[str] = (),
    total_observability_events: int | None = None,
) -> dict[str, Any]:
    failures = list(invocation_failures)
    pending = []
    reviews = []
    scores: list[dict[str, Any]] = []

    for scenario_result in scenario_results:
        scenario_id = scenario_result.get("scenario_id")
        for result in scenario_result.get("results", []):
            evaluator_id = result.get("evaluator_id")
            score = result.get("score")
            threshold = result.get("threshold")
            status = result.get("status")
            gate_mode = result.get("gate_mode", "blocking")
            scores.append(
                {
                    "scenario_id": scenario_id,
                    "evaluator_id": evaluator_id,
                    "score": score,
                    "threshold": threshold,
                    "status": status,
                    "gate_mode": gate_mode,
                }
            )
            if status == "FAIL":
                failures.append(f"{scenario_id}:{evaluator_id} below threshold")
            elif status == "REVIEW":
                reviews.append(f"{scenario_id}:{evaluator_id}:review_only")
            elif status in {"PENDING", "SKIPPED", "ERROR"}:
                pending.append(f"{scenario_id}:{evaluator_id}:{status}")

    if total_observability_events == 0:
        failures.append("zero traces/spans found in CloudWatch")

    if failures:
        gate_status = "FAILED"
    elif pending:
        gate_status = "PENDING"
    elif scores:
        gate_status = "PASSED"
    else:
        gate_status = "SKIPPED"

    return {
        "status": gate_status,
        "scores": scores,
        "failure_reasons": failures,
        "pending_reasons": pending,
        "review_reasons": reviews,
        "total_observability_events": total_observability_events,
    }


def summarize_batch_evaluation_result(batch_result: Any) -> dict[str, Any]:
    """Return a JSON-safe summary from BatchEvaluationRunner output."""
    summary = {
        "batch_evaluation_id": getattr(batch_result, "batch_evaluation_id", None),
        "batch_evaluation_arn": getattr(batch_result, "batch_evaluation_arn", None),
        "batch_evaluation_name": getattr(batch_result, "batch_evaluation_name", None),
        "status": getattr(batch_result, "status", None),
        "created_at": str(getattr(batch_result, "created_at", "")),
        "updated_at": (
            str(getattr(batch_result, "updated_at"))
            if getattr(batch_result, "updated_at", None)
            else None
        ),
        "error_details": getattr(batch_result, "error_details", None) or [],
        "agent_invocation_failures": [
            _model_or_mapping_to_dict(item)
            for item in (getattr(batch_result, "agent_invocation_failures", None) or [])
        ],
        "output_data_config": None,
        "sessions": {},
        "evaluator_summaries": [],
    }

    output_data_config = getattr(batch_result, "output_data_config", None)
    if output_data_config:
        summary["output_data_config"] = _model_or_mapping_to_dict(output_data_config)

    evaluation_results = getattr(batch_result, "evaluation_results", None)
    if evaluation_results:
        summary["sessions"] = {
            "completed": getattr(evaluation_results, "number_of_sessions_completed", None),
            "failed": getattr(evaluation_results, "number_of_sessions_failed", None),
            "ignored": getattr(evaluation_results, "number_of_sessions_ignored", None),
            "in_progress": getattr(
                evaluation_results, "number_of_sessions_in_progress", None
            ),
            "total": getattr(evaluation_results, "total_number_of_sessions", None),
        }
        for evaluator_summary in getattr(evaluation_results, "evaluator_summaries", None) or []:
            statistics = getattr(evaluator_summary, "statistics", None)
            summary["evaluator_summaries"].append(
                {
                    "evaluator_id": getattr(evaluator_summary, "evaluator_id", None),
                    "average_score": (
                        getattr(statistics, "average_score", None)
                        if statistics
                        else None
                    ),
                    "total_evaluated": getattr(
                        evaluator_summary, "total_evaluated", None
                    ),
                }
            )
    validate_no_sensitive_values(summary)
    return summary


def build_batch_evaluation_manifest(
    *,
    deployment_id: str,
    dataset_manifest: Mapping[str, Any],
    batch_result: Any,
    evaluator_ids: Sequence[str],
    scenario_count: int,
    batch_events_count: int | None = None,
) -> dict[str, Any]:
    batch_summary = summarize_batch_evaluation_result(batch_result)
    manifest = {
        "version": "1.0",
        "artifact_type": "section_03_batch_evaluation_manifest",
        "created_at": utc_now(),
        "deployment_id": deployment_id,
        "dataset_lineage_id": dataset_manifest.get("dataset_lineage_id"),
        "managed_datasets": dataset_manifest.get("managed_datasets"),
        "source_section02": dataset_manifest.get("source_section02"),
        "scenario_count": scenario_count,
        "evaluator_ids": list(evaluator_ids),
        "batch_evaluation": batch_summary,
        "batch_events_count": batch_events_count,
    }
    validate_batch_evaluation_manifest(manifest)
    return manifest


def _model_or_mapping_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=False)
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": str(value)}


def validate_batch_evaluation_manifest(manifest: Mapping[str, Any]) -> None:
    for field in [
        "version",
        "artifact_type",
        "deployment_id",
        "dataset_lineage_id",
        "scenario_count",
        "evaluator_ids",
        "batch_evaluation",
    ]:
        if field not in manifest:
            raise DeploymentContractError(f"batch evaluation manifest missing {field}")
    if manifest["artifact_type"] != "section_03_batch_evaluation_manifest":
        raise DeploymentContractError("batch evaluation manifest has wrong artifact_type")
    batch = manifest.get("batch_evaluation") or {}
    if batch.get("status") != "COMPLETED":
        raise DeploymentContractError(
            f"batch evaluation did not complete successfully: {batch.get('status')}"
        )
    if not batch.get("batch_evaluation_id") or not batch.get("batch_evaluation_arn"):
        raise DeploymentContractError("batch evaluation is missing ID or ARN")
    sessions = batch.get("sessions") or {}
    if sessions.get("completed") in {None, 0}:
        raise DeploymentContractError("batch evaluation completed zero sessions")
    if not batch.get("evaluator_summaries"):
        raise DeploymentContractError("batch evaluation has no evaluator summaries")
    validate_no_sensitive_values(manifest)


def build_deployment_manifest(
    *,
    deployment_id: str,
    region: str,
    account_id: str,
    runtime: Mapping[str, Any],
    gateway: Mapping[str, Any],
    cognito: Mapping[str, Any],
    image: Mapping[str, Any],
    model_id: str,
    otel_service_name: str,
    dataset_manifest: Mapping[str, Any] | None = None,
    section02: Mapping[str, Any] | None = None,
    prompt_version: str | None = None,
    tool_policy_version: str | None = None,
    observability: Mapping[str, Any] | None = None,
    quality_gate: Mapping[str, Any] | None = None,
    batch_evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "version": "1.0",
        "artifact_type": "section_03_deployment_manifest",
        "deployment_id": deployment_id,
        "created_at": utc_now(),
        "region": region,
        "account_id": account_id,
        "runtime": dict(runtime),
        "gateway": dict(gateway),
        "cognito": dict(cognito),
        "image": dict(image),
        "model_id": model_id,
        "otel_service_name": otel_service_name,
        "dataset_lineage": _dataset_lineage_summary(dataset_manifest),
        "section02_quality_contract": dict(section02 or {}),
        "agent_behavior": {
            "prompt_version": prompt_version,
            "tool_policy_version": tool_policy_version,
        },
        "observability": dict(observability or {}),
        "postdeploy_quality_gate": dict(quality_gate or {"status": "NOT_RUN"}),
        "batch_evaluation": dict(batch_evaluation or {"status": "NOT_RUN"}),
    }
    validate_deployment_manifest(manifest)
    return manifest


def _dataset_lineage_summary(dataset_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if not dataset_manifest:
        return {
            "dataset_manifest_path": str(DATASET_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "dataset_lineage_id": None,
            "status": "MISSING",
        }
    return {
        "dataset_manifest_path": str(DATASET_MANIFEST_PATH.relative_to(REPO_ROOT)),
        "dataset_lineage_id": dataset_manifest.get("dataset_lineage_id"),
        "source_section02": dataset_manifest.get("source_section02"),
        "managed_datasets": dataset_manifest.get("managed_datasets"),
        "example_counts": dataset_manifest.get("example_counts"),
        "release_gate_scenario_ids": dataset_manifest.get("release_gate_scenario_ids"),
    }


def build_data_protection_policy(log_group_arns: Sequence[str]) -> dict[str, Any]:
    """Build a CloudWatch Logs data protection policy for optional application."""
    if not log_group_arns:
        raise DeploymentContractError("At least one log group ARN is required")
    return {
        "Name": "Section03RuntimeDataProtection",
        "Description": "Mask common sensitive data in Section 03 runtime logs.",
        "Version": "2021-06-01",
        "Statement": [
            {
                "Sid": "Audit",
                "DataIdentifier": [
                    "arn:aws:dataprotection::aws:data-identifier/EmailAddress",
                    "arn:aws:dataprotection::aws:data-identifier/PhoneNumber-US",
                    "arn:aws:dataprotection::aws:data-identifier/AwsSecretKey",
                    "arn:aws:dataprotection::aws:data-identifier/AwsAccessKey",
                ],
                "Operation": {"Audit": {"FindingsDestination": {}}},
            },
            {
                "Sid": "Deidentify",
                "DataIdentifier": [
                    "arn:aws:dataprotection::aws:data-identifier/EmailAddress",
                    "arn:aws:dataprotection::aws:data-identifier/PhoneNumber-US",
                    "arn:aws:dataprotection::aws:data-identifier/AwsSecretKey",
                    "arn:aws:dataprotection::aws:data-identifier/AwsAccessKey",
                ],
                "Operation": {"Deidentify": {"MaskConfig": {}}},
            },
        ],
        "ResourceArn": list(log_group_arns),
    }


def validate_no_sensitive_values(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in DENYLIST_KEY_FRAGMENTS):
                # Metadata should record identifiers, not secret values or demo emails.
                if key_text in {"user_pool_id", "user_client_id"}:
                    validate_no_sensitive_values(item, f"{path}.{key}")
                    continue
                raise DeploymentContractError(f"Sensitive key is not allowed at {path}.{key}")
            validate_no_sensitive_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_sensitive_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        for pattern in PII_OR_SECRET_PATTERNS:
            if pattern.search(value):
                raise DeploymentContractError(f"Sensitive value is not allowed at {path}")


def validate_deployment_manifest(manifest: Mapping[str, Any]) -> None:
    for field in [
        "version",
        "artifact_type",
        "deployment_id",
        "region",
        "account_id",
        "runtime",
        "gateway",
        "image",
        "model_id",
        "otel_service_name",
    ]:
        if field not in manifest:
            raise DeploymentContractError(f"deployment manifest missing {field}")
    if manifest["artifact_type"] != "section_03_deployment_manifest":
        raise DeploymentContractError("deployment manifest has wrong artifact_type")

    runtime = manifest["runtime"]
    gateway = manifest["gateway"]
    image = manifest["image"]
    for field in ["runtime_id", "runtime_arn", "runtime_name"]:
        if not runtime.get(field):
            raise DeploymentContractError(f"runtime metadata missing {field}")
    for field in ["gateway_id", "gateway_url"]:
        if not gateway.get(field):
            raise DeploymentContractError(f"gateway metadata missing {field}")
    if not image.get("repository") or not image.get("tag"):
        raise DeploymentContractError("image metadata missing repository or tag")
    validate_no_sensitive_values(manifest)


def manifest_section02_summary(dataset_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if not dataset_manifest:
        return {}
    return deepcopy(dict(dataset_manifest.get("source_section02") or {}))


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "sample_deployment_id": make_deployment_id(),
                "postdeploy_ground_truth_exists": POSTDEPLOY_GROUND_TRUTH_PATH.is_file(),
                "dataset_manifest_exists": DATASET_MANIFEST_PATH.is_file(),
            },
            indent=2,
        )
    )
