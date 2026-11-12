#!/usr/bin/env python3
"""
Run the evaluation across agent variants and compare them (one change per iteration).

    python iterate.py                                   # every variant in config/variants.json
    python iterate.py v1-local-baseline v2-local-prompt-v2
    python iterate.py --no-judge

Each run's summary is appended to iterations/log.jsonl (tracked in git), and a
markdown comparison table is written to iterations/latest_comparison.md.
Variants that need AWS infrastructure are skipped until `python infra.py deploy` has run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from evaluate import load_variant, run_eval

HERE = Path(__file__).resolve().parent
OUT = HERE / "iterations"


def table(rows: list[dict]) -> str:
    cols = ["variant", "change", "cases", "quality", "safety", "checks", "accuracy", "complete", "helpful",
            "halluc", "guardrail blocks", "false blocks", "latency s"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        if r.get("skipped"):
            lines.append(f"| {r['variant']} | {r['change']} | skipped: {r['skipped']} |" + " |" * (len(cols) - 3))
            continue
        s, j = r["summary"], r["summary"].get("judge_mean", {})
        lines.append("| " + " | ".join(str(x) for x in [
            r["variant"], r["change"], s["cases_passed"], s["quality_passed"], s["safety_passed"], s["checks_passed"],
            j.get("accuracy", "-"), j.get("completeness", "-"), j.get("helpfulness", "-"), s.get("hallucinations", "-"),
            s["guardrail_interventions"], s["false_blocks"], s["mean_latency_s"]]) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("variants", nargs="*", help="Variant names (default: all)")
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    all_variants = json.loads((HERE / "config" / "variants.json").read_text())["variants"]
    variants = [load_variant(n) for n in args.variants] if args.variants else all_variants
    has_infra = (HERE / "infra_state.json").exists()

    OUT.mkdir(exist_ok=True)
    rows = []
    for v in variants:
        if (v["tools"] == "gateway" or v["guardrail"]) and not has_infra:
            rows.append({"variant": v["name"], "change": v["change"], "skipped": "run `python infra.py deploy`"})
            print(f"\nSkipping {v['name']}: needs AWS infrastructure (python infra.py deploy)")
            continue
        res = run_eval(v, use_judge=not args.no_judge)
        row = {"timestamp": datetime.now().isoformat(timespec="seconds"), "variant": v["name"], "change": v["change"],
               "config": {k: v[k] for k in ["prompt", "tools", "guardrail"]}, "summary": res["summary"],
               "failed_cases": [r["id"] for r in res["runs"] if not r["passed"]], "results_file": res["results_file"]}
        if v["guardrail"]:
            row["config"]["guardrail_version"] = json.loads((HERE / "infra_state.json").read_text()).get("guardrail_version")
        rows.append(row)
        with (OUT / "log.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    md = table(rows)
    failed = "\n".join(f"- **{r['variant']}** failed: {', '.join(r['failed_cases']) or 'none'}"
                       for r in rows if not r.get("skipped"))
    (OUT / "latest_comparison.md").write_text(f"# Variant comparison ({datetime.now():%Y-%m-%d %H:%M})\n\n{md}\n\n{failed}\n")
    print("\n" + md + "\n\n" + failed)


if __name__ == "__main__":
    main()
