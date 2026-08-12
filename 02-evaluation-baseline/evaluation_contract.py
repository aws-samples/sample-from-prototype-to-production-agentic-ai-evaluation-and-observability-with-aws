#!/usr/bin/env python3
"""
Section 02 local evaluation quality-contract helpers.

This module deliberately stays on local/offline evidence. Section 03 turns
approved evidence into dataset drafts, ground truth, and simulation scenarios.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SECTION_DIR = Path(__file__).resolve().parent
DATASET_PATH = SECTION_DIR / "evaluation_dataset.json"
REGISTRY_PATH = SECTION_DIR / "evaluator_registry.json"
SLICES_PATH = SECTION_DIR / "evaluation_slices.json"
RUN_MANIFEST_PATH = SECTION_DIR / "run_manifest.json"
RELEASE_GATE_EVIDENCE_PATH = SECTION_DIR / "release_gate_evidence.json"

REQUIRED_CUSTOM_EVALUATORS = {
    "goal_success",
    "helpfulness",
    "rbac_compliance",
    "tool_parameter_accuracy",
    "policy_compliance",
    "response_quality",
    "customer_satisfaction",
}

REQUIRED_AGENTCORE_BUILTINS = {
    "agentcore_goal_success_rate": "Builtin.GoalSuccessRate",
    "agentcore_correctness": "Builtin.Correctness",
    "agentcore_helpfulness": "Builtin.Helpfulness",
}

REQUIRED_SLICE_NAMES = {
    "smoke",
    "release_gate",
    "adversarial",
    "agentcore_ondemand",
    "production_feedback",
}

VALID_GATE_ROLES = {"hard_gate", "soft_gate", "trend_signal", "compare_only"}
VALID_RELIABILITY = {"RELIABLE", "MODERATE", "UNRELIABLE", "N/A", "UNKNOWN"}
RELIABILITY_ORDER = {
    "UNKNOWN": 0,
    "UNRELIABLE": 1,
    "MODERATE": 2,
    "RELIABLE": 3,
    "N/A": 99,
}

SAFE_SPAN_ATTRIBUTE_ALLOWLIST = {
    "eval.run_id",
    "eval.dataset_version",
    "eval.slice_name",
    "eval.test_case_id",
    "eval.case_category",
    "eval.case_subcategory",
    "eval.case_difficulty",
    "eval.registry_version",
    "eval.thresholds_version",
    "eval.synthetic",
    "agent.name",
    "agent.role",
    "agent.model_id",
}

DENYLIST_KEY_FRAGMENTS = {
    "ground_truth",
    "reference_answer",
    "expected_tool",
    "expected_tool_parameters",
    "must_have_facts",
    "expected_output",
    "prompt",
    "input_text",
    "response",
    "conversation_history",
    "email",
    "jwt",
    "token",
    "secret",
    "credential",
    "password",
    "access_key",
}

PII_OR_SECRET_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(secret|token|password|credential|jwt)\b"),
]


class EvaluationContractError(ValueError):
    """Raised when Section 02 quality-contract artifacts are invalid."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a JSON object with a clear error message."""
    json_path = Path(path)
    if not json_path.is_file():
        raise EvaluationContractError(f"Missing JSON artifact: {json_path}")
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise EvaluationContractError(f"Invalid JSON in {json_path}: {e}") from e
    if not isinstance(data, dict):
        raise EvaluationContractError(f"JSON artifact must contain an object: {json_path}")
    return data


def save_json(data: Mapping[str, Any], path: str | os.PathLike[str]) -> Path:
    """Save JSON with stable formatting."""
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
        f.write("\n")
    return json_path


def load_dataset(path: str | os.PathLike[str] = DATASET_PATH) -> dict[str, Any]:
    """Load the local evaluation dataset."""
    dataset = load_json(path)
    if "version" not in dataset:
        raise EvaluationContractError("evaluation_dataset.json missing version")
    if not isinstance(dataset.get("test_cases"), list):
        raise EvaluationContractError("evaluation_dataset.json test_cases must be a list")
    return dataset


def dataset_version(dataset: Mapping[str, Any]) -> str:
    """Return the dataset version as a string."""
    return str(dataset.get("version", "unknown"))


