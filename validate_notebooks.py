#!/usr/bin/env python3
"""
Notebook Validation Script for E-Commerce Agent Workshop

Validates all Jupyter notebooks for:
1. Structural integrity (nbformat validation)
2. Source format consistency (string vs list)
3. Stale references from old multi-agent architecture
4. Workshop-specific content checks (correct tool names, evaluator names, etc.)
5. Cell ID presence

Usage:
    # Using project venv (has nbformat):
    ../.venv/bin/python validate_notebooks.py

    # Or with any Python that has nbformat installed:
    python validate_notebooks.py

    # Fix source format inconsistencies:
    ../.venv/bin/python validate_notebooks.py --fix

    # Validate a single notebook:
    ../.venv/bin/python validate_notebooks.py --file 02-evaluation-baseline/02b-strands-evaluation.ipynb
"""

import json
import sys
import os
import re
import argparse
from pathlib import Path

# Try to import nbformat for validation, but work without it
try:
    import nbformat
    HAS_NBFORMAT = True
except ImportError:
    HAS_NBFORMAT = False


# ── Workshop-specific configuration ──────────────────────────────────────────

WORKSHOP_DIR = Path(__file__).parent

# All notebooks to validate (relative to workshop dir)
NOTEBOOK_PATHS = [
    "00-prerequisites/0-environment-setup.ipynb",
    "01-single-agent-prototype/01-single-agent-prototype.ipynb",
    "02-evaluation-baseline/02a-deepeval-evaluation.ipynb",
    "02-evaluation-baseline/02b-strands-evaluation.ipynb",
    "04-online-eval-observability/04-agentcore-evaluations.ipynb",
    "05-production-batch-evaluation/05-production-batch-evaluation.ipynb",
]

# Stale references that should NOT appear in notebook source cells
# (pattern, description, severity)
STALE_PATTERNS = [
    # Old multi-agent architecture
    (r'\border_agent\b', "Reference to removed order_agent", "ERROR"),
    (r'\baccount_agent\b', "Reference to removed account_agent", "ERROR"),
    (r'\bOrderAgent\b', "Reference to removed OrderAgent class", "ERROR"),
    (r'\bAccountAgent\b', "Reference to removed AccountAgent class", "ERROR"),
    (r'OrderTools___', "Old multi-agent tool prefix OrderTools___", "ERROR"),
    (r'AccountTools___', "Old multi-agent tool prefix AccountTools___", "ERROR"),

    # Old tools that don't exist in single agent
    (r'\bget_order_status\b', "Reference to non-existent get_order_status tool", "ERROR"),
    (r'\btrack_shipment\b', "Reference to non-existent track_shipment tool", "ERROR"),
    (r'\bget_customer_info\b', "Reference to non-existent get_customer_info tool", "ERROR"),
    (r'\bupdate_customer\b', "Reference to non-existent update_customer tool", "ERROR"),

    # Old evaluator
    (r'\bRoutingAccuracyEvaluator\b', "Reference to removed RoutingAccuracyEvaluator", "WARNING"),
    (r'\brouting_accuracy\b', "Reference to old routing_accuracy metric", "WARNING"),

    # Old architecture concepts
    (r'multi-agent\s+system', "Reference to multi-agent system (now single agent with RBAC)", "WARNING"),
    (r'multi.agent\s+orchestrat', "Reference to multi-agent orchestrator", "ERROR"),
    (r'three\s+(specialized\s+)?agents', "Reference to three agents", "ERROR"),
    (r'3\s+agents', "Reference to 3 agents", "ERROR"),

    # Old directory name
    (r'01-multi-agent-prototype', "Reference to old directory name", "ERROR"),

    # Bedrock Knowledge Base (not used in single agent)
    (r'Knowledge\s+Base', "Reference to Bedrock Knowledge Base (not used)", "WARNING"),
    (r'\bkb_name\b', "Reference to Knowledge Base name field", "WARNING"),
]

# Valid tool names for the Product Catalog Agent
VALID_TOOLS = {
    # READ tools (customer + admin)
    "search_products", "get_product_details", "check_inventory",
    "get_product_recommendations", "compare_products", "get_return_policy",
    # WRITE tools (admin only)
    "create_product", "update_product", "delete_product",
    "update_inventory", "update_pricing",
}

