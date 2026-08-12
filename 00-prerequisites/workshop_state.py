#!/usr/bin/env python3
"""
Local workshop state/resource manifest helper.

The manifest is intentionally local JSON. Section 00 records what it prepares
and verifies, while later sections can add their own resource pointers without
losing fields this helper does not know about yet.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
WORKSHOP_PREFIX = "ecommerce-workshop"
STATE_FILE_NAME = "workshop_state.json"

SECTION_DIR = Path(__file__).resolve().parent
REPO_ROOT = SECTION_DIR.parent

DOWNSTREAM_MANIFEST_PATHS = {
    "dataset": "03-production-deployment/dataset_manifest.json",
    "deployment": "03-production-deployment/deployment_manifest.json",
    "online_evidence": "04-online-eval-observability/online_evidence_manifest.json",
    "dataset_update": "04-online-eval-observability/dataset_update_manifest.json",
    "optimization": "05-agentcore-optimization/optimization_manifest.json",
    "release_decision": "05-agentcore-optimization/release_decision_report.json",
    "promotion": "05-agentcore-optimization/promotion_manifest.json",
}

KNOWN_REQUIRED_CHECK_KEYS = {
    "aws_identity",
    "dynamodb_tables",
    "bedrock_models",
    "ssm_parameters",
}

KNOWN_ADVANCED_CHECK_KEYS = {
    "agentcore_runtime",
    "agentcore_gateway",
    "agentcore_evaluations",
    "managed_datasets",
    "agentcore_optimization",
    "cloudwatch_logs",
    "s3",
    "iam",
}


def utc_now() -> str:
    """Return a compact UTC timestamp for manifest metadata."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def get_state_file_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Return the manifest path, defaulting to 00-prerequisites/workshop_state.json."""
    if path is None:
        return SECTION_DIR / STATE_FILE_NAME
    return Path(path).expanduser()


def default_downstream_manifest_pointers() -> dict[str, dict[str, Any]]:
    """Return known downstream manifest pointer slots without creating them."""
    pointers: dict[str, dict[str, Any]] = {}
    for name, relative_path in DOWNSTREAM_MANIFEST_PATHS.items():
        pointers[name] = {
            "path": relative_path,
            "exists": (REPO_ROOT / relative_path).exists(),
        }
    return pointers


def default_workshop_state() -> dict[str, Any]:
    """Build a new empty state manifest."""
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "workshop": {
            "account_id": None,
            "region": None,
            "prefix": WORKSHOP_PREFIX,
        },
        "resources": {
            "dynamodb_tables": {},
            "ssm_parameters": {},
            "s3_buckets": {},
            "cloudwatch_log_groups": {},
            "iam_roles": {},
            "agentcore": {
                "runtime": {},
                "gateway": {},
                "evaluations": {},
                "managed_datasets": {},
                "optimization": {},
            },
        },
        "verification": {
            "required_checks": {},
            "advanced_checks": {},
        },
        "advanced_capability_checks": {},
        "downstream_manifests": default_downstream_manifest_pointers(),
    }


