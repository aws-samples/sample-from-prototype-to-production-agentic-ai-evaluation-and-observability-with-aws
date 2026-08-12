#!/usr/bin/env python3
"""
Section 05 optimization-contract helpers.

Section 05 consumes Section 03/04 evidence, runs optimization analysis, and
records release decisions. It must not mutate AgentCore datasets.
"""

from __future__ import annotations

import json
import os
import re
import ast
import hashlib
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SECTION_DIR = Path(__file__).resolve().parent
REPO_ROOT = SECTION_DIR.parent
SECTION01_DIR = REPO_ROOT / "01-single-agent-prototype"
SECTION03_DIR = REPO_ROOT / "03-production-deployment"
SECTION04_DIR = REPO_ROOT / "04-online-eval-observability"

DEPLOYMENT_MANIFEST_PATH = SECTION03_DIR / "deployment_manifest.json"
DATASET_MANIFEST_PATH = SECTION03_DIR / "dataset_manifest.json"
BATCH_EVALUATION_MANIFEST_PATH = SECTION03_DIR / "batch_evaluation_manifest.json"
ONLINE_EVIDENCE_MANIFEST_PATH = SECTION04_DIR / "online_evidence_manifest.json"
DATASET_UPDATE_MANIFEST_PATH = SECTION04_DIR / "dataset_update_manifest.json"
PRODUCTION_FEEDBACK_CANDIDATES_PATH = SECTION04_DIR / "production_feedback_candidates.json"
PROMOTED_FEEDBACK_EXAMPLES_PATH = SECTION04_DIR / "promoted_feedback_examples.json"

OPTIMIZATION_MANIFEST_PATH = SECTION_DIR / "optimization_manifest.json"
RELEASE_DECISION_REPORT_PATH = SECTION_DIR / "release_decision_report.json"
PROMOTION_MANIFEST_PATH = SECTION_DIR / "promotion_manifest.json"

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

PII_OR_SECRET_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\b(password|token|secret|authorization|credential)\b"),
]


