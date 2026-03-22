#!/usr/bin/env python3
"""
Compare evaluation results against a baseline.

Usage:
    python scripts/compare_baseline.py --current eval_results.json --baseline baseline.json
    python scripts/compare_baseline.py --current eval_results.json --baseline baseline.json --max-regression 0.05
"""

import json
import sys
import argparse


def load_results(path: str) -> dict:
    """Load evaluation results."""
    with open(path) as f:
        return json.load(f)


def compare(current: dict, baseline: dict, max_regression: float = 0.05) -> dict:
    """Compare current results against baseline."""
    report = {
        'regressions': [],
        'improvements': [],
        'unchanged': [],
        'overall_pass': True
    }
    
    # Compare deterministic pass rates
    curr_det = current.get('summary', {}).get('deterministic', {})
    base_det = baseline.get('summary', {}).get('deterministic', {})
    
    if curr_det and base_det:
        curr_rate = curr_det.get('pass_rate', 0)
        base_rate = base_det.get('pass_rate', 0)
        delta = curr_rate - base_rate
        
        entry = {
            'metric': 'deterministic_pass_rate',
            'baseline': base_rate,
            'current': curr_rate,
            'delta': delta
        }
        
        if delta < -max_regression:
            entry['status'] = 'REGRESSION'
            report['regressions'].append(entry)
            report['overall_pass'] = False
        elif delta > max_regression:
            entry['status'] = 'IMPROVEMENT'
            report['improvements'].append(entry)
        else:
            entry['status'] = 'UNCHANGED'
            report['unchanged'].append(entry)
    
    # Compare LLM judge scores
    curr_judge = current.get('summary', {}).get('llm_judge', {})
    base_judge = baseline.get('summary', {}).get('llm_judge', {})
    
    if curr_judge and base_judge:
        curr_mean = curr_judge.get('mean_score', 0)
        base_mean = base_judge.get('mean_score', 0)
        delta = curr_mean - base_mean
        
        entry = {
            'metric': 'llm_judge_mean_score',
            'baseline': base_mean,
            'current': curr_mean,
            'delta': delta
        }
        
        if delta < -max_regression:
            entry['status'] = 'REGRESSION'
            report['regressions'].append(entry)
            report['overall_pass'] = False
        elif delta > max_regression:
            entry['status'] = 'IMPROVEMENT'
            report['improvements'].append(entry)
        else:
            entry['status'] = 'UNCHANGED'
            report['unchanged'].append(entry)
    
    # Per-category comparison
    curr_results = {r['test_case']: r for r in current.get('results', []) if r.get('level') == 'deterministic'}
    base_results = {r['test_case']: r for r in baseline.get('results', []) if r.get('level') == 'deterministic'}
    
    common_cases = set(curr_results.keys()) & set(base_results.keys())
    new_failures = []
    
    for case_id in common_cases:
        curr_pass = curr_results[case_id].get('overall_pass', True)
        base_pass = base_results[case_id].get('overall_pass', True)
        
        if base_pass and not curr_pass:
            new_failures.append(case_id)
    
    if new_failures:
        report['new_failures'] = new_failures
    
    return report


def main():
    parser = argparse.ArgumentParser(description='Compare eval results against baseline')
    parser.add_argument('--current', required=True, help='Current evaluation results')
    parser.add_argument('--baseline', required=True, help='Baseline evaluation results')
    parser.add_argument('--max-regression', type=float, default=0.05,
                        help='Maximum allowed regression (default: 0.05 = 5%%)')
    parser.add_argument('--ci', action='store_true',
                        help='CI mode: exit non-zero on regression')
    
    args = parser.parse_args()
    
    current = load_results(args.current)
    baseline = load_results(args.baseline)
    
    report = compare(current, baseline, args.max_regression)
    
    print("=== Evaluation Comparison Report ===\n")
    
    if report['improvements']:
        print("📈 Improvements:")
        for item in report['improvements']:
            print(f"  {item['metric']}: {item['baseline']:.3f} → {item['current']:.3f} (+{item['delta']:.3f})")
    
    if report['regressions']:
        print("📉 Regressions:")
        for item in report['regressions']:
            print(f"  {item['metric']}: {item['baseline']:.3f} → {item['current']:.3f} ({item['delta']:.3f})")
    
    if report['unchanged']:
        print("➡️  Unchanged:")
        for item in report['unchanged']:
            print(f"  {item['metric']}: {item['baseline']:.3f} → {item['current']:.3f}")
    
    if report.get('new_failures'):
        print(f"\n⚠️  New failures in {len(report['new_failures'])} cases:")
        for case_id in report['new_failures']:
            print(f"  - {case_id}")
    
    print(f"\nOverall: {'✅ PASS' if report['overall_pass'] else '❌ FAIL'}")
    print(f"Max allowed regression: {args.max_regression:.0%}")
    
    if args.ci and not report['overall_pass']:
        sys.exit(1)


if __name__ == '__main__':
    main()
