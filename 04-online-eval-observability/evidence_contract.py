#!/usr/bin/env python3
"""
Section 04 evidence-contract helpers.

Section 04 observes the deployed release candidate, mines reviewable production
feedback candidates, and updates the existing AgentCore managed dataset only
after explicit review.
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
SECTION03_DIR = REPO_ROOT / "03-production-deployment"

DEPLOYMENT_MANIFEST_PATH = SECTION03_DIR / "deployment_manifest.json"
DATASET_MANIFEST_PATH = SECTION03_DIR / "dataset_manifest.json"
BATCH_EVALUATION_MANIFEST_PATH = SECTION03_DIR / "batch_evaluation_manifest.json"

ONLINE_EVIDENCE_MANIFEST_PATH = SECTION_DIR / "online_evidence_manifest.json"
PRODUCTION_FEEDBACK_CANDIDATES_PATH = SECTION_DIR / "production_feedback_candidates.json"
PROMOTED_FEEDBACK_EXAMPLES_PATH = SECTION_DIR / "promoted_feedback_examples.json"
DATASET_UPDATE_MANIFEST_PATH = SECTION_DIR / "dataset_update_manifest.json"

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


class EvidenceContractError(ValueError):
    """Raised when Section 04 evidence artifacts are invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.is_file():
        raise EvidenceContractError(f"Missing JSON artifact: {json_path}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EvidenceContractError(f"JSON artifact must contain an object: {json_path}")
    return data


def save_json(data: Mapping[str, Any], path: str | os.PathLike[str]) -> Path:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return json_path


def load_section03_context() -> dict[str, Any]:
    deployment = load_json(DEPLOYMENT_MANIFEST_PATH)
    dataset = load_json(DATASET_MANIFEST_PATH)
    batch = load_json(BATCH_EVALUATION_MANIFEST_PATH)
    if deployment.get("postdeploy_quality_gate", {}).get("status") != "PASSED":
        raise EvidenceContractError("Section 03 post-deployment quality gate is not PASSED")
    if batch.get("batch_evaluation", {}).get("status") != "COMPLETED":
        raise EvidenceContractError("Section 03 batch evaluation is not COMPLETED")
    return {
        "deployment": deployment,
        "dataset": dataset,
        "batch_evaluation": batch,
    }


def runtime_log_groups(deployment: Mapping[str, Any]) -> list[str]:
    runtime_id = deployment.get("runtime", {}).get("runtime_id")
    configured = (
        deployment.get("observability", {})
        .get("log_delivery", {})
        .get("log_group")
    )
    groups = [
        "aws/spans",
        f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT" if runtime_id else None,
        configured,
    ]
    return [group for group in dict.fromkeys(groups) if group]


def service_names(deployment: Mapping[str, Any]) -> list[str]:
    runtime = deployment.get("runtime", {})
    runtime_name = runtime.get("runtime_name")
    names = [
        deployment.get("otel_service_name"),
        f"{runtime_name}.DEFAULT" if runtime_name else None,
    ]
    ordered = [name for name in dict.fromkeys(names) if name]
    return ordered[-1:] or ordered


def demo_user_suffix(deployment: Mapping[str, Any]) -> str:
    deployment_id = str(deployment.get("deployment_id", ""))
    if "-" in deployment_id:
        return deployment_id.split("-")[-1]
    return uuid.uuid4().hex[:8]


def sanitize_text(value: Any, *, max_length: int = 900) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<email>", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text, flags=re.I)
    text = re.sub(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "<jwt>", text)
    text = re.sub(r"(?i)(password|token|secret|authorization)=?[^\\s,;]+", r"\1=<redacted>", text)
    return text[:max_length]


def validate_no_sensitive_values(value: Any, path: str = "$", *, allow_expected: bool = False) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in DENYLIST_KEY_FRAGMENTS):
                if key_text in {"user_pool_id", "user_client_id"}:
                    validate_no_sensitive_values(item, f"{path}.{key}", allow_expected=allow_expected)
                    continue
                raise EvidenceContractError(f"Sensitive key is not allowed at {path}.{key}")
            validate_no_sensitive_values(item, f"{path}.{key}", allow_expected=allow_expected)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_sensitive_values(item, f"{path}[{index}]", allow_expected=allow_expected)
    elif isinstance(value, str):
        for pattern in PII_OR_SECRET_PATTERNS:
            if pattern.search(value):
                raise EvidenceContractError(f"Sensitive value is not allowed at {path}")