# Valid evaluator names
VALID_EVALUATORS = {
    "GoalSuccessEvaluator", "HelpfulnessEvaluator", "RBACComplianceEvaluator",
    "ToolParameterAccuracyEvaluator", "PolicyComplianceEvaluator",
    "ResponseQualityEvaluator", "CustomerSatisfactionEvaluator",
}


# ── Validation functions ─────────────────────────────────────────────────────

class ValidationResult:
    def __init__(self, notebook_path):
        self.notebook_path = notebook_path
        self.issues = []  # list of (severity, cell_index, message)
        self.stats = {}

    def add(self, severity, cell_index, message):
        self.issues.append((severity, cell_index, message))

    def has_errors(self):
        return any(sev == "ERROR" for sev, _, _ in self.issues)

    def has_warnings(self):
        return any(sev == "WARNING" for sev, _, _ in self.issues)

    def summary(self):
        errors = sum(1 for s, _, _ in self.issues if s == "ERROR")
        warnings = sum(1 for s, _, _ in self.issues if s == "WARNING")
        info = sum(1 for s, _, _ in self.issues if s == "INFO")
        return errors, warnings, info


def validate_structure(nb_data, result):
    """Validate basic notebook JSON structure."""
    # Check required top-level keys
    for key in ["nbformat", "nbformat_minor", "metadata", "cells"]:
        if key not in nb_data:
            result.add("ERROR", None, f"Missing required key: {key}")

    if not isinstance(nb_data.get("cells", []), list):
        result.add("ERROR", None, "cells is not a list")
        return

    result.stats["num_cells"] = len(nb_data["cells"])
    result.stats["code_cells"] = sum(1 for c in nb_data["cells"] if c.get("cell_type") == "code")
    result.stats["markdown_cells"] = sum(1 for c in nb_data["cells"] if c.get("cell_type") == "markdown")

    for i, cell in enumerate(nb_data["cells"]):
        # Check required cell keys
        if "cell_type" not in cell:
            result.add("ERROR", i, "Missing cell_type")
        if "source" not in cell:
            result.add("ERROR", i, "Missing source")
        if "metadata" not in cell:
            result.add("WARNING", i, "Missing metadata field")

        # Code cells need execution_count and outputs
        if cell.get("cell_type") == "code":
            if "execution_count" not in cell:
                result.add("WARNING", i, "Code cell missing execution_count")
            if "outputs" not in cell:
                result.add("WARNING", i, "Code cell missing outputs")


def validate_source_format(nb_data, result):
    """Check source format consistency (string vs list)."""
    string_cells = []
    list_cells = []

    for i, cell in enumerate(nb_data["cells"]):
        src = cell.get("source", "")
        if isinstance(src, str):
            string_cells.append(i)
        elif isinstance(src, list):
            list_cells.append(i)
        else:
            result.add("ERROR", i, f"Source has unexpected type: {type(src).__name__}")

    result.stats["string_source_cells"] = len(string_cells)
    result.stats["list_source_cells"] = len(list_cells)

    # Both formats are valid per nbformat spec, but mixing is inconsistent
    if string_cells and list_cells:
        result.add("INFO", None,
                    f"Mixed source formats: {len(string_cells)} string, {len(list_cells)} list "
                    f"(use --fix to normalize)")


def validate_cell_ids(nb_data, result):
    """Check for cell ID presence and uniqueness."""
    ids_seen = {}
    missing_ids = 0

    for i, cell in enumerate(nb_data["cells"]):
        cell_id = cell.get("id")
        if cell_id is None:
            missing_ids += 1
        else:
            if cell_id in ids_seen:
                result.add("ERROR", i, f"Duplicate cell ID '{cell_id}' (also in cell {ids_seen[cell_id]})")
            ids_seen[cell_id] = i

    result.stats["cells_with_ids"] = len(ids_seen)
    result.stats["cells_without_ids"] = missing_ids

    if missing_ids > 0:
        result.add("INFO", None,
                    f"{missing_ids}/{len(nb_data['cells'])} cells missing IDs "
                    f"(use --fix to generate)")


