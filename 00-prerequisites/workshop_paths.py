#!/usr/bin/env python3
"""
Path helpers for Section 00 notebooks and scripts.

Notebook kernels may start in the repository root, the notebook folder, or an
IDE-selected working directory. These helpers resolve the Section 00 directory
before opening local files so workshop cells do not depend on the launch folder.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable


SECTION_NAME = "00-prerequisites"


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _section_candidates(start: Path) -> list[Path]:
    paths: list[Path] = []

    env_section_dir = os.environ.get("WORKSHOP_SECTION_DIR")
    if env_section_dir:
        paths.append(Path(env_section_dir))

    for parent in [start, *start.parents]:
        paths.append(parent)
        paths.append(parent / SECTION_NAME)

    return _unique_paths(paths)


def is_section_dir(path: Path) -> bool:
    """Return True when path looks like the Section 00 workshop directory."""
    return (
        path.is_dir()
        and (path / "sample_data" / "orders.json").is_file()
        and (path / "sample_data" / "accounts.json").is_file()
        and (path / "sample_data" / "products.json").is_file()
        and (path / "setup_infrastructure.py").is_file()
        and (path / "verify_infrastructure.py").is_file()
    )


def find_section_dir(start: str | os.PathLike[str] | None = None) -> Path:
    """Find the Section 00 directory from a notebook or repo working directory."""
    start_path = Path(start or Path.cwd()).expanduser().resolve()
    if start_path.is_file():
        start_path = start_path.parent

    for candidate in _section_candidates(start_path):
        if is_section_dir(candidate):
            return candidate

    raise FileNotFoundError(
        "Could not locate the 00-prerequisites workshop directory. "
        "Open the notebook from the workshop repo root or set WORKSHOP_SECTION_DIR "
        "to the 00-prerequisites folder."
    )


def section_file_path(
    filename: str,
    *,
    section_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Return an existing file path inside the Section 00 directory."""
    path = find_section_dir(section_dir) / filename
    if not path.is_file():
        raise FileNotFoundError(f"Section 00 file not found: {path}")
    return path


def sample_data_path(
    filename: str,
    *,
    section_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Return an existing sample data file path."""
    path = find_section_dir(section_dir) / "sample_data" / filename
    if not path.is_file():
        raise FileNotFoundError(f"Sample data file not found: {path}")
    return path


def read_sample_json(
    filename: str,
    *,
    section_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load one of the Section 00 sample data JSON files."""
    with sample_data_path(filename, section_dir=section_dir).open(
        "r", encoding="utf-8"
    ) as f:
        return json.load(f)