def deep_merge(base: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    """Merge updates into base recursively while preserving unknown nested fields."""
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = deepcopy(value)
    return base


def ensure_state_defaults(state: Mapping[str, Any]) -> dict[str, Any]:
    """Add any missing known fields while keeping existing and unknown data."""
    merged = default_workshop_state()
    deep_merge(merged, state)
    return merged


def load_workshop_state(
    path: str | os.PathLike[str] | None = None,
    *,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """Load the manifest, optionally creating it when missing."""
    state_path = get_state_file_path(path)
    if not state_path.exists():
        state = default_workshop_state()
        if create_if_missing:
            save_workshop_state(state, state_path)
        return state

    with state_path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    return ensure_state_defaults(loaded)


def load_state_if_exists(
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    """Load the manifest only if it exists; useful for read-only planning."""
    state_path = get_state_file_path(path)
    if not state_path.exists():
        return None
    return load_workshop_state(state_path)


def save_workshop_state(
    state: Mapping[str, Any],
    path: str | os.PathLike[str] | None = None,
) -> Path:
    """Save the manifest with an atomic replace."""
    state_path = get_state_file_path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state_to_write = ensure_state_defaults(state)
    state_to_write["updated_at"] = utc_now()
    temp_path = state_path.with_suffix(state_path.suffix + ".tmp")

    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(state_to_write, f, indent=2, sort_keys=True)
        f.write("\n")

    os.replace(temp_path, state_path)
    return state_path


def create_workshop_state(
    initial_state: Mapping[str, Any] | None = None,
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Create a state file from scratch and return the saved state."""
    state = default_workshop_state()
    if initial_state:
        deep_merge(state, initial_state)
    save_workshop_state(state, path)
    return load_workshop_state(path)


def update_workshop_state(
    updates: Mapping[str, Any],
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load, deep-merge, and save state while preserving unknown fields."""
    state = load_workshop_state(path)
    deep_merge(state, updates)
    save_workshop_state(state, path)
    return load_workshop_state(path)


def replace_known_map_entries(
    existing: Mapping[str, Any] | None,
    current_entries: Mapping[str, Any],
    known_keys: set[str],
) -> dict[str, Any]:
    """Replace current known entries while preserving unknown map entries."""
    updated = deepcopy(dict(existing or {}))
    for key in known_keys:
        updated.pop(key, None)
    for key, value in current_entries.items():
        updated[key] = deepcopy(value)
    return updated


def dynamodb_table_resource(
    *,
    table_name: str,
    logical_name: str,
    region: str,
    account_id: str,
    status: str = "recorded",
    item_count: int | None = None,
) -> dict[str, Any]:
    """Build a manifest entry for a DynamoDB table."""
    resource = {
        "name": table_name,
        "logical_name": logical_name,
        "service": "dynamodb",
        "arn": f"arn:aws:dynamodb:{region}:{account_id}:table/{table_name}",
        "module": "00-prerequisites",
        "status": status,
    }
    if item_count is not None:
        resource["item_count"] = item_count
    return resource


def ssm_parameter_resource(
    *,
    parameter_name: str,
    logical_name: str,
    value: str,
    region: str,
    account_id: str,
    status: str = "recorded",
) -> dict[str, Any]:
    """Build a manifest entry for an SSM parameter."""
    return {
        "name": parameter_name,
        "logical_name": logical_name,
        "service": "ssm",
        "arn": f"arn:aws:ssm:{region}:{account_id}:parameter/{parameter_name}",
        "module": "00-prerequisites",
        "status": status,
        "value": value,
    }


def record_section00_infrastructure(
    *,
    account_id: str,
    region: str,
    prefix: str,
    dynamodb_tables: Mapping[str, str],
    ssm_parameters: Mapping[str, tuple[str, str]],
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Record Section 00 resources and future manifest pointer slots."""
    table_entries = {
        logical_name: dynamodb_table_resource(
            table_name=table_name,
            logical_name=logical_name,
            region=region,
            account_id=account_id,
            status="created_or_reused",
        )
        for logical_name, table_name in dynamodb_tables.items()
    }
    parameter_entries = {
        logical_name: ssm_parameter_resource(
            parameter_name=parameter_name,
            logical_name=logical_name,
            value=value,
            region=region,
            account_id=account_id,
            status="created_or_updated",
        )
        for logical_name, (parameter_name, value) in ssm_parameters.items()
    }

    return update_workshop_state(
        {
            "workshop": {
                "account_id": account_id,
                "region": region,
                "prefix": prefix,
            },
            "resources": {
                "dynamodb_tables": table_entries,
                "ssm_parameters": parameter_entries,
            },
            "downstream_manifests": default_downstream_manifest_pointers(),
        },
        path,
    )


def record_verification_results(
    *,
    account_id: str | None,
    region: str,
    prefix: str,
    required_checks: Mapping[str, Any],
    advanced_checks: Mapping[str, Any],
    advanced_required: bool,
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Record required and advanced verification results."""
    checked_at = utc_now()
    advanced_summary = {
        "required": advanced_required,
        "passed": sum(1 for result in advanced_checks.values() if result.get("ok")),
        "warnings": sum(
            1 for result in advanced_checks.values() if result.get("status") == "warning"
        ),
        "failed": sum(
            1 for result in advanced_checks.values() if result.get("status") == "failed"
        ),
        "total": len(advanced_checks),
    }

    state = load_workshop_state(path)
    deep_merge(
        state,
        {
            "workshop": {
                "account_id": account_id,
                "region": region,
                "prefix": prefix,
            },
            "downstream_manifests": default_downstream_manifest_pointers(),
        },
    )

    verification = state.setdefault("verification", {})
    verification["last_checked_at"] = checked_at
    verification["required_checks"] = replace_known_map_entries(
        verification.get("required_checks"),
        required_checks,
        KNOWN_REQUIRED_CHECK_KEYS,
    )
    verification["advanced_checks"] = replace_known_map_entries(
        verification.get("advanced_checks"),
        advanced_checks,
        KNOWN_ADVANCED_CHECK_KEYS,
    )

    advanced_state = state.setdefault("advanced_capability_checks", {})
    advanced_state["last_checked_at"] = checked_at
    summary = dict(advanced_state.get("summary") or {})
    summary.update(advanced_summary)
    advanced_state["summary"] = summary
    advanced_state["results"] = replace_known_map_entries(
        advanced_state.get("results"),
        advanced_checks,
        KNOWN_ADVANCED_CHECK_KEYS,
    )

    save_workshop_state(state, path)
    return load_workshop_state(path)