def validate_stale_references(nb_data, result):
    """Check for references to old multi-agent architecture in source cells."""
    for i, cell in enumerate(nb_data["cells"]):
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)

        # Skip checking saved outputs (they may contain old references from prior runs)
        # Only check source content
        for pattern, description, severity in STALE_PATTERNS:
            matches = re.findall(pattern, src, re.IGNORECASE)
            if matches:
                # Check context: is this in a comment explaining the replacement?
                # Allow patterns like "Replaces RoutingAccuracyEvaluator"
                if "routing_accuracy" in pattern and "replaces" in src.lower():
                    continue
                if "RoutingAccuracy" in pattern and "Replaces" in src:
                    continue
                # Allow ProductTools___ in Module 05 docstring explaining prefix stripping
                if "ProductTools___" in description:
                    context_match = re.search(r'ProductTools___\w+.*strip', src)
                    if context_match:
                        continue

                result.add(severity, i,
                           f"{description}: found '{matches[0]}' in {cell.get('cell_type', '?')} cell")


def validate_nbformat(path, result):
    """Run nbformat validation if available."""
    if not HAS_NBFORMAT:
        result.add("INFO", None, "nbformat not installed, skipping format validation")
        return

    try:
        nb = nbformat.read(str(path), as_version=4)
        nbformat.validate(nb)
        result.stats["nbformat_valid"] = True
    except nbformat.ValidationError as e:
        result.stats["nbformat_valid"] = False
        result.add("ERROR", None, f"nbformat validation failed: {str(e)[:200]}")
    except Exception as e:
        result.add("ERROR", None, f"Error reading notebook: {str(e)[:200]}")


def validate_saved_outputs(nb_data, result):
    """Check saved outputs for stale references (informational only)."""
    stale_output_cells = []
    for i, cell in enumerate(nb_data["cells"]):
        if cell.get("cell_type") != "code":
            continue
        for output in cell.get("outputs", []):
            text = ""
            if "text" in output:
                text = "".join(output["text"]) if isinstance(output["text"], list) else output["text"]
            for data_key in output.get("data", {}):
                content = output["data"][data_key]
                text += "".join(content) if isinstance(content, list) else str(content)

            # Check for old agent names in outputs
            old_patterns = [r'order_agent', r'account_agent', r'orchestrator',
                            r'routing_accuracy', r'OrderTools___', r'AccountTools___']
            for pat in old_patterns:
                if re.search(pat, text, re.IGNORECASE):
                    stale_output_cells.append(i)
                    break

    if stale_output_cells:
        result.add("INFO", None,
                    f"{len(stale_output_cells)} code cells have saved outputs with old references "
                    f"(cells {stale_output_cells[:5]}{'...' if len(stale_output_cells) > 5 else ''}) "
                    f"- these will be replaced on next execution")


# ── Fix functions ────────────────────────────────────────────────────────────

def normalize_source_format(nb_data):
    """Convert all source fields to list format (per nbformat convention)."""
    changes = 0
    for cell in nb_data["cells"]:
        src = cell.get("source", "")
        if isinstance(src, str):
            # Convert string to list of lines, each ending with \n except possibly the last
            if src == "":
                cell["source"] = []
            else:
                lines = src.split("\n")
                # Add \n to all lines except the last (if it's not empty)
                result = []
                for j, line in enumerate(lines):
                    if j < len(lines) - 1:
                        result.append(line + "\n")
                    else:
                        if line:  # Don't add empty trailing line
                            result.append(line)
                cell["source"] = result
            changes += 1
    return changes


def generate_cell_ids(nb_data):
    """Generate missing cell IDs using a simple hash-based approach.

    Also bumps nbformat_minor to 5 if needed, since cell IDs require 4.5+.
    """
    import hashlib
    changes = 0
    existing_ids = {cell.get("id") for cell in nb_data["cells"] if cell.get("id")}

    for i, cell in enumerate(nb_data["cells"]):
        if "id" not in cell or cell["id"] is None:
            # Generate a deterministic ID based on cell index and content
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            hash_input = f"{i}:{cell.get('cell_type', '')}:{src[:100]}"
            cell_id = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
            # Ensure uniqueness
            while cell_id in existing_ids:
                cell_id = hashlib.sha256((cell_id + "x").encode()).hexdigest()[:8]
            cell["id"] = cell_id
            existing_ids.add(cell_id)
            changes += 1

    # Cell IDs require nbformat 4.5+
    if changes > 0 and nb_data.get("nbformat_minor", 0) < 5:
        nb_data["nbformat_minor"] = 5

    return changes


