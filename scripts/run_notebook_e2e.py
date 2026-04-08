#!/usr/bin/env python3
"""
Run all workshop notebooks end-to-end via papermill.
Produces a summary report at /tmp/nb-outputs/e2e-report.md

Usage:
    python3 scripts/run_notebook_e2e.py

Requires: papermill, ipykernel registered as 'workshop'
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
OUTPUT_DIR = Path("/tmp/nb-outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

REPORT_PATH = OUTPUT_DIR / "e2e-report.md"

# Notebooks in execution order
# (notebook_path relative to repo, working_dir relative to repo, label)
NOTEBOOKS = [
    ("00-prerequisites/0-environment-setup.ipynb", "00-prerequisites", "Module 00: Prerequisites"),
    ("01-single-agent-prototype/01-single-agent-prototype.ipynb", "01-single-agent-prototype", "Module 01: Single Agent"),
    ("02-evaluation-baseline/02b-strands-evaluation.ipynb", "02-evaluation-baseline", "Module 02b: Strands Evaluation"),
    # Module 03 deploys infra - skip for now as runtime already exists
    # ("03-production-deployment/03-production-deployment.ipynb", "03-production-deployment", "Module 03: Production Deployment"),
    # Module 05 needs Module 03+04 artifacts
    # ("05-production-batch-evaluation/05-production-batch-evaluation.ipynb", "05-production-batch-evaluation", "Module 05: Batch Evaluation"),
]

KERNEL = "workshop"
MAX_RETRIES = 2
RETRY_WAIT = 90  # seconds between retries


def run_notebook(nb_path, cwd, label, attempt=1):
    """Run a notebook and return (passed, errors, duration_s)."""
    out_name = nb_path.replace("/", "_").replace(".ipynb", f"_output.ipynb")
    out_path = OUTPUT_DIR / out_name

    abs_nb = str(REPO_ROOT / nb_path)
    abs_cwd = str(REPO_ROOT / cwd)

    print(f"\n{'='*60}")
    print(f"  {label} (attempt {attempt})")
    print(f"  {nb_path}")
    print(f"{'='*60}")

    start = time.time()
    try:
        result = subprocess.run(
            ["papermill", abs_nb, str(out_path), "-k", KERNEL, "--cwd", abs_cwd],
            capture_output=True, text=True, timeout=1800,  # 30 min max per notebook
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return False, [("TIMEOUT", f"Notebook execution exceeded 30 minutes")], duration

    duration = time.time() - start

    # Parse output notebook for errors
    errors = []
    try:
        with open(out_path) as f:
            nb = json.load(f)
        for i, cell in enumerate(nb['cells']):
            if cell['cell_type'] == 'code':
                for output in cell.get('outputs', []):
                    if output.get('output_type') == 'error':
                        ename = output.get('ename', 'Unknown')
                        evalue = output.get('evalue', '')[:200]
                        errors.append((f"Cell {i}: {ename}", evalue))
    except Exception as e:
        errors.append(("ParseError", str(e)[:200]))

    passed = len(errors) == 0
    status = "✅ PASSED" if passed else f"❌ FAILED ({len(errors)} error(s))"
    print(f"  {status} in {duration:.0f}s")
    for ename, evalue in errors:
        print(f"    {ename}: {evalue[:100]}")

    return passed, errors, duration


def main():
    os.chdir(str(REPO_ROOT))
    start_time = datetime.now(timezone.utc)

    print(f"Workshop Notebook E2E Verification")
    print(f"Started: {start_time.isoformat()}")
    print(f"Repo: {REPO_ROOT}")

    results = []

    for nb_path, cwd, label in NOTEBOOKS:
        passed = False
        errors = []
        total_duration = 0

        for attempt in range(1, MAX_RETRIES + 1):
            passed, errors, duration = run_notebook(nb_path, cwd, label, attempt)
            total_duration += duration

            if passed:
                break

            # Check if errors are throttling-related (retryable)
            is_throttle = any(
                'ServiceUnavailable' in str(e) or 'ThrottlingException' in str(e) or 'Too many' in str(e)
                for e in errors
            )
            if not is_throttle or attempt == MAX_RETRIES:
                break

            print(f"  Throttling detected, waiting {RETRY_WAIT}s before retry...")
            time.sleep(RETRY_WAIT)

        results.append({
            "label": label,
            "notebook": nb_path,
            "passed": passed,
            "errors": errors,
            "duration_s": total_duration,
        })

        # If a notebook fails with non-throttle error, stop — later notebooks depend on it
        if not passed:
            is_throttle = any(
                'ServiceUnavailable' in str(e) or 'ThrottlingException' in str(e) or 'Too many' in str(e)
                for e in errors
            )
            if not is_throttle:
                print(f"\n⛔ Stopping — {label} failed with non-transient error")
                break

    # Generate report
    end_time = datetime.now(timezone.utc)
    total_passed = sum(1 for r in results if r['passed'])
    total_run = len(results)

    report = []
    report.append(f"# Workshop Notebook E2E Report")
    report.append(f"")
    report.append(f"**Date:** {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
    report.append(f"**Branch:** feature/agentcore-ondemand-eval")
    report.append(f"**Duration:** {(end_time - start_time).total_seconds():.0f}s")
    report.append(f"**Result:** {total_passed}/{total_run} passed")
    report.append(f"")

    for r in results:
        status = "✅" if r['passed'] else "❌"
        report.append(f"## {status} {r['label']}")
        report.append(f"- Notebook: `{r['notebook']}`")
        report.append(f"- Duration: {r['duration_s']:.0f}s")
        if r['errors']:
            report.append(f"- Errors:")
            for ename, evalue in r['errors']:
                report.append(f"  - {ename}: {evalue[:150]}")
        report.append(f"")

    report_text = "\n".join(report)

    with open(REPORT_PATH, 'w') as f:
        f.write(report_text)

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {total_passed}/{total_run} notebooks passed")
    print(f"  Report: {REPORT_PATH}")
    print(f"{'='*60}")

    return 0 if total_passed == total_run else 1


if __name__ == "__main__":
    sys.exit(main())