def extract_tool_calls_from_spans(spans: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    session_tools: dict[str, list[str]] = {}
    for span in spans:
        attrs = span.get("attributes") or {}
        tool_name = attrs.get("gen_ai.tool.name")
        session_id = attrs.get("session.id") or attrs.get("runtime.session_id")
        if not tool_name or not session_id:
            continue
        plain = str(tool_name).split("___")[-1]
        session_tools.setdefault(str(session_id), [])
        if plain not in session_tools[str(session_id)]:
            session_tools[str(session_id)].append(plain)
    return session_tools


def build_online_evidence_manifest(
    *,
    deployment: Mapping[str, Any],
    dataset: Mapping[str, Any],
    batch_evaluation: Mapping[str, Any],
    online_config: Mapping[str, Any],
    dashboard: Mapping[str, Any],
    monitored_sessions: Sequence[Mapping[str, Any]],
    trace_summary: Mapping[str, Any],
    metric_summary: Mapping[str, Any],
    query_templates: Mapping[str, str],
) -> dict[str, Any]:
    manifest = {
        "version": "1.0",
        "artifact_type": "section_04_online_evidence_manifest",
        "created_at": utc_now(),
        "deployment_id": deployment.get("deployment_id"),
        "runtime": deployment.get("runtime"),
        "model_id": deployment.get("model_id"),
        "otel_service_name": deployment.get("otel_service_name"),
        "agent_version": deployment.get("agent_behavior"),
        "dataset_lineage": deployment.get("dataset_lineage"),
        "release_candidate_batch_evaluation": {
            "manifest_path": str(BATCH_EVALUATION_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "batch_evaluation_id": batch_evaluation.get("batch_evaluation", {}).get(
                "batch_evaluation_id"
            ),
            "batch_evaluation_arn": batch_evaluation.get("batch_evaluation", {}).get(
                "batch_evaluation_arn"
            ),
            "evaluator_summaries": batch_evaluation.get("batch_evaluation", {}).get(
                "evaluator_summaries", []
            ),
        },
        "managed_datasets": dataset.get("managed_datasets"),
        "log_groups": runtime_log_groups(deployment),
        "service_names": service_names(deployment),
        "online_evaluation": dict(online_config),
        "dashboard": dict(dashboard),
        "monitored_sessions": deepcopy(list(monitored_sessions)),
        "trace_summary": dict(trace_summary),
        "metric_summary": dict(metric_summary),
        "trace_query_templates": dict(query_templates),
        "status": {
            "online_config_ready": bool(online_config.get("online_evaluation_config_id")),
            "trace_records_found": int(trace_summary.get("span_count", 0)) > 0,
        },
    }
    validate_online_evidence_manifest(manifest)
    return manifest


def build_feedback_candidates(
    *,
    deployment: Mapping[str, Any],
    dataset: Mapping[str, Any],
    monitored_sessions: Sequence[Mapping[str, Any]],
    session_tools: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for item in monitored_sessions:
        if item.get("status") != "success":
            priority = "high"
            reason = "runtime_invocation_error"
        elif item.get("scenario_role") in {"rbac_regression", "recommendation_gap", "comparison_gap"}:
            priority = "medium"
            reason = item.get("scenario_role")
        elif any(word in str(item.get("response", "")).lower() for word in ["sorry", "unable", "not find"]):
            priority = "medium"
            reason = "weak_response_signal"
        else:
            continue

        session_id = str(item.get("session_id"))
        actual_tools = list(session_tools.get(session_id) or item.get("tools_used") or [])
        candidates.append(
            {
                "candidate_id": f"feedback-{session_id[-12:]}",
                "source_session_id": session_id,
                "source_trace_ids": list(item.get("trace_ids") or []),
                "actor_role": item.get("actor_role", "customer"),
                "scenario_role": item.get("scenario_role", "production_feedback_candidate"),
                "sanitized_user_input": sanitize_text(item.get("prompt")),
                "sanitized_agent_output": sanitize_text(item.get("response")),
                "actual_tools": actual_tools,
                "signal_summary": {
                    "priority": priority,
                    "reason": reason,
                    "online_eval_signal": "triage_only",
                },
                "review_status": "needs_review",
                "recommended_for_promotion": (
                    priority in {"high", "medium"}
                    and reason != "runtime_invocation_error"
                ),
                "recommended_for_canary_investigation": reason == "runtime_invocation_error",
            }
        )

    artifact = {
        "version": "1.0",
        "artifact_type": "section_04_production_feedback_candidates",
        "created_at": utc_now(),
        "deployment_id": deployment.get("deployment_id"),
        "dataset_lineage_id": dataset.get("dataset_lineage_id"),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    validate_feedback_candidates(artifact)
    return artifact


def promote_feedback_candidates(
    candidates_artifact: Mapping[str, Any],
    *,
    reviewer: str = "workshop_reviewer",
    max_examples: int = 2,
) -> dict[str, Any]:
    promoted = []
    examples = []
    for candidate in candidates_artifact.get("candidates", []):
        if not candidate.get("recommended_for_promotion"):
            continue
        if candidate.get("signal_summary", {}).get("reason") == "runtime_invocation_error":
            continue
        if len(promoted) >= max_examples:
            break

        candidate_id = candidate["candidate_id"]
        scenario_id = f"prod-feedback-{candidate_id.replace('feedback-', '')}"
        expected_tools = list(candidate.get("actual_tools") or [])
        expected_response = candidate.get("sanitized_agent_output", "")
        assertions = [
            {
                "text": (
                    f"{scenario_id}: reviewed production feedback preserves "
                    f"{candidate.get('scenario_role')} behavior."
                )
            }
        ]
        if expected_tools:
            assertions.append(
                {"text": f"{scenario_id}: agent uses observed tool {', '.join(expected_tools)}."}
            )

        example = {
            "scenario_id": scenario_id,
            "turns": [
                {
                    "input": candidate.get("sanitized_user_input", ""),
                    "expected_response": expected_response,
                }
            ],
            "assertions": assertions,
            "metadata": {
                "source": "section_04_production_feedback",
                "source_candidate_id": candidate_id,
                "source_session_id": candidate.get("source_session_id"),
                "source_trace_ids": candidate.get("source_trace_ids", []),
                "role": candidate.get("actor_role", "customer"),
                "category": candidate.get("scenario_role"),
                "reviewer": reviewer,
                "reviewed_at": utc_now(),
            },
        }
        if expected_tools:
            example["expected_trajectory"] = {"toolNames": expected_tools}

        promoted.append(
            {
                "candidate_id": candidate_id,
                "scenario_id": scenario_id,
                "decision": "promote_to_dataset_draft",
                "reviewer": reviewer,
                "rationale": "Synthetic workshop review accepted this trace as regression coverage.",
                "source_session_id": candidate.get("source_session_id"),
            }
        )
        examples.append(example)

    artifact = {
        "version": "1.0",
        "artifact_type": "section_04_promoted_feedback_examples",
        "created_at": utc_now(),
        "source_candidate_artifact": str(
            PRODUCTION_FEEDBACK_CANDIDATES_PATH.relative_to(REPO_ROOT)
        ),
        "promoted_count": len(promoted),
        "review_decisions": promoted,
        "managed_dataset_examples": examples,
    }
    validate_promoted_feedback_examples(artifact)
    return artifact


def build_dataset_update_manifest(
    *,
    deployment: Mapping[str, Any],
    dataset: Mapping[str, Any],
    promoted_examples: Mapping[str, Any],
    prior_versions: Sequence[Mapping[str, Any]],
    new_versions: Sequence[Mapping[str, Any]],
    add_examples_response: Mapping[str, Any] | None = None,
    publish_response: Mapping[str, Any] | None = None,
    status: str = "UPDATED_AND_PUBLISHED",
) -> dict[str, Any]:
    managed = dataset.get("managed_datasets", {}).get("predefined", {})
    previous_latest = _latest_dataset_version(prior_versions)
    new_latest = _latest_dataset_version(new_versions)
    manifest = {
        "version": "1.0",
        "artifact_type": "section_04_dataset_update_manifest",
        "created_at": utc_now(),
        "deployment_id": deployment.get("deployment_id"),
        "dataset_lineage_id": dataset.get("dataset_lineage_id"),
        "managed_dataset": managed,
        "previous_latest_version": previous_latest,
        "updated_dataset_version": new_latest,
        "added_example_count": promoted_examples.get("promoted_count", 0),
        "added_scenario_ids": [
            item.get("scenario_id")
            for item in promoted_examples.get("managed_dataset_examples", [])
        ],
        "source_session_ids": [
            item.get("source_session_id")
            for item in promoted_examples.get("review_decisions", [])
        ],
        "add_examples_response": _public_response_summary(add_examples_response),
        "publish_response": _public_response_summary(publish_response),
        "status": status,
    }
    validate_dataset_update_manifest(manifest)
    return manifest


def _latest_dataset_version(versions: Sequence[Mapping[str, Any]]) -> str | None:
    numeric = []
    for item in versions:
        text = str(item.get("datasetVersion", ""))
        if text.isdigit():
            numeric.append(int(text))
    return str(max(numeric)) if numeric else None


def _public_response_summary(response: Mapping[str, Any] | None) -> dict[str, Any]:
    if not response:
        return {}
    return {
        key: response.get(key)
        for key in ["datasetId", "datasetArn", "datasetName", "status", "draftStatus", "exampleCount"]
        if key in response
    }


def validate_online_evidence_manifest(manifest: Mapping[str, Any]) -> None:
    for field in [
        "artifact_type",
        "deployment_id",
        "runtime",
        "managed_datasets",
        "online_evaluation",
        "monitored_sessions",
        "trace_summary",
    ]:
        if field not in manifest:
            raise EvidenceContractError(f"online evidence manifest missing {field}")
    if manifest["artifact_type"] != "section_04_online_evidence_manifest":
        raise EvidenceContractError("online evidence manifest has wrong artifact_type")
    validate_no_sensitive_values(manifest)


def validate_feedback_candidates(artifact: Mapping[str, Any]) -> None:
    if artifact.get("artifact_type") != "section_04_production_feedback_candidates":
        raise EvidenceContractError("feedback candidates artifact has wrong artifact_type")
    for candidate in artifact.get("candidates", []):
        for field in ["candidate_id", "source_session_id", "sanitized_user_input", "review_status"]:
            if not candidate.get(field):
                raise EvidenceContractError(f"feedback candidate missing {field}")
    validate_no_sensitive_values(artifact)


def validate_promoted_feedback_examples(artifact: Mapping[str, Any]) -> None:
    if artifact.get("artifact_type") != "section_04_promoted_feedback_examples":
        raise EvidenceContractError("promoted examples artifact has wrong artifact_type")
    for example in artifact.get("managed_dataset_examples", []):
        if not example.get("scenario_id") or not example.get("turns"):
            raise EvidenceContractError("promoted managed example is incomplete")
        validate_no_sensitive_values(example, allow_expected=True)


def validate_dataset_update_manifest(manifest: Mapping[str, Any]) -> None:
    for field in [
        "artifact_type",
        "deployment_id",
        "dataset_lineage_id",
        "managed_dataset",
        "updated_dataset_version",
        "added_example_count",
        "status",
    ]:
        if field not in manifest:
            raise EvidenceContractError(f"dataset update manifest missing {field}")
    if manifest["artifact_type"] != "section_04_dataset_update_manifest":
        raise EvidenceContractError("dataset update manifest has wrong artifact_type")
    if manifest["status"] == "UPDATED_AND_PUBLISHED" and not manifest.get("updated_dataset_version"):
        raise EvidenceContractError("dataset update manifest missing updated version")
    validate_no_sensitive_values(manifest)