class OptimizationContractError(ValueError):
    """Raised when Section 05 artifacts are invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.is_file():
        raise OptimizationContractError(f"Missing JSON artifact: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise OptimizationContractError(f"JSON artifact must contain an object: {json_path}")
    return data


def save_json(data: Mapping[str, Any], path: str | os.PathLike[str]) -> Path:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return json_path


def load_upstream_evidence() -> dict[str, Any]:
    evidence = {
        "deployment": load_json(DEPLOYMENT_MANIFEST_PATH),
        "dataset": load_json(DATASET_MANIFEST_PATH),
        "batch_evaluation": load_json(BATCH_EVALUATION_MANIFEST_PATH),
        "online_evidence": load_json(ONLINE_EVIDENCE_MANIFEST_PATH),
        "dataset_update": load_json(DATASET_UPDATE_MANIFEST_PATH),
        "production_feedback_candidates": load_json(PRODUCTION_FEEDBACK_CANDIDATES_PATH),
        "promoted_feedback_examples": load_json(PROMOTED_FEEDBACK_EXAMPLES_PATH),
    }
    if evidence["batch_evaluation"].get("batch_evaluation", {}).get("status") != "COMPLETED":
        raise OptimizationContractError("Section 03 batch baseline is not completed")
    if evidence["dataset_update"].get("status") not in {
        "UPDATED_AND_PUBLISHED",
        "NOOP_ALREADY_PRESENT",
    }:
        raise OptimizationContractError("Section 04 dataset update is not ready")
    validate_evidence_alignment(evidence)
    return evidence


def validate_evidence_alignment(evidence: Mapping[str, Any]) -> None:
    deployment_id = evidence.get("deployment", {}).get("deployment_id")
    if not deployment_id:
        raise OptimizationContractError("Section 03 deployment manifest has no deployment_id")
    for key in ["batch_evaluation", "online_evidence", "dataset_update"]:
        candidate = evidence.get(key, {}).get("deployment_id")
        if candidate and candidate != deployment_id:
            raise OptimizationContractError(
                f"{key} deployment_id does not match Section 03 deployment"
            )

    dataset_lineage_id = evidence.get("dataset", {}).get("dataset_lineage_id")
    for key in ["batch_evaluation", "online_evidence", "dataset_update"]:
        item = evidence.get(key, {})
        candidate = item.get("dataset_lineage_id") or item.get("dataset_lineage", {}).get(
            "dataset_lineage_id"
        )
        if dataset_lineage_id and candidate and candidate != dataset_lineage_id:
            raise OptimizationContractError(
                f"{key} dataset lineage does not match Section 03 dataset"
            )

    online_status = evidence.get("online_evidence", {}).get("status", {})
    if online_status and not online_status.get("online_config_ready"):
        raise OptimizationContractError("Section 04 online evaluation config is not ready")
    if online_status and not online_status.get("trace_records_found"):
        raise OptimizationContractError("Section 04 trace evidence is missing")


def file_sha256(path: str | os.PathLike[str]) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_section01_prompts(agent_config: Mapping[str, Any]) -> dict[str, str]:
    prompts = {}
    for role, rel_path in (agent_config.get("prompt_files") or {}).items():
        prompt_path = SECTION01_DIR / rel_path
        prompts[role] = prompt_path.read_text(encoding="utf-8")
    return prompts


def _runtime_strings_and_docstrings(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments: dict[str, str] = {}
    docstrings: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str):
                        assignments[target.id] = node.value.value
        elif isinstance(node, ast.FunctionDef):
            docstring = ast.get_docstring(node)
            if docstring:
                docstrings[node.name] = docstring
    return assignments, docstrings


def load_current_behavior() -> dict[str, Any]:
    agent_config = load_json(SECTION01_DIR / "config" / "agent_config.json")
    tool_catalog = load_json(SECTION01_DIR / "config" / "tool_catalog.json")
    runtime_agent = SECTION03_DIR / "agents" / "product_catalog_agent.py"
    runtime_assignments, runtime_docstrings = _runtime_strings_and_docstrings(runtime_agent)
    prompts = {
        "customer": runtime_assignments.get("CUSTOMER_SYSTEM_PROMPT"),
        "admin": runtime_assignments.get("ADMIN_SYSTEM_PROMPT"),
    }
    if not all(prompts.values()):
        prompts = _read_section01_prompts(agent_config)
    tool_descriptions = {
        item["name"]: runtime_docstrings.get(item["name"]) or item["description"]
        for item in tool_catalog.get("tools", [])
        if item.get("name") and item.get("description")
    }
    source_files = {
        "runtime_agent": str(runtime_agent.relative_to(REPO_ROOT)),
        "section01_agent_config": str((SECTION01_DIR / "config" / "agent_config.json").relative_to(REPO_ROOT)),
        "section01_tool_catalog": str((SECTION01_DIR / "config" / "tool_catalog.json").relative_to(REPO_ROOT)),
    }
    return {
        "prompt_version": agent_config.get("prompt_version"),
        "tool_policy_version": agent_config.get("tool_policy_version"),
        "tool_catalog_version": tool_catalog.get("catalog_version"),
        "system_prompts": prompts,
        "tool_descriptions": tool_descriptions,
        "source": "section03_runtime_source",
        "source_files": source_files,
        "source_hashes": {
            "runtime_agent": file_sha256(runtime_agent),
            "section01_agent_config": file_sha256(SECTION01_DIR / "config" / "agent_config.json"),
            "section01_tool_catalog": file_sha256(SECTION01_DIR / "config" / "tool_catalog.json"),
        },
    }


def load_gateway_tool_descriptions() -> dict[str, str]:
    utils_path = SECTION03_DIR / "utils.py"
    spec = importlib.util.spec_from_file_location("section03_utils", utils_path)
    if not spec or not spec.loader:
        raise OptimizationContractError("Could not load Section 03 Gateway tool schemas")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schemas = module.get_product_tool_schemas()
    descriptions = {
        item["name"]: item["description"]
        for item in schemas
        if item.get("name") and item.get("description")
    }
    if not descriptions:
        raise OptimizationContractError("Section 03 Gateway tool schemas have no descriptions")
    return descriptions


def combined_system_prompt(behavior: Mapping[str, Any]) -> str:
    prompts = behavior.get("system_prompts") or {}
    if not isinstance(prompts, Mapping) or not prompts:
        raise OptimizationContractError("No system prompts found for recommendation")
    chunks = []
    for role, text in sorted(prompts.items()):
        chunks.append(f"## {role}\n{text}")
    return "\n\n".join(chunks)


def recommendation_safe_system_prompt(behavior: Mapping[str, Any]) -> str:
    """Return a compact prompt view that passes recommendation safety checks."""
    categories = [
        "Audio",
        "Wearables",
        "Monitors and Displays",
        "Gaming",
        "Accessories",
        "Cameras",
        "Furniture",
    ]
    return (
        "You are a product catalog assistant for an ecommerce store. "
        "Use catalog tools to answer product search, comparison, inventory, "
        "recommendation, and return-policy questions. "
        "Use administrator-only catalog mutation tools only for administrator users. "
        "Answer with accurate product information from tools and ask for clarification "
        "when product identity is ambiguous. "
        f"The catalog categories are: {', '.join(categories)}. "
        f"Prompt version: {behavior.get('prompt_version') or 'unknown'}. "
        f"Tool policy version: {behavior.get('tool_policy_version') or 'unknown'}."
    )


def log_group_arns(
    *,
    region: str,
    account_id: str,
    log_group_names: Sequence[str],
) -> list[str]:
    if not region or not account_id:
        raise OptimizationContractError("region and account_id are required")
    arns = []
    for name in log_group_names:
        if not name:
            continue
        arns.append(f"arn:aws:logs:{region}:{account_id}:log-group:{name}")
    return arns


def parse_utc_datetime(value: str) -> datetime:
    if not value:
        raise OptimizationContractError("timestamp value is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def derive_insight_trace_window(
    online_evidence: Mapping[str, Any],
    *,
    before_seconds: int = 300,
    after_seconds: int = 120,
) -> dict[str, datetime]:
    """Return a bounded trace window around the Section 04 monitored run."""
    created_at = online_evidence.get("created_at")
    if not created_at:
        raise OptimizationContractError("online evidence manifest has no created_at")
    anchor = parse_utc_datetime(str(created_at))
    return {
        "start_time": anchor - timedelta(seconds=before_seconds),
        "end_time": anchor + timedelta(seconds=after_seconds),
    }


def validate_insights_gate(
    insights: Mapping[str, Any],
    *,
    required_outputs: Sequence[str] = (
        "has_user_intent",
        "has_execution_summary",
    ),
) -> dict[str, Any]:
    failures: dict[str, Any] = {}
    status = insights.get("status")
    if status != "COMPLETED":
        failures["status"] = {
            "observed": status or "UNKNOWN",
            "expected": "COMPLETED",
        }
    error_details = insights.get("error_details") or insights.get("errorDetails") or []
    error_count = insights.get("error_count")
    if error_count is None:
        error_count = len(error_details)
    if error_count:
        failures["errors"] = {
            "error_count": error_count,
            "error_details": list(error_details),
        }
    evaluation_results = (
        insights.get("evaluation_results")
        or insights.get("evaluationResults")
        or {}
    )
    failed_sessions = evaluation_results.get("numberOfSessionsFailed")
    if failed_sessions:
        failures["failed_sessions"] = failed_sessions
    missing_outputs = [
        output_name for output_name in required_outputs if insights.get(output_name) is not True
    ]
    if missing_outputs:
        failures["missing_outputs"] = missing_outputs

    gate = {
        "status": "PASSED" if not failures else "FAILED",
        "required_status": "COMPLETED",
        "required_outputs": list(required_outputs),
        "optional_outputs": ["has_failure_analysis"],
        "failures": failures,
    }
    validate_no_sensitive_values(gate)
    if failures:
        raise OptimizationContractError(
            "Insights gate failed. Do not request recommendations from partial or failed insights."
        )
    return gate


def gateway_qualified_tool_name(tool_name: str, *, prefix: str = "ProductTools___") -> str:
    if "___" in tool_name:
        return tool_name
    return f"{prefix}{tool_name}"


def plain_tool_name(tool_name: str) -> str:
    return tool_name.split("___", 1)[1] if "___" in tool_name else tool_name


def observed_tool_names(
    online_evidence: Mapping[str, Any],
    current_tool_descriptions: Mapping[str, str],
    *,
    limit: int = 3,
) -> list[str]:
    observed: list[str] = []
    valid = set(current_tool_descriptions)
    for session in online_evidence.get("monitored_sessions") or []:
        candidates = list(session.get("tools_used_from_spans") or []) + list(
            session.get("tools_used") or []
        )
        for tool_name in candidates:
            plain = plain_tool_name(str(tool_name))
            if plain in valid and plain not in observed:
                observed.append(plain)

    preferred_order = [
        "check_inventory",
        "compare_products",
        "get_product_details",
        "get_product_recommendations",
        "search_products",
        "get_return_policy",
        "update_inventory",
        "update_pricing",
        "create_product",
        "update_product",
        "delete_product",
    ]
    observed.sort(key=lambda item: preferred_order.index(item) if item in preferred_order else len(preferred_order))
    return observed[:limit]


def build_tool_recommendation_inputs(
    current_tool_descriptions: Mapping[str, str],
    observed_tools: Sequence[str],
    *,
    prefix: str = "ProductTools___",
) -> list[dict[str, Any]]:
    inputs = []
    for tool_name in observed_tools:
        plain = plain_tool_name(str(tool_name))
        description = current_tool_descriptions.get(plain)
        if not description:
            continue
        inputs.append(
            {
                "plain_tool_name": plain,
                "toolName": gateway_qualified_tool_name(plain, prefix=prefix),
                "toolDescription": {"text": description},
            }
        )
    if not inputs:
        raise OptimizationContractError("No observed tools are available for tool recommendation")
    return inputs


def build_bundle_configuration(behavior: Mapping[str, Any]) -> dict[str, Any]:
    configuration = {
        "system_prompts": dict(behavior.get("system_prompts") or {}),
        "tool_descriptions": dict(behavior.get("tool_descriptions") or {}),
        "prompt_version": behavior.get("prompt_version"),
        "tool_policy_version": behavior.get("tool_policy_version"),
        "tool_catalog_version": behavior.get("tool_catalog_version"),
        "source": behavior.get("source"),
        "source_hashes": dict(behavior.get("source_hashes") or {}),
    }
    validate_no_sensitive_values(configuration)
    return configuration


def build_treatment_behavior(
    behavior: Mapping[str, Any],
    *,
    recommended_system_prompt: str | None,
    recommended_tool_descriptions: Mapping[str, str] | None,
) -> dict[str, Any]:
    treatment = {
        "prompt_version": behavior.get("prompt_version"),
        "tool_policy_version": behavior.get("tool_policy_version"),
        "tool_catalog_version": behavior.get("tool_catalog_version"),
        "source": behavior.get("source"),
        "source_hashes": dict(behavior.get("source_hashes") or {}),
        "system_prompts": dict(behavior.get("system_prompts") or {}),
        "tool_descriptions": dict(behavior.get("tool_descriptions") or {}),
    }
    if recommended_system_prompt:
        treatment["system_prompts"] = {
            "recommended_combined": recommended_system_prompt,
        }
    if recommended_tool_descriptions:
        treatment["tool_descriptions"].update(dict(recommended_tool_descriptions))
    validate_no_sensitive_values(treatment)
    return treatment


def detect_config_bundle_readiness(
    runtime_agent_path: Path | None = None,
    deployment_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = runtime_agent_path or (SECTION03_DIR / "agents" / "product_catalog_agent.py")
    text = path.read_text(encoding="utf-8")
    has_context_import = "BedrockAgentCoreContext" in text
    has_bundle_read = "get_config_bundle" in text
    source_supported = has_context_import and has_bundle_read
    deployment = dict(deployment_manifest or {})
    if not deployment and DEPLOYMENT_MANIFEST_PATH.is_file():
        try:
            deployment = load_json(DEPLOYMENT_MANIFEST_PATH)
        except OptimizationContractError:
            deployment = {}
    source_hash = file_sha256(path)
    deployed_hook_version = (
        deployment.get("runtime", {}).get("config_bundle_hook_version")
        or deployment.get("agent_behavior", {}).get("config_bundle_hook_version")
    )
    deployed_source_hash = (
        deployment.get("runtime", {}).get("config_bundle_source_sha256")
        or deployment.get("agent_behavior", {}).get("config_bundle_source_sha256")
    )
    image = deployment.get("image") or {}
    deployment_has_image_evidence = bool(image.get("tag") and image.get("digest"))
    source_hash_matches = bool(deployed_source_hash and deployed_source_hash == source_hash)
    deployed_supported = (
        source_supported
        and str(deployed_hook_version or "") == "1"
        and source_hash_matches
        and deployment_has_image_evidence
    )
    supported = deployed_supported
    try:
        path_label = str(path.relative_to(REPO_ROOT))
    except ValueError:
        path_label = str(path)
    if deployed_supported:
        reason = "deployed runtime reads AgentCore configuration bundles"
    elif source_supported and str(deployed_hook_version or "") == "1":
        reason = (
            "runtime source and deployment marker claim configuration-bundle support, "
            "but deployment source hash or image digest evidence is missing or stale; rerun Section 03"
        )
    elif source_supported:
        reason = (
            "runtime source reads AgentCore configuration bundles, but deployment "
            "manifest does not prove the deployed runtime has hook version 1; rerun Section 03"
        )
    else:
        reason = "runtime does not read AgentCore configuration bundles yet"
    return {
        "supported": supported,
        "source_supported": source_supported,
        "deployed_supported": deployed_supported,
        "deployed_hook_version": deployed_hook_version,
        "source_hash": source_hash,
        "deployed_source_hash": deployed_source_hash,
        "source_hash_matches": source_hash_matches,
        "deployment_has_image_evidence": deployment_has_image_evidence,
        "runtime_agent_path": path_label,
        "required_hook": "BedrockAgentCoreContext.get_config_bundle()",
        "required_deployment_marker": "runtime.config_bundle_hook_version=1",
        "required_source_hash_marker": "runtime.config_bundle_source_sha256",
        "required_image_evidence": "image.tag and image.digest",
        "reason": reason,
    }


def require_config_bundle_ready(readiness: Mapping[str, Any]) -> None:
    if readiness.get("supported") is not True:
        raise OptimizationContractError(
            f"Configuration-bundle experiment blocked: {readiness.get('reason')}"
        )


def recommendation_text_or_fallback(
    recommendation: Mapping[str, Any],
    *,
    fallback_text: str,
    kind: str,
) -> str:
    result = recommendation.get("result") or {}
    if kind == "system_prompt":
        return (
            result.get("recommendedSystemPrompt")
            or result.get("systemPrompt")
            or fallback_text
        )
    return fallback_text


def extract_system_prompt_recommendation(result: Mapping[str, Any]) -> str | None:
    payload = result.get("recommendationResult") or result.get("result") or {}
    prompt_result = payload.get("systemPromptRecommendationResult") or payload
    if prompt_result.get("errorCode"):
        return None
    return prompt_result.get("recommendedSystemPrompt") or prompt_result.get("systemPrompt")


def extract_tool_description_recommendations(
    result: Mapping[str, Any],
    current_tool_descriptions: Mapping[str, str],
) -> dict[str, str]:
    payload = result.get("recommendationResult") or result.get("result") or {}
    tool_result = payload.get("toolDescriptionRecommendationResult") or payload
    if tool_result.get("errorCode"):
        return {}
    returned_tools = tool_result.get("tools") or []
    updated: dict[str, str] = {}
    ordered_names = list(current_tool_descriptions)
    for index, item in enumerate(returned_tools):
        tool_name = item.get("toolName") or (
            ordered_names[index] if index < len(ordered_names) else None
        )
        new_description = item.get("recommendedToolDescription")
        plain = plain_tool_name(str(tool_name)) if tool_name else None
        if plain and new_description and plain in current_tool_descriptions:
            updated[plain] = str(new_description)
    return updated


def validate_recommendation_gate(
    recommendations: Mapping[str, Any],
    *,
    required: Sequence[str] = ("system_prompt", "tool_descriptions"),
) -> dict[str, Any]:
    failures: dict[str, dict[str, Any]] = {}
    for key in required:
        item = recommendations.get(key)
        if not isinstance(item, Mapping):
            failures[key] = {"status": "MISSING"}
            continue
        status = item.get("status")
        if status != "COMPLETED":
            failures[key] = {
                "status": status or "UNKNOWN",
                "recommendation_id": item.get("recommendation_id"),
                "error_code": item.get("error_code"),
                "error_type": item.get("error_type"),
                "reason": "RECOMMENDATION_JOB_NOT_COMPLETED",
            }
            continue
        if item.get("has_candidate") is not True:
            failures[key] = {
                "status": status,
                "recommendation_id": item.get("recommendation_id"),
                "error_code": item.get("error_code"),
                "reason": "NO_RECOMMENDATION_CANDIDATE",
            }

    gate = {
        "status": "PASSED" if not failures else "FAILED",
        "required_recommendations": list(required),
        "failures": failures,
    }
    validate_no_sensitive_values(gate)
    if failures:
        failed_keys = ", ".join(sorted(failures))
        raise OptimizationContractError(
            f"Recommendation gate failed for: {failed_keys}. "
            "Do not create treatment bundles from failed recommendation jobs."
        )
    return gate


def summarize_configuration_bundle_response(response: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "bundle_id": response.get("bundleId"),
        "bundle_arn": response.get("bundleArn"),
        "version_id": response.get("versionId"),
        "status": response.get("status", "CREATED"),
    }
    validate_no_sensitive_values(summary)
    return summary


def blocked_experiment(
    *,
    experiment_type: str,
    reason: str,
    prerequisites: Sequence[str],
    planned_variants: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    experiment = {
        "type": experiment_type,
        "status": "BLOCKED",
        "reason": reason,
        "prerequisites": list(prerequisites),
        "planned_variants": [dict(variant) for variant in planned_variants],
        "promotion_allowed": False,
    }
    validate_no_sensitive_values(experiment)
    return experiment


def dry_run_target_canary_plan(
    *,
    baseline_runtime: Mapping[str, Any],
    candidate_runtime: Mapping[str, Any] | None,
    ci_gate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not candidate_runtime:
        status = "DRY_RUN_NO_CANDIDATE_RUNTIME"
        reason = "No v2 runtime or Gateway target candidate was produced in this workshop run"
    elif not ci_gate or ci_gate.get("status") != "PASSED":
        status = "BLOCKED_PREPROD_GATE"
        reason = "Candidate runtime requires Section 03-style pre-production gate evidence"
    else:
        status = "READY_FOR_CANARY"
        reason = "Candidate runtime has pre-production gate evidence"
    plan = {
        "type": "target_based_canary",
        "status": status,
        "reason": reason,
        "traffic_policy": {"control": 90, "treatment": 10},
        "baseline_runtime": dict(baseline_runtime),
        "candidate_runtime": dict(candidate_runtime or {}),
        "ci_preproduction_gate": dict(ci_gate or {}),
        "promotion_allowed": False,
    }
    validate_no_sensitive_values(plan)
    return plan


def has_completed_experiment_evidence(experiments: Mapping[str, Any]) -> bool:
    completed_statuses = {
        "COMPLETED",
        "COMPLETED_WITH_RESULTS",
        "COMPLETED_WITH_WINNER",
        "PASSED",
        "PROMOTION_READY",
    }
    for experiment in experiments.values():
        if not isinstance(experiment, Mapping):
            continue
        if (
            experiment.get("status") in completed_statuses
            and experiment.get("promotion_allowed") is True
        ):
            return True
    return False


def build_optimization_manifest(
    *,
    evidence: Mapping[str, Any],
    behavior: Mapping[str, Any],
    insights: Mapping[str, Any],
    recommendations: Mapping[str, Any],
    bundle_readiness: Mapping[str, Any],
    configuration_bundles: Mapping[str, Any],
    experiments: Mapping[str, Any],
) -> dict[str, Any]:
    deployment = evidence["deployment"]
    dataset_update = evidence["dataset_update"]
    batch = evidence["batch_evaluation"]
    manifest = {
        "version": "1.0",
        "artifact_type": "section_05_optimization_manifest",
        "created_at": utc_now(),
        "deployment_id": deployment.get("deployment_id"),
        "runtime": deployment.get("runtime"),
        "evidence_inputs": {
            "deployment_manifest": str(DEPLOYMENT_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "dataset_manifest": str(DATASET_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "batch_evaluation_manifest": str(BATCH_EVALUATION_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "online_evidence_manifest": str(ONLINE_EVIDENCE_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "dataset_update_manifest": str(DATASET_UPDATE_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "production_feedback_candidates": str(PRODUCTION_FEEDBACK_CANDIDATES_PATH.relative_to(REPO_ROOT)),
            "promoted_feedback_examples": str(PROMOTED_FEEDBACK_EXAMPLES_PATH.relative_to(REPO_ROOT)),
        },
        "baseline": {
            "batch_evaluation_id": batch.get("batch_evaluation", {}).get("batch_evaluation_id"),
            "batch_evaluation_arn": batch.get("batch_evaluation", {}).get("batch_evaluation_arn"),
            "evaluator_summaries": batch.get("batch_evaluation", {}).get("evaluator_summaries", []),
            "baseline_dataset_version": evidence["dataset"].get("managed_datasets", {})
            .get("predefined", {})
            .get("baseline_dataset_version"),
            "updated_dataset_version": dataset_update.get("updated_dataset_version"),
        },
        "behavior": {
            "prompt_version": behavior.get("prompt_version"),
            "tool_policy_version": behavior.get("tool_policy_version"),
            "tool_catalog_version": behavior.get("tool_catalog_version"),
            "tool_count": len(behavior.get("tool_descriptions", {})),
            "source": behavior.get("source"),
            "source_files": dict(behavior.get("source_files") or {}),
            "source_hashes": dict(behavior.get("source_hashes") or {}),
        },
        "insights": dict(insights),
        "recommendations": dict(recommendations),
        "config_bundle_readiness": dict(bundle_readiness),
        "configuration_bundles": dict(configuration_bundles),
        "experiments": dict(experiments),
    }
    validate_optimization_manifest(manifest)
    return manifest


def build_release_decision_report(
    *,
    optimization_manifest: Mapping[str, Any],
    decision: str,
    rationale: str,
    residual_risks: Sequence[str],
    next_steps: Sequence[str],
) -> dict[str, Any]:
    if decision not in {"promote", "rollback", "continue", "investigate"}:
        raise OptimizationContractError(f"Invalid release decision: {decision}")
    if decision == "promote" and not has_completed_experiment_evidence(
        optimization_manifest.get("experiments") or {}
    ):
        raise OptimizationContractError(
            "Promotion requires completed A/B or canary evidence with promotion_allowed=true"
        )
    report = {
        "version": "1.0",
        "artifact_type": "section_05_release_decision_report",
        "created_at": utc_now(),
        "deployment_id": optimization_manifest.get("deployment_id"),
        "decision": decision,
        "rationale": rationale,
        "baseline": optimization_manifest.get("baseline"),
        "experiment_status": optimization_manifest.get("experiments"),
        "config_bundle_readiness": optimization_manifest.get("config_bundle_readiness"),
        "residual_risks": list(residual_risks),
        "next_steps": list(next_steps),
        "promotion_allowed": decision == "promote",
    }
    validate_release_decision_report(report)
    return report


def build_promotion_manifest(
    *,
    deployment: Mapping[str, Any],
    release_decision: Mapping[str, Any],
    selected_variant: Mapping[str, Any] | None = None,
    promotion_execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    promotion_allowed = release_decision.get("promotion_allowed") is True
    execution = dict(promotion_execution or {})
    promotion_executed = execution.get("promotion_executed") is True
    if promotion_executed and not promotion_allowed:
        raise OptimizationContractError("Promotion execution requires a promote release decision")
    if (
        promotion_executed
        and execution.get("execution_result", {}).get("production_traffic_switched")
        is not True
    ):
        raise OptimizationContractError(
            "Promotion execution must prove production traffic or default behavior was switched"
        )
    manifest = {
        "version": "1.0",
        "artifact_type": "section_05_promotion_manifest",
        "created_at": utc_now(),
        "deployment_id": deployment.get("deployment_id"),
        "status": execution.get("status") or (
            "DRY_RUN_READY" if promotion_allowed else "SKIPPED_NO_PROMOTION"
        ),
        "promotion_executed": promotion_executed,
        "execution_mode": execution.get("execution_mode") or (
            "manual_approval_required" if promotion_allowed else "not_requested"
        ),
        "execution_result": execution.get("execution_result") or {},
        "selected_variant": dict(selected_variant or {}),
        "active_runtime": deployment.get("runtime"),
        "rollback_target": {
            "runtime": deployment.get("runtime"),
            "image": deployment.get("image"),
            "batch_evaluation": deployment.get("batch_evaluation", {}).get("batch_evaluation", {}),
        },
        "monitoring_handoff": {
            "next_section": "04-online-eval-observability",
            "reason": "post-promotion monitoring and feedback mining return to Section 04",
        },
    }
    validate_promotion_manifest(manifest)
    return manifest


def validate_no_sensitive_values(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in DENYLIST_KEY_FRAGMENTS):
                if key_text in {"user_pool_id", "user_client_id"}:
                    validate_no_sensitive_values(item, f"{path}.{key}")
                    continue
                raise OptimizationContractError(f"Sensitive key is not allowed at {path}.{key}")
            validate_no_sensitive_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_sensitive_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        for pattern in PII_OR_SECRET_PATTERNS:
            if pattern.search(value):
                raise OptimizationContractError(f"Sensitive value is not allowed at {path}")


def validate_optimization_manifest(manifest: Mapping[str, Any]) -> None:
    for field in [
        "artifact_type",
        "deployment_id",
        "evidence_inputs",
        "baseline",
        "insights",
        "recommendations",
        "config_bundle_readiness",
        "experiments",
    ]:
        if field not in manifest:
            raise OptimizationContractError(f"optimization manifest missing {field}")
    if manifest["artifact_type"] != "section_05_optimization_manifest":
        raise OptimizationContractError("optimization manifest has wrong artifact_type")
    validate_no_sensitive_values(manifest)


def validate_release_decision_report(report: Mapping[str, Any]) -> None:
    if report.get("artifact_type") != "section_05_release_decision_report":
        raise OptimizationContractError("release decision report has wrong artifact_type")
    if report.get("decision") not in {"promote", "rollback", "continue", "investigate"}:
        raise OptimizationContractError("release decision is invalid")
    validate_no_sensitive_values(report)


def validate_promotion_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("artifact_type") != "section_05_promotion_manifest":
        raise OptimizationContractError("promotion manifest has wrong artifact_type")
    if (
        manifest.get("promotion_executed") is True
        and manifest.get("execution_mode") != "explicit_operator_approved"
    ):
        raise OptimizationContractError("promotion execution requires explicit operator approval")
    validate_no_sensitive_values(manifest)