def index_test_cases(dataset: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return test cases grouped by ID, preserving duplicates for validation."""
    index: dict[str, list[dict[str, Any]]] = {}
    for test_case in dataset.get("test_cases", []):
        case_id = test_case.get("id")
        if case_id:
            index.setdefault(str(case_id), []).append(test_case)
    return index


def duplicate_test_case_ids(dataset: Mapping[str, Any]) -> dict[str, int]:
    """Return duplicate case IDs and their counts."""
    return {
        case_id: len(cases)
        for case_id, cases in index_test_cases(dataset).items()
        if len(cases) > 1
    }


def load_registry(path: str | os.PathLike[str] = REGISTRY_PATH) -> dict[str, Any]:
    """Load and validate the evaluator registry."""
    registry = load_json(path)
    validate_registry(registry)
    return registry


def registry_by_id(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return registry evaluator entries keyed by evaluator ID."""
    return {
        str(entry["id"]): deepcopy(entry)
        for entry in registry.get("evaluators", [])
    }


def validate_registry(registry: Mapping[str, Any]) -> None:
    """Validate evaluator registry shape and required evaluator coverage."""
    if "version" not in registry:
        raise EvaluationContractError("evaluator_registry.json missing version")
    if "thresholds_version" not in registry:
        raise EvaluationContractError("evaluator_registry.json missing thresholds_version")

    evaluators = registry.get("evaluators")
    if not isinstance(evaluators, list) or not evaluators:
        raise EvaluationContractError("evaluator_registry.json evaluators must be a list")

    seen: set[str] = set()
    for entry in evaluators:
        for field in [
            "id",
            "display_name",
            "implementation",
            "type",
            "input_level",
            "purpose",
            "threshold",
            "gate_role",
            "reliability_policy",
        ]:
            if field not in entry:
                raise EvaluationContractError(
                    f"Evaluator registry entry missing field '{field}': {entry}"
                )
        evaluator_id = str(entry["id"])
        if evaluator_id in seen:
            raise EvaluationContractError(f"Duplicate evaluator ID: {evaluator_id}")
        seen.add(evaluator_id)

        if entry["gate_role"] not in VALID_GATE_ROLES:
            raise EvaluationContractError(
                f"Invalid gate_role for {evaluator_id}: {entry['gate_role']}"
            )

    missing_custom = REQUIRED_CUSTOM_EVALUATORS - seen
    if missing_custom:
        raise EvaluationContractError(
            f"Evaluator registry missing custom evaluators: {sorted(missing_custom)}"
        )

    registry_entries = registry_by_id(registry)
    for evaluator_id, builtin_name in REQUIRED_AGENTCORE_BUILTINS.items():
        if registry_entries.get(evaluator_id, {}).get("implementation") != builtin_name:
            raise EvaluationContractError(
                f"Evaluator registry missing AgentCore built-in {builtin_name}"
            )

    if not any(
        entry["gate_role"] == "hard_gate"
        and entry["type"] == "deterministic_assertion"
        for entry in evaluators
    ):
        raise EvaluationContractError("At least one deterministic hard gate is required")


def load_slices(path: str | os.PathLike[str] = SLICES_PATH) -> dict[str, Any]:
    """Load and validate evaluation slices."""
    slices = load_json(path)
    validate_slices_shape(slices)
    return slices


def validate_slices_shape(slices: Mapping[str, Any]) -> None:
    """Validate slice artifact shape."""
    if "version" not in slices:
        raise EvaluationContractError("evaluation_slices.json missing version")
    slice_map = slices.get("slices")
    if not isinstance(slice_map, dict) or not slice_map:
        raise EvaluationContractError("evaluation_slices.json must define slices")
    missing = REQUIRED_SLICE_NAMES - set(slice_map)
    if missing:
        raise EvaluationContractError(f"Missing required slices: {sorted(missing)}")
    for name, spec in slice_map.items():
        ids = spec.get("test_case_ids", [])
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise EvaluationContractError(f"Slice '{name}' test_case_ids must be strings")


def get_cases_for_slice(
    dataset: Mapping[str, Any],
    slices: Mapping[str, Any],
    slice_name: str,
) -> list[dict[str, Any]]:
    """Resolve a named slice to dataset records.

    Explicit duplicate case IDs are rejected because they are ambiguous evidence.
    The source dataset may still contain duplicates that are not referenced by
    the selected slice.
    """
    validate_slices_shape(slices)
    slice_map = slices["slices"]
    if slice_name not in slice_map:
        raise EvaluationContractError(f"Unknown evaluation slice: {slice_name}")

    index = index_test_cases(dataset)
    selected: list[dict[str, Any]] = []
    for case_id in slice_map[slice_name].get("test_case_ids", []):
        matches = index.get(case_id, [])
        if not matches:
            raise EvaluationContractError(
                f"Slice '{slice_name}' references missing case ID: {case_id}"
            )
        if len(matches) > 1:
            raise EvaluationContractError(
                f"Slice '{slice_name}' references duplicate case ID: {case_id}"
            )
        selected.append(deepcopy(matches[0]))
    return selected


def case_ids_for_slice(
    dataset: Mapping[str, Any],
    slices: Mapping[str, Any],
    slice_name: str,
) -> list[str]:
    """Return selected case IDs for a named slice."""
    return [case["id"] for case in get_cases_for_slice(dataset, slices, slice_name)]


def build_run_manifest(
    *,
    region: str,
    selected_slice: str,
    selected_test_case_ids: Sequence[str],
    dataset: Mapping[str, Any],
    registry: Mapping[str, Any],
    agent_manifest: Mapping[str, Any] | None = None,
    judge_model_id: str | None = None,
    framework: str = "strands-evals",
    module: str = "02-evaluation-baseline",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable manifest for one local baseline run."""
    now = utc_now()
    generated_run_id = run_id or (
        f"section02-{selected_slice}-{now.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
    )

    agent_manifest = dict(agent_manifest or {})
    agent_info = agent_manifest.get("agent", {})
    model_info = agent_manifest.get("model", {})
    config_info = agent_manifest.get("config", {})

    return {
        "schema_version": "1.0",
        "artifact_type": "section_02_local_evaluation_run_manifest",
        "run_id": generated_run_id,
        "timestamp": now,
        "module": module,
        "framework": framework,
        "region": region,
        "dataset_version": dataset_version(dataset),
        "selected_slice": selected_slice,
        "selected_test_case_ids": list(selected_test_case_ids),
        "agent": {
            "name": agent_info.get("name", dataset.get("agent", "Product Catalog Agent")),
            "version": agent_info.get("version"),
            "model_id": model_info.get("model_id"),
            "prompt_version": config_info.get("prompt_version"),
            "tool_policy_version": config_info.get("tool_policy_version"),
            "tool_catalog_version": config_info.get("tool_catalog_version"),
        },
        "judge_model_id": judge_model_id,
        "evaluator_registry_version": registry["version"],
        "thresholds_version": registry["thresholds_version"],
        "notes": [
            "Local/offline Section 02 evidence only.",
            "No cloud dataset construction in this section.",
        ],
    }


def threshold_map(registry: Mapping[str, Any]) -> dict[str, float]:
    """Return evaluator thresholds, excluding compare-only and null thresholds."""
    return {
        entry["id"]: float(entry["threshold"])
        for entry in registry.get("evaluators", [])
        if entry.get("threshold") is not None and entry.get("gate_role") != "compare_only"
    }


def normalize_reliability(verdict: str | None) -> str:
    """Normalize a reliability verdict."""
    normalized = str(verdict or "UNKNOWN").upper()
    return normalized if normalized in VALID_RELIABILITY else "UNKNOWN"


def effective_gate_role(
    evaluator_entry: Mapping[str, Any],
    reliability_summary: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Return effective gate role after applying meta-evaluation reliability."""
    base_role = str(evaluator_entry["gate_role"])
    policy = evaluator_entry.get("reliability_policy", {})
    if base_role in {"compare_only", "trend_signal"}:
        return base_role, "N/A"

    if not policy.get("meta_eval_required"):
        return base_role, "N/A"

    evaluator_id = str(evaluator_entry["id"])
    reliability = normalize_reliability(
        (reliability_summary or {}).get(evaluator_id, {}).get("verdict")
    )
    required = normalize_reliability(policy.get("minimum_verdict_for_gate"))
    if RELIABILITY_ORDER[reliability] >= RELIABILITY_ORDER[required]:
        return base_role, reliability
    return str(policy.get("fallback_gate_role", "trend_signal")), reliability


def build_gate_interpretation(
    *,
    scores: Mapping[str, Any],
    registry: Mapping[str, Any],
    reliability_summary: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Interpret aggregate evaluator scores through gate roles and reliability."""
    interpretations: dict[str, dict[str, Any]] = {}
    for evaluator_id, entry in registry_by_id(registry).items():
        if entry.get("type") == "agentcore_builtin":
            continue
        score = scores.get(evaluator_id)
        threshold = entry.get("threshold")
        effective_role, reliability = effective_gate_role(entry, reliability_summary)
        passed = None
        if score is not None and threshold is not None:
            passed = float(score) >= float(threshold)
        interpretations[evaluator_id] = {
            "score": score,
            "threshold": threshold,
            "configured_gate_role": entry["gate_role"],
            "effective_gate_role": effective_role,
            "reliability": reliability,
            "passed_threshold": passed,
        }
    return interpretations


def _case_name(case: Any) -> str:
    return str(getattr(case, "name", case.get("id") if isinstance(case, Mapping) else ""))


def _case_input(case: Any) -> str:
    return str(getattr(case, "input", case.get("input") if isinstance(case, Mapping) else ""))


def _case_expected_output(case: Any) -> str:
    if hasattr(case, "expected_output"):
        return str(case.expected_output or "")
    if isinstance(case, Mapping):
        return str(case.get("reference_answer") or case.get("ground_truth") or "")
    return ""


def _case_metadata(case: Any) -> dict[str, Any]:
    if hasattr(case, "metadata"):
        return deepcopy(case.metadata)
    if isinstance(case, Mapping):
        return deepcopy(dict(case))
    return {}


def _rows_by_case(results: Any) -> dict[str, dict[str, Any]]:
    if results is None:
        return {}
    if hasattr(results, "to_dict"):
        rows = results.to_dict(orient="records")
    else:
        rows = list(results)
    return {str(row.get("test_case")): dict(row) for row in rows}


def _deterministic_by_case(deterministic_results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(result.get("test_case")): deepcopy(dict(result))
        for result in deterministic_results
    }


def _numeric_scores(row: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for evaluator_id in registry_by_id(registry):
        value = row.get(evaluator_id)
        if isinstance(value, (int, float)):
            scores[evaluator_id] = float(value)
    return scores


def build_release_gate_evidence(
    *,
    selected_cases: Sequence[Any],
    response_cache: Mapping[str, Any],
    trajectory_cache: Mapping[str, Any],
    deterministic_results: Sequence[Mapping[str, Any]],
    results: Any,
    run_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    reliability_summary: Mapping[str, Any] | None = None,
    output_path: str | os.PathLike[str] | None = RELEASE_GATE_EVIDENCE_PATH,
) -> dict[str, Any]:
    """Build and optionally save local release-gate evidence for Section 03a."""
    rows = _rows_by_case(results)
    deterministic_map = _deterministic_by_case(deterministic_results)
    registry_entries = registry_by_id(registry)
    records: list[dict[str, Any]] = []

    for case in selected_cases:
        case_id = _case_name(case)
        metadata = _case_metadata(case)
        row = rows.get(case_id, {})
        det_result = deterministic_map.get(case_id, {})
        evaluator_scores = _numeric_scores(row, registry)

        hard_failures: list[str] = []
        soft_warnings: list[str] = []

        if det_result and not det_result.get("overall_pass", False):
            hard_failures.append("deterministic_expected_behavior")

        score_interpretation = build_gate_interpretation(
            scores=evaluator_scores,
            registry=registry,
            reliability_summary=reliability_summary,
        )
        for evaluator_id, interpretation in score_interpretation.items():
            effective_role = interpretation["effective_gate_role"]
            passed = interpretation["passed_threshold"]
            if passed is False and effective_role == "hard_gate":
                hard_failures.append(evaluator_id)
            elif passed is False and effective_role == "soft_gate":
                soft_warnings.append(evaluator_id)

        if hard_failures:
            decision = "fail"
        elif soft_warnings:
            decision = "human_review_required"
        else:
            decision = "pass"

        record = {
            "source_test_case_id": case_id,
            "source_dataset_version": run_manifest["dataset_version"],
            "run_id": run_manifest["run_id"],
            "selected_slice": run_manifest["selected_slice"],
            "role": metadata.get("role", "customer"),
            "category": metadata.get("category"),
            "subcategory": metadata.get("subcategory"),
            "difficulty": metadata.get("difficulty"),
            "input": _case_input(case),
            "expected_output": _case_expected_output(case),
            "must_have_facts": metadata.get("must_have_facts", []),
            "assertions": {
                "expected_output_contains": metadata.get("expected_output_contains", []),
                "expected_output_not_contains": metadata.get("expected_output_not_contains", []),
                "expected_behavior": metadata.get("expected_behavior", "allow"),
            },
            "expected_tool_trajectory": {
                "expected_tool": metadata.get("expected_tool"),
                "expected_tool_parameters": metadata.get("expected_tool_parameters"),
            },
            "actual_tool_trajectory": deepcopy(trajectory_cache.get(case_id, [])),
            "response_excerpt": str(response_cache.get(case_id, ""))[:500],
            "deterministic_results": det_result,
            "evaluator_scores": {
                evaluator_id: {
                    "score": evaluator_scores.get(evaluator_id),
                    "threshold": registry_entries[evaluator_id].get("threshold"),
                    "configured_gate_role": registry_entries[evaluator_id].get("gate_role"),
                    "gate_interpretation": score_interpretation.get(evaluator_id, {}),
                }
                for evaluator_id in evaluator_scores
            },
            "gate_decision": decision,
            "hard_failures": hard_failures,
            "soft_warnings": soft_warnings,
            "eligible_for_section_03a_ground_truth": decision == "pass",
        }
        records.append(record)

    artifact = {
        "version": "1.0",
        "artifact_type": "section_02_local_release_gate_evidence",
        "run_manifest": deepcopy(dict(run_manifest)),
        "evaluator_registry_version": registry["version"],
        "thresholds_version": registry["thresholds_version"],
        "records": records,
    }

    if output_path:
        save_json(artifact, output_path)
    return artifact


def safe_span_attributes(
    *,
    case: Any,
    run_manifest: Mapping[str, Any],
    agent_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build allowlisted safe span attributes for AgentCore on-demand scoring."""
    metadata = _case_metadata(case)
    agent_info = (agent_manifest or {}).get("agent", {})
    model_info = (agent_manifest or {}).get("model", {})
    attrs = {
        "eval.run_id": run_manifest["run_id"],
        "eval.dataset_version": run_manifest["dataset_version"],
        "eval.slice_name": run_manifest["selected_slice"],
        "eval.test_case_id": _case_name(case),
        "eval.case_category": metadata.get("category", ""),
        "eval.case_subcategory": metadata.get("subcategory", ""),
        "eval.case_difficulty": metadata.get("difficulty", ""),
        "eval.registry_version": run_manifest["evaluator_registry_version"],
        "eval.thresholds_version": run_manifest["thresholds_version"],
        "eval.synthetic": True,
        "agent.name": agent_info.get("name") or run_manifest.get("agent", {}).get("name"),
        "agent.role": metadata.get("role", "customer"),
        "agent.model_id": model_info.get("model_id") or run_manifest.get("agent", {}).get("model_id"),
    }
    validate_safe_span_attributes(attrs)
    return attrs


def validate_safe_span_attributes(attrs: Mapping[str, Any]) -> None:
    """Validate safe trace metadata keys and values."""
    for key, value in attrs.items():
        if key not in SAFE_SPAN_ATTRIBUTE_ALLOWLIST:
            raise EvaluationContractError(f"Unsafe span attribute key: {key}")
        lowered = key.lower()
        if any(fragment in lowered for fragment in DENYLIST_KEY_FRAGMENTS):
            raise EvaluationContractError(f"Denylisted span attribute key: {key}")
        if isinstance(value, str):
            for pattern in PII_OR_SECRET_PATTERNS:
                if pattern.search(value):
                    raise EvaluationContractError(
                        f"Unsafe span attribute value for key {key}"
                    )


def attach_safe_span_attributes(
    adot_spans: Sequence[Mapping[str, Any]],
    attrs: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return ADOT span/log docs with safe correlation metadata attached."""
    validate_safe_span_attributes(attrs)
    enriched: list[dict[str, Any]] = []
    for span in adot_spans:
        span_copy = deepcopy(dict(span))
        span_attributes = span_copy.setdefault("attributes", {})
        if not isinstance(span_attributes, dict):
            raise EvaluationContractError("ADOT span attributes must be a mapping")
        span_attributes.update(attrs)
        enriched.append(span_copy)
    return enriched


def validate_contract_artifacts(
    *,
    dataset_path: str | os.PathLike[str] = DATASET_PATH,
    registry_path: str | os.PathLike[str] = REGISTRY_PATH,
    slices_path: str | os.PathLike[str] = SLICES_PATH,
) -> dict[str, Any]:
    """Validate local Section 02 contract artifacts."""
    dataset = load_dataset(dataset_path)
    registry = load_registry(registry_path)
    slices = load_slices(slices_path)
    resolved_counts = {
        slice_name: len(get_cases_for_slice(dataset, slices, slice_name))
        for slice_name in slices["slices"]
    }
    return {
        "dataset_version": dataset_version(dataset),
        "registry_version": registry["version"],
        "slices_version": slices["version"],
        "duplicate_case_ids": duplicate_test_case_ids(dataset),
        "resolved_slice_counts": resolved_counts,
    }


if __name__ == "__main__":
    summary = validate_contract_artifacts()
    print(json.dumps(summary, indent=2, default=str))
