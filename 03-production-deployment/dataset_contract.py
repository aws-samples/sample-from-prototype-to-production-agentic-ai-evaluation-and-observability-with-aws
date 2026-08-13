#!/usr/bin/env python3
"""
Section 03 dataset-contract helpers.

Section 02 produces local evaluation evidence. Section 03 turns approved
evidence into deployable ground truth, simulation scenarios, local mirror
artifacts, and AgentCore DatasetClient payloads.
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
SECTION02_DIR = REPO_ROOT / "02-evaluation-baseline"

SECTION02_RELEASE_GATE_EVIDENCE_PATH = SECTION02_DIR / "release_gate_evidence.json"
SECTION02_RUN_MANIFEST_PATH = SECTION02_DIR / "run_manifest.json"
SECTION02_EVALUATOR_REGISTRY_PATH = SECTION02_DIR / "evaluator_registry.json"
SECTION02_EVALUATION_DATASET_PATH = SECTION02_DIR / "evaluation_dataset.json"

DATASET_MANIFEST_PATH = SECTION_DIR / "dataset_manifest.json"
POSTDEPLOY_GROUND_TRUTH_PATH = SECTION_DIR / "postdeploy_ground_truth.json"
POSTDEPLOY_SIMULATION_SCENARIOS_PATH = SECTION_DIR / "postdeploy_simulation_scenarios.json"

PREDEFINED_SCHEMA = "AGENTCORE_EVALUATION_PREDEFINED_V1"
SIMULATED_SCHEMA = "AGENTCORE_EVALUATION_SIMULATED_V1"

SECTION03_PREDEFINED_HARD_GATE_SOURCE_IDS = {
    "TC-DETAILS-001",
    "TC-ADMIN-007",
    "TC-RBAC-001",
    "TC-OOS-001",
}

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
    re.compile(r"(?i)\b(authorization|bearer|jwt|token|password|secret|credential)\b"),
]


class DatasetContractError(ValueError):
    """Raised when Section 03 dataset artifacts are invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.is_file():
        raise DatasetContractError(f"Missing JSON artifact: {json_path}")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetContractError(f"Invalid JSON in {json_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DatasetContractError(f"JSON artifact must contain an object: {json_path}")
    return data


def save_json(data: Mapping[str, Any], path: str | os.PathLike[str]) -> Path:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return json_path


def load_section02_contract(
    evidence_path: Path = SECTION02_RELEASE_GATE_EVIDENCE_PATH,
    run_manifest_path: Path = SECTION02_RUN_MANIFEST_PATH,
    registry_path: Path = SECTION02_EVALUATOR_REGISTRY_PATH,
    evaluation_dataset_path: Path = SECTION02_EVALUATION_DATASET_PATH,
) -> dict[str, Any]:
    evidence = load_json(evidence_path)
    run_manifest = load_json(run_manifest_path)
    evaluator_registry = load_json(registry_path)
    evaluation_dataset = load_json(evaluation_dataset_path)

    records = evidence.get("records")
    if not isinstance(records, list) or not records:
        raise DatasetContractError("Section 02 release_gate_evidence.json has no records")

    return {
        "release_gate_evidence": evidence,
        "run_manifest": run_manifest,
        "evaluator_registry": evaluator_registry,
        "evaluation_dataset": evaluation_dataset,
    }


def threshold_map(registry: Mapping[str, Any]) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for entry in registry.get("evaluators", []):
        threshold = entry.get("threshold")
        if isinstance(threshold, (int, float)):
            thresholds[str(entry["id"])] = float(threshold)
    return thresholds


def builtin_threshold_policy(registry: Mapping[str, Any]) -> dict[str, float]:
    thresholds = threshold_map(registry)
    return {
        "Builtin.Correctness": thresholds.get("goal_success", 0.7),
        "Builtin.GoalSuccessRate": thresholds.get("goal_success", 0.7),
        "Builtin.Helpfulness": thresholds.get("helpfulness", 0.65),
        "Builtin.TrajectoryAnyOrderMatch": thresholds.get(
            "deterministic_tool_trajectory_rbac", 1.0
        ),
        "Builtin.TrajectoryExactOrderMatch": thresholds.get(
            "deterministic_tool_trajectory_rbac", 1.0
        ),
    }


def eligible_release_gate_records(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [
        deepcopy(record)
        for record in evidence.get("records", [])
        if record.get("eligible_for_section_03a_ground_truth") is True
    ]
    if not records:
        raise DatasetContractError(
            "No Section 02 records are eligible for Section 03a ground truth"
        )
    return records


def requires_stateful_runtime(record: Mapping[str, Any]) -> bool:
    return str(record.get("category", "")).lower() == "multi_turn"


def eligible_predefined_release_gate_records(
    evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Records that can be used as a stable hard gate for the stateless Section 03 runtime."""
    records = [
        record
        for record in eligible_release_gate_records(evidence)
        if not requires_stateful_runtime(record)
        and str(record.get("source_test_case_id")) in SECTION03_PREDEFINED_HARD_GATE_SOURCE_IDS
    ]
    if not records:
        raise DatasetContractError(
            "No Section 02 records are eligible for the Section 03 stateless release gate"
        )
    return records


def excluded_release_gate_records(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_test_case_id": record.get("source_test_case_id"),
            "gate_decision": record.get("gate_decision"),
            "eligible_for_section_03a_ground_truth": record.get(
                "eligible_for_section_03a_ground_truth"
            ),
            "role": record.get("role"),
            "category": record.get("category"),
        }
        for record in evidence.get("records", [])
        if record.get("eligible_for_section_03a_ground_truth") is not True
    ]


def deferred_predefined_release_gate_records(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    deferred = []
    for record in eligible_release_gate_records(evidence):
        source_id = str(record.get("source_test_case_id"))
        if requires_stateful_runtime(record):
            reason = (
                "requires multi-turn runtime memory; retained in simulated scenarios "
                "until Section 03 introduces stateful conversation memory"
            )
        elif source_id not in SECTION03_PREDEFINED_HARD_GATE_SOURCE_IDS:
            reason = (
                "not part of the stable Section 03 deployment hard gate; retained for "
                "simulation, review, or optimization evidence instead of blocking the "
                "live post-deployment gate"
            )
        else:
            continue

        deferred.append(
            {
                "source_test_case_id": record.get("source_test_case_id"),
                "gate_decision": record.get("gate_decision"),
                "eligible_for_section_03a_ground_truth": record.get(
                    "eligible_for_section_03a_ground_truth"
                ),
                "role": record.get("role"),
                "category": record.get("category"),
                "deferred_reason": reason,
            }
        )
    return deferred


def source_case_index(evaluation_dataset: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index = {}
    for test_case in evaluation_dataset.get("test_cases", []):
        case_id = test_case.get("id")
        if case_id and case_id not in index:
            index[str(case_id)] = deepcopy(test_case)
    return index


def setup_turns_from_source_case(source_case: Mapping[str, Any] | None) -> list[dict[str, str]]:
    if not source_case:
        return []
    turns = []
    for item in source_case.get("conversation_history") or []:
        role = item.get("role")
        content = item.get("content")
        if role and content:
            turns.append({"role": str(role), "content": str(content)})
    return turns


def _clean_scenario_id(prefix: str, source_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", source_id).strip("-")
    return f"{prefix}-{cleaned}"


def _expected_tool_names(record: Mapping[str, Any]) -> list[str]:
    trajectory = record.get("expected_tool_trajectory") or {}
    expected_tool = trajectory.get("expected_tool")
    if not expected_tool:
        return []
    return [str(expected_tool)]


def assertion_texts(record: Mapping[str, Any]) -> list[str]:
    assertions: list[str] = []
    source_id = str(record.get("source_test_case_id", "unknown"))
    expected_behavior = (record.get("assertions") or {}).get("expected_behavior")

    if expected_behavior:
        assertions.append(f"{source_id}: expected behavior is {expected_behavior}.")

    for fact in record.get("must_have_facts") or []:
        assertions.append(f"{source_id}: response includes key fact '{fact}'.")

    not_contains = (record.get("assertions") or {}).get("expected_output_not_contains") or []
    for forbidden in not_contains:
        assertions.append(f"{source_id}: response does not include '{forbidden}'.")

    expected_tools = _expected_tool_names(record)
    if expected_tools:
        assertions.append(
            f"{source_id}: agent uses expected tool {', '.join(expected_tools)}."
        )
    elif expected_behavior == "deny":
        assertions.append(
            f"{source_id}: customer request is refused and no admin-only tool is called."
        )

    if not assertions:
        assertions.append(f"{source_id}: response satisfies the release-gate intent.")
    return assertions


def evaluator_ids_for_record(record: Mapping[str, Any]) -> list[str]:
    evaluator_ids = ["Builtin.GoalSuccessRate", "Builtin.Helpfulness"]
    if record.get("expected_output"):
        evaluator_ids.insert(0, "Builtin.Correctness")
    if _expected_tool_names(record):
        evaluator_ids.append("Builtin.TrajectoryAnyOrderMatch")
    return evaluator_ids


def predefined_example_from_record(
    record: Mapping[str, Any],
    registry: Mapping[str, Any],
    source_case: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_id = str(record["source_test_case_id"])
    setup_turns = setup_turns_from_source_case(source_case)
    turns = [
        {"input": turn["content"]}
        for turn in setup_turns
        if turn.get("role") == "user" and turn.get("content")
    ]
    turns.append(
        {
            "input": str(record["input"]),
            **(
                {"expected_response": str(record["expected_output"])}
                if record.get("expected_output")
                else {}
            ),
        }
    )
    example: dict[str, Any] = {
        "scenario_id": _clean_scenario_id("release-gate", source_id),
        "turns": turns,
        "assertions": [{"text": text} for text in assertion_texts(record)],
        "metadata": {
            "source_test_case_id": source_id,
            "source_dataset_version": record.get("source_dataset_version"),
            "source_run_id": record.get("run_id"),
            "selected_slice": record.get("selected_slice"),
            "role": record.get("role"),
            "category": record.get("category"),
            "subcategory": record.get("subcategory"),
            "difficulty": record.get("difficulty"),
            "gate_decision": record.get("gate_decision"),
            "setup_turn_count": len(setup_turns),
            "evaluator_ids": evaluator_ids_for_record(record),
            "threshold_policy": builtin_threshold_policy(registry),
        },
    }
    expected_tools = _expected_tool_names(record)
    if expected_tools:
        example["expected_trajectory"] = {"toolNames": expected_tools}
    return example


def build_predefined_examples(
    evidence: Mapping[str, Any],
    registry: Mapping[str, Any],
    evaluation_dataset: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    source_cases = source_case_index(evaluation_dataset or {})
    examples = [
        predefined_example_from_record(
            record,
            registry,
            source_case=source_cases.get(str(record.get("source_test_case_id"))),
        )
        for record in eligible_predefined_release_gate_records(evidence)
    ]
    validate_predefined_examples(examples)
    return examples


def simulation_example_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    source_id = str(record["source_test_case_id"])
    role = str(record.get("role", "customer"))
    category = str(record.get("category", "release_gate"))
    return {
        "scenario_id": _clean_scenario_id("sim", source_id),
        "scenario_description": (
            f"{role} actor explores {category} behavior derived from {source_id}"
        ),
        "actor_profile": {
            "traits": {
                "role": role,
                "communication_style": "direct",
                "risk_tolerance": "low" if category in {"rbac_boundary", "adversarial"} else "normal",
            },
            "context": (
                "Synthetic workshop actor. Uses no real customer data. "
                f"Original category: {category}."
            ),
            "goal": str(record.get("input", "")),
        },
        "input": str(record.get("input", "")),
        "max_turns": 3 if category != "multi_turn" else 5,
        "assertions": [{"text": text} for text in assertion_texts(record)],
        "metadata": {
            "source_test_case_id": source_id,
            "source_dataset_version": record.get("source_dataset_version"),
            "role": role,
            "category": category,
            "selected_slice": record.get("selected_slice"),
            "simulation_source": "section_02_release_gate_evidence",
        },
    }


def build_simulation_examples(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    examples = [
        simulation_example_from_record(record)
        for record in eligible_release_gate_records(evidence)
    ]
    validate_simulation_examples(examples)
    return examples


def postdeploy_ground_truth_from_examples(
    examples: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Any],
    evaluation_dataset: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    threshold_policy = builtin_threshold_policy(registry)
    source_cases = source_case_index(evaluation_dataset or {})
    scenarios = []
    for example in examples:
        metadata = dict(example.get("metadata") or {})
        turns = list(example.get("turns") or [])
        first_turn = turns[0] if turns else {}
        final_turn = turns[-1] if turns else {}
        source_case = source_cases.get(str(metadata.get("source_test_case_id")))
        setup_turns = setup_turns_from_source_case(source_case)
        expected_tools = (example.get("expected_trajectory") or {}).get("toolNames", [])
        scenarios.append(
            {
                "scenario_id": example["scenario_id"],
                "source_test_case_id": metadata.get("source_test_case_id"),
                "role": metadata.get("role", "customer"),
                "category": metadata.get("category"),
                "setup_turns": setup_turns,
                "prompt": final_turn.get("input", first_turn.get("input", "")),
                "expected_response": final_turn.get("expected_response"),
                "must_have_facts": (source_case or {}).get("must_have_facts", []),
                "expected_trajectory": expected_tools,
                "assertions": [
                    item["text"]
                    for item in example.get("assertions", [])
                    if isinstance(item, Mapping) and item.get("text")
                ],
                "evaluator_ids": metadata.get("evaluator_ids")
                or evaluator_ids_for_record(
                    {
                        "expected_output": first_turn.get("expected_response"),
                        "expected_tool_trajectory": {
                            "expected_tool": expected_tools[0] if expected_tools else None
                        },
                    }
                ),
                "threshold_policy": threshold_policy,
                "metadata": metadata,
            }
        )

    artifact = {
        "version": "1.0",
        "artifact_type": "section_03_postdeploy_ground_truth_mirror",
        "schema_type": PREDEFINED_SCHEMA,
        "authoritative_source": "AgentCore managed dataset when DatasetClient creation succeeds",
        "scenarios": scenarios,
    }
    validate_postdeploy_ground_truth(artifact)
    return artifact


def simulation_artifact_from_examples(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    artifact = {
        "version": "1.0",
        "artifact_type": "section_03_postdeploy_simulation_scenarios_mirror",
        "schema_type": SIMULATED_SCHEMA,
        "authoritative_source": "AgentCore managed dataset when DatasetClient creation succeeds",
        "scenarios": deepcopy(list(examples)),
    }
    validate_simulation_examples(artifact["scenarios"])
    return artifact


def managed_dataset_source(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"inlineExamples": {"examples": deepcopy(list(examples))}}


def build_dataset_manifest(
    *,
    region: str,
    account_id: str,
    section02_contract: Mapping[str, Any],
    predefined_examples: Sequence[Mapping[str, Any]],
    simulated_examples: Sequence[Mapping[str, Any]],
    managed_predefined_dataset: Mapping[str, Any] | None = None,
    managed_simulated_dataset: Mapping[str, Any] | None = None,
    predefined_baseline_version: str | None = None,
    simulated_baseline_version: str | None = None,
    dataset_lineage_id: str | None = None,
) -> dict[str, Any]:
    evidence = section02_contract["release_gate_evidence"]
    run_manifest = section02_contract["run_manifest"]

    manifest = {
        "version": "1.0",
        "artifact_type": "section_03_dataset_manifest",
        "dataset_lineage_id": dataset_lineage_id or f"dataset-lineage-{uuid.uuid4().hex[:12]}",
        "created_at": utc_now(),
        "region": region,
        "account_id": account_id,
        "source_section02": {
            "run_id": run_manifest.get("run_id"),
            "dataset_version": run_manifest.get("dataset_version"),
            "selected_slice": run_manifest.get("selected_slice"),
            "evaluator_registry_version": evidence.get("evaluator_registry_version"),
            "release_gate_evidence_version": evidence.get("version"),
            "thresholds_version": evidence.get("thresholds_version"),
            "prompt_version": (run_manifest.get("agent") or {}).get("prompt_version"),
            "tool_policy_version": (run_manifest.get("agent") or {}).get(
                "tool_policy_version"
            ),
        },
        "schemas": {
            "predefined": PREDEFINED_SCHEMA,
            "simulated": SIMULATED_SCHEMA,
        },
        "managed_datasets": {
            "predefined": _managed_dataset_pointer(
                managed_predefined_dataset,
                PREDEFINED_SCHEMA,
                predefined_baseline_version,
            ),
            "simulated": _managed_dataset_pointer(
                managed_simulated_dataset,
                SIMULATED_SCHEMA,
                simulated_baseline_version,
            ),
        },
        "local_mirrors": {
            "postdeploy_ground_truth": str(POSTDEPLOY_GROUND_TRUTH_PATH.relative_to(REPO_ROOT)),
            "postdeploy_simulation_scenarios": str(
                POSTDEPLOY_SIMULATION_SCENARIOS_PATH.relative_to(REPO_ROOT)
            ),
        },
        "example_counts": {
            "predefined": len(predefined_examples),
            "simulated": len(simulated_examples),
            "excluded_from_predefined": len(excluded_release_gate_records(evidence)),
            "deferred_from_predefined": len(
                deferred_predefined_release_gate_records(evidence)
            ),
        },
        "release_gate_scenario_ids": [
            str(example["scenario_id"]) for example in predefined_examples
        ],
        "simulated_scenario_ids": [
            str(example["scenario_id"]) for example in simulated_examples
        ],
        "excluded_release_gate_records": excluded_release_gate_records(evidence),
        "deferred_predefined_release_gate_records": deferred_predefined_release_gate_records(
            evidence
        ),
        "status": {
            "draft_created": managed_predefined_dataset is not None,
            "baseline_published": predefined_baseline_version is not None,
            "local_mirrors_written": False,
        },
    }
    validate_dataset_manifest(manifest)
    return manifest


def _managed_dataset_pointer(
    dataset_response: Mapping[str, Any] | None,
    schema_type: str,
    baseline_version: str | None,
) -> dict[str, Any]:
    if not dataset_response:
        return {
            "schema_type": schema_type,
            "dataset_id": None,
            "dataset_arn": None,
            "dataset_name": None,
            "draft_status": "NOT_CREATED",
            "baseline_dataset_version": None,
            "example_count": None,
        }
    return {
        "schema_type": schema_type,
        "dataset_id": dataset_response.get("datasetId"),
        "dataset_arn": dataset_response.get("datasetArn"),
        "dataset_name": dataset_response.get("datasetName"),
        "status": dataset_response.get("status"),
        "draft_status": dataset_response.get("draftStatus"),
        "baseline_dataset_version": baseline_version,
        "example_count": dataset_response.get("exampleCount"),
    }


def write_local_dataset_artifacts(
    *,
    manifest: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
    simulation_scenarios: Mapping[str, Any],
    manifest_path: Path = DATASET_MANIFEST_PATH,
    ground_truth_path: Path = POSTDEPLOY_GROUND_TRUTH_PATH,
    simulation_path: Path = POSTDEPLOY_SIMULATION_SCENARIOS_PATH,
) -> dict[str, Path]:
    updated_manifest = deepcopy(dict(manifest))
    updated_manifest.setdefault("status", {})["local_mirrors_written"] = True
    save_json(ground_truth, ground_truth_path)
    save_json(simulation_scenarios, simulation_path)
    save_json(updated_manifest, manifest_path)
    return {
        "dataset_manifest": manifest_path,
        "postdeploy_ground_truth": ground_truth_path,
        "postdeploy_simulation_scenarios": simulation_path,
    }


def build_local_dataset_artifacts(
    *,
    region: str,
    account_id: str,
    section02_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = dict(section02_contract or load_section02_contract())
    evidence = contract["release_gate_evidence"]
    registry = contract["evaluator_registry"]
    evaluation_dataset = contract.get("evaluation_dataset", {})
    predefined_examples = build_predefined_examples(evidence, registry, evaluation_dataset)
    simulation_examples = build_simulation_examples(evidence)
    ground_truth = postdeploy_ground_truth_from_examples(
        predefined_examples,
        registry,
        evaluation_dataset,
    )
    simulation_scenarios = simulation_artifact_from_examples(simulation_examples)
    manifest = build_dataset_manifest(
        region=region,
        account_id=account_id,
        section02_contract=contract,
        predefined_examples=predefined_examples,
        simulated_examples=simulation_examples,
    )
    return {
        "section02_contract": contract,
        "predefined_examples": predefined_examples,
        "simulation_examples": simulation_examples,
        "postdeploy_ground_truth": ground_truth,
        "postdeploy_simulation_scenarios": simulation_scenarios,
        "dataset_manifest": manifest,
    }


def dataset_client_preflight() -> tuple[bool, Any | None, str | None]:
    try:
        from bedrock_agentcore.evaluation import DatasetClient  # type: ignore

        return True, DatasetClient, None
    except Exception as exc:  # pragma: no cover - depends on installed SDK
        return (
            False,
            None,
            (
                "DatasetClient is not available in the installed bedrock-agentcore "
                f"package: {type(exc).__name__}: {exc}"
            ),
        )


def assert_managed_dataset_ready(manifest: Mapping[str, Any] | None) -> None:
    """Require the managed AgentCore dataset path before Section 03 deployment."""
    if not manifest:
        raise DatasetContractError(
            "Section 03a dataset manifest is missing. Run 03a-ground-truth-dataset.ipynb first."
        )

    status = manifest.get("dataset_client_status") or {}
    status_value = status.get("status")
    if status_value != "CREATED_AND_PUBLISHED":
        reason = status.get("reason") or "managed dataset was not created and published"
        raise DatasetContractError(
            "AgentCore managed dataset is not ready. "
            f"status={status_value or 'UNKNOWN'} reason={reason}. "
            "Update/install an AgentCore SDK that exposes DatasetClient and rerun 03a."
        )

    managed = manifest.get("managed_datasets") or {}
    for name in ["predefined", "simulated"]:
        pointer = managed.get(name) or {}
        if not pointer.get("dataset_id"):
            raise DatasetContractError(f"Managed {name} dataset is missing dataset_id")
        if not pointer.get("baseline_dataset_version"):
            raise DatasetContractError(
                f"Managed {name} dataset is missing baseline_dataset_version"
            )


def validate_no_sensitive_values(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in DENYLIST_KEY_FRAGMENTS):
                raise DatasetContractError(f"Sensitive key is not allowed at {path}.{key}")
            validate_no_sensitive_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_sensitive_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        for pattern in PII_OR_SECRET_PATTERNS:
            if pattern.search(value):
                raise DatasetContractError(f"Sensitive value is not allowed at {path}")


def validate_predefined_examples(examples: Sequence[Mapping[str, Any]]) -> None:
    if not examples:
        raise DatasetContractError("At least one PREDEFINED example is required")
    seen: set[str] = set()
    for example in examples:
        scenario_id = example.get("scenario_id")
        if not scenario_id:
            raise DatasetContractError("PREDEFINED example missing scenario_id")
        if scenario_id in seen:
            raise DatasetContractError(f"Duplicate scenario_id: {scenario_id}")
        seen.add(str(scenario_id))
        turns = example.get("turns")
        if not isinstance(turns, list) or not turns:
            raise DatasetContractError(f"{scenario_id} missing turns")
        if not turns[0].get("input"):
            raise DatasetContractError(f"{scenario_id} first turn missing input")
        if not example.get("assertions"):
            raise DatasetContractError(f"{scenario_id} missing assertions")
        validate_no_sensitive_values(example)


def validate_simulation_examples(examples: Sequence[Mapping[str, Any]]) -> None:
    if not examples:
        raise DatasetContractError("At least one SIMULATED example is required")
    for example in examples:
        scenario_id = example.get("scenario_id")
        if not scenario_id:
            raise DatasetContractError("SIMULATED example missing scenario_id")
        actor_profile = example.get("actor_profile")
        if not isinstance(actor_profile, Mapping):
            raise DatasetContractError(f"{scenario_id} missing actor_profile")
        if not actor_profile.get("goal"):
            raise DatasetContractError(f"{scenario_id} actor_profile missing goal")
        if not example.get("input"):
            raise DatasetContractError(f"{scenario_id} missing input")
        validate_no_sensitive_values(example)


def validate_postdeploy_ground_truth(artifact: Mapping[str, Any]) -> None:
    scenarios = artifact.get("scenarios")
    if artifact.get("schema_type") != PREDEFINED_SCHEMA:
        raise DatasetContractError("postdeploy ground truth has wrong schema_type")
    if not isinstance(scenarios, list) or not scenarios:
        raise DatasetContractError("postdeploy ground truth has no scenarios")
    for scenario in scenarios:
        for field in ["scenario_id", "role", "prompt", "assertions", "evaluator_ids"]:
            if not scenario.get(field):
                raise DatasetContractError(
                    f"postdeploy scenario missing {field}: {scenario.get('scenario_id')}"
                )
        validate_no_sensitive_values(scenario)


def validate_dataset_manifest(manifest: Mapping[str, Any]) -> None:
    for field in [
        "version",
        "artifact_type",
        "dataset_lineage_id",
        "region",
        "account_id",
        "source_section02",
        "managed_datasets",
        "local_mirrors",
        "example_counts",
    ]:
        if field not in manifest:
            raise DatasetContractError(f"dataset manifest missing {field}")
    if manifest["artifact_type"] != "section_03_dataset_manifest":
        raise DatasetContractError("dataset manifest has wrong artifact_type")
    if manifest["example_counts"]["predefined"] < 1:
        raise DatasetContractError("dataset manifest must include predefined examples")
    validate_no_sensitive_values(manifest)


if __name__ == "__main__":
    region = os.environ.get("AWS_REGION", "us-west-2")
    account_id = os.environ.get("AWS_ACCOUNT_ID", "000000000000")
    artifacts = build_local_dataset_artifacts(region=region, account_id=account_id)
    print(
        json.dumps(
            {
                "predefined_examples": len(artifacts["predefined_examples"]),
                "simulation_examples": len(artifacts["simulation_examples"]),
                "dataset_lineage_id": artifacts["dataset_manifest"]["dataset_lineage_id"],
                "source_section02_run_id": artifacts["dataset_manifest"]["source_section02"][
                    "run_id"
                ],
            },
            indent=2,
        )
    )
