#!/usr/bin/env python3
"""
Configuration loader for the local Product Catalog Agent prototype.

Module 01 stays local-only, but it now exposes the same behavior contract that
later sections can evaluate and reuse: model settings, prompt version, tool
policy version, tool catalog, role mapping, and run metadata.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SECTION_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = SECTION_DIR / "config"


class AgentConfigError(ValueError):
    """Raised when the local agent behavior config is missing or inconsistent."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for manifest metadata."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AgentConfigError(f"Missing configuration file: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise AgentConfigError(f"Invalid JSON in {path}: {e}") from e

    if not isinstance(data, dict):
        raise AgentConfigError(f"Configuration file must contain a JSON object: {path}")
    return data


def _resolve_section_path(relative_path: str, *, section_dir: Path = SECTION_DIR) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return section_dir / path


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


@dataclass(frozen=True)
class AgentBehaviorConfig:
    """Loaded and validated behavior config for the local prototype."""

    section_dir: Path
    agent_config_path: Path
    agent_config: Mapping[str, Any]
    tool_policy_path: Path
    tool_policy: Mapping[str, Any]
    tool_catalog_path: Path
    tool_catalog: Mapping[str, Any]
    prompts: Mapping[str, str]
    prompt_paths: Mapping[str, str]

    @property
    def agent_name(self) -> str:
        return str(self.agent_config["agent_name"])

    @property
    def agent_version(self) -> str:
        return str(self.agent_config["agent_version"])

    @property
    def default_role(self) -> str:
        return str(self.agent_config.get("default_role", "customer"))

    @property
    def prompt_version(self) -> str:
        return str(self.agent_config["prompt_version"])

    @property
    def tool_policy_version(self) -> str:
        return str(self.agent_config["tool_policy_version"])

    @property
    def tool_catalog_version(self) -> str:
        return str(self.agent_config["tool_catalog_version"])

    @property
    def model_config(self) -> dict[str, Any]:
        return deepcopy(dict(self.agent_config["model"]))

    @property
    def mcp_server_config(self) -> dict[str, Any]:
        return deepcopy(dict(self.agent_config["mcp_server"]))

    def normalize_role(self, role: str | None) -> str:
        """Return a known role, falling back to least-privilege customer."""
        requested_role = (role or self.default_role).strip().lower()
        roles = self.tool_policy.get("roles", {})
        if requested_role in roles:
            return requested_role
        return self.default_role

    def tools_for_role(self, role: str | None) -> list[str]:
        """Return allowed tool names for a role after least-privilege fallback."""
        normalized_role = self.normalize_role(role)
        role_config = self.tool_policy["roles"][normalized_role]
        tools = role_config.get("allowed_tools", role_config.get("tools", []))
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            raise AgentConfigError(
                f"Role '{normalized_role}' allowed_tools must be a list of strings"
            )
        return _dedupe(tools)

    def tool_catalog_by_name(self) -> dict[str, dict[str, Any]]:
        """Return tool catalog entries keyed by tool name."""
        return {
            str(tool["name"]): deepcopy(tool)
            for tool in self.tool_catalog.get("tools", [])
        }

    def metadata_for_tools(self, tool_names: list[str]) -> list[dict[str, Any]]:
        """Return JSON-serializable catalog metadata for the named tools."""
        catalog = self.tool_catalog_by_name()
        return [deepcopy(catalog[name]) for name in tool_names if name in catalog]

    def render_prompt(
        self,
        *,
        role: str | None,
        user_name: str,
        user_email: str,
    ) -> str:
        """Render the prompt template for the normalized role."""
        normalized_role = self.normalize_role(role)
        if normalized_role not in self.prompts:
            raise AgentConfigError(f"Missing prompt for role: {normalized_role}")

        available_tools = self.tools_for_role(normalized_role)
        try:
            return self.prompts[normalized_role].format(
                user_name=user_name,
                user_email=user_email,
                user_role=normalized_role,
                available_tools=", ".join(available_tools),
                prompt_version=self.prompt_version,
            )
        except KeyError as e:
            raise AgentConfigError(
                f"Prompt for role '{normalized_role}' has an unknown placeholder: {e}"
            ) from e

    def base_manifest(self) -> dict[str, Any]:
        """Return local behavior-contract metadata shared by per-run manifests."""
        return {
            "schema_version": "1.0",
            "module": "01-single-agent-prototype",
            "execution_mode": "local",
            "local_only": bool(self.agent_config.get("local_only", True)),
            "generated_at": utc_now(),
            "agent": {
                "name": self.agent_name,
                "version": self.agent_version,
                "description": self.agent_config.get("agent_description"),
            },
            "model": self.model_config,
            "config": {
                "agent_config_path": str(self.agent_config_path.relative_to(self.section_dir)),
                "prompt_version": self.prompt_version,
                "prompt_paths": deepcopy(dict(self.prompt_paths)),
                "tool_policy_path": str(self.tool_policy_path.relative_to(self.section_dir)),
                "tool_policy_version": self.tool_policy_version,
                "tool_catalog_path": str(self.tool_catalog_path.relative_to(self.section_dir)),
                "tool_catalog_version": self.tool_catalog_version,
            },
            "mcp_server": self.mcp_server_config,
        }


def validate_behavior_config(config: AgentBehaviorConfig) -> None:
    """Validate the config files as a single behavior contract."""
    agent_config = config.agent_config
    tool_policy = config.tool_policy
    tool_catalog = config.tool_catalog

    required_agent_fields = [
        "schema_version",
        "agent_name",
        "agent_version",
        "default_role",
        "model",
        "mcp_server",
        "prompt_version",
        "prompt_files",
        "tool_policy_version",
        "tool_catalog_version",
    ]
    for field in required_agent_fields:
        if field not in agent_config:
            raise AgentConfigError(f"agent_config.json missing required field: {field}")

    if agent_config["tool_policy_version"] != tool_policy.get("policy_version"):
        raise AgentConfigError(
            "agent_config.json tool_policy_version does not match tool_policy.json"
        )

    if agent_config["tool_catalog_version"] != tool_catalog.get("catalog_version"):
        raise AgentConfigError(
            "agent_config.json tool_catalog_version does not match tool_catalog.json"
        )

    roles = tool_policy.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise AgentConfigError("tool_policy.json must define at least one role")

    if agent_config["default_role"] not in roles:
        raise AgentConfigError("default_role must exist in tool_policy roles")

    catalog_by_name = config.tool_catalog_by_name()
    if not catalog_by_name:
        raise AgentConfigError("tool_catalog.json must include at least one tool")

    for role in roles:
        for tool_name in config.tools_for_role(role):
            if tool_name not in catalog_by_name:
                raise AgentConfigError(
                    f"Role '{role}' references tool missing from catalog: {tool_name}"
                )

    for role, prompt in config.prompts.items():
        for placeholder in [
            "{user_name}",
            "{user_email}",
            "{user_role}",
            "{available_tools}",
            "{prompt_version}",
        ]:
            if placeholder not in prompt:
                raise AgentConfigError(
                    f"Prompt for role '{role}' missing placeholder: {placeholder}"
                )


def load_agent_behavior_config(
    config_dir: str | Path | None = None,
) -> AgentBehaviorConfig:
    """Load and validate Section 01 behavior config."""
    if config_dir is None:
        section_dir = SECTION_DIR
        agent_config_path = CONFIG_DIR / "agent_config.json"
    else:
        supplied = Path(config_dir).expanduser().resolve()
        if supplied.name == "config":
            section_dir = supplied.parent
            agent_config_path = supplied / "agent_config.json"
        else:
            section_dir = supplied
            agent_config_path = supplied / "config" / "agent_config.json"

    agent_config = _load_json(agent_config_path)

    tool_policy_path = _resolve_section_path(
        agent_config.get("tool_policy_file", "config/tool_policy.json"),
        section_dir=section_dir,
    )
    tool_catalog_path = _resolve_section_path(
        agent_config.get("tool_catalog_file", "config/tool_catalog.json"),
        section_dir=section_dir,
    )

    tool_policy = _load_json(tool_policy_path)
    tool_catalog = _load_json(tool_catalog_path)

    prompt_paths: dict[str, str] = {}
    prompts: dict[str, str] = {}
    prompt_files = agent_config.get("prompt_files", {})
    if not isinstance(prompt_files, dict) or not prompt_files:
        raise AgentConfigError("agent_config.json prompt_files must map roles to files")

    for role, relative_path in prompt_files.items():
        prompt_path = _resolve_section_path(str(relative_path), section_dir=section_dir)
        if not prompt_path.is_file():
            raise AgentConfigError(f"Missing prompt file for role '{role}': {prompt_path}")
        prompts[str(role)] = prompt_path.read_text(encoding="utf-8")
        prompt_paths[str(role)] = str(prompt_path.relative_to(section_dir))

    config = AgentBehaviorConfig(
        section_dir=section_dir,
        agent_config_path=agent_config_path,
        agent_config=agent_config,
        tool_policy_path=tool_policy_path,
        tool_policy=tool_policy,
        tool_catalog_path=tool_catalog_path,
        tool_catalog=tool_catalog,
        prompts=prompts,
        prompt_paths=prompt_paths,
    )
    validate_behavior_config(config)
    return config