# ── Main ─────────────────────────────────────────────────────────────────────

def validate_notebook(path, fix=False):
    """Run all validations on a single notebook."""
    result = ValidationResult(str(path))

    # Load raw JSON
    try:
        with open(path) as f:
            nb_data = json.load(f)
    except json.JSONDecodeError as e:
        result.add("ERROR", None, f"Invalid JSON: {e}")
        return result

    # Run validations
    validate_structure(nb_data, result)
    validate_source_format(nb_data, result)
    validate_cell_ids(nb_data, result)
    validate_stale_references(nb_data, result)
    validate_saved_outputs(nb_data, result)
    validate_nbformat(path, result)

    # Apply fixes if requested
    if fix:
        src_changes = normalize_source_format(nb_data)
        id_changes = generate_cell_ids(nb_data)

        if src_changes > 0 or id_changes > 0:
            with open(path, "w") as f:
                json.dump(nb_data, f, indent=1, ensure_ascii=False)
                f.write("\n")
            result.add("INFO", None,
                        f"Fixed: normalized {src_changes} source fields, "
                        f"generated {id_changes} cell IDs")

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate workshop Jupyter notebooks")
    parser.add_argument("--fix", action="store_true",
                        help="Fix source format inconsistencies and generate missing cell IDs")
    parser.add_argument("--file", type=str,
                        help="Validate a single notebook (relative to workshop dir)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show all issues including INFO level")
    args = parser.parse_args()

    if args.file:
        paths = [WORKSHOP_DIR / args.file]
    else:
        paths = [WORKSHOP_DIR / p for p in NOTEBOOK_PATHS]

    print("=" * 70)
    print("E-Commerce Agent Workshop - Notebook Validation")
    print("=" * 70)

    if not HAS_NBFORMAT:
        print("\nWARNING: nbformat not installed. Install with: pip install nbformat")
        print("         Some validations will be skipped.\n")

    total_errors = 0
    total_warnings = 0

    for path in paths:
        if not path.exists():
            print(f"\n  SKIP  {path.relative_to(WORKSHOP_DIR)} (file not found)")
            continue

        result = validate_notebook(path, fix=args.fix)
        errors, warnings, info = result.summary()
        total_errors += errors
        total_warnings += warnings

        # Status indicator
        if errors > 0:
            status = "FAIL"
        elif warnings > 0:
            status = "WARN"
        else:
            status = "OK  "

        rel_path = path.relative_to(WORKSHOP_DIR)
        stats = result.stats
        print(f"\n  {status}  {rel_path}")
        print(f"         Cells: {stats.get('num_cells', '?')} "
              f"({stats.get('code_cells', '?')} code, {stats.get('markdown_cells', '?')} markdown)")

        if stats.get("string_source_cells", 0) > 0 and stats.get("list_source_cells", 0) > 0:
            print(f"         Source format: {stats.get('string_source_cells', 0)} string, "
                  f"{stats.get('list_source_cells', 0)} list")

        # Print issues
        for severity, cell_idx, message in result.issues:
            if severity == "INFO" and not args.verbose:
                continue
            cell_str = f"cell[{cell_idx}]" if cell_idx is not None else "global"
            print(f"         [{severity}] {cell_str}: {message}")

    # Summary
    print("\n" + "=" * 70)
    if total_errors > 0:
        print(f"RESULT: {total_errors} errors, {total_warnings} warnings")
        print("        Fix errors before proceeding.")
    elif total_warnings > 0:
        print(f"RESULT: {total_warnings} warnings (no errors)")
    else:
        print("RESULT: All notebooks valid")

    if not args.fix and any(
        r.stats.get("string_source_cells", 0) > 0 and r.stats.get("list_source_cells", 0) > 0
        for r in [validate_notebook(WORKSHOP_DIR / p) for p in NOTEBOOK_PATHS
                   if (WORKSHOP_DIR / p).exists()]
    ):
        print("\nTIP: Run with --fix to normalize source formats and generate cell IDs")

    print("=" * 70)
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
