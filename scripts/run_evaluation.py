#!/usr/bin/env python3
"""
Agent Evaluation Script — Extracted from Module 02b for CI/CD integration.

Usage:
    # Run all evaluations
    python scripts/run_evaluation.py

    # Run only deterministic checks (fast, zero LLM cost)
    python scripts/run_evaluation.py --level deterministic

    # Run specific categories with a pass threshold
    python scripts/run_evaluation.py --category adversarial,rbac_boundary --threshold 1.0

    # Run LLM-as-judge evaluations
    python scripts/run_evaluation.py --level llm-judge

    # Save results to file
    python scripts/run_evaluation.py --output eval_results.json
"""

import json
import sys
import argparse
import os
from pathlib import Path


def load_dataset(dataset_path: str) -> dict:
    """Load evaluation dataset."""
    with open(dataset_path) as f:
        return json.load(f)


def run_deterministic_checks(test_cases: list, responses: dict) -> list:
    """
    Run Layer 1 deterministic assertions on agent responses.
    
    Checks:
    - expected_output_contains: keywords that must appear
    - must_have_facts: key facts that must appear
    - expected_output_not_contains: forbidden content (adversarial)
    - expected_behavior: RBAC allow/deny validation
    """
    results = []
    
    for case in test_cases:
        case_id = case['id']
        response = responses.get(case_id, "")
        
        # Warn if response is empty (likely missing --responses file)
        if not response.strip():
            results.append({
                'test_case': case_id,
                'category': case['category'],
                'level': 'deterministic',
                'contains_pass': False,
                'facts_pass': False,
                'not_contains_pass': True,
                'behavior_pass': True,
                'overall_pass': False,
                'note': 'Empty response — provide --responses file with cached agent outputs'
            })
            continue
        
        response_lower = response.lower()
        
        # Check 1: expected_output_contains
        expected_contains = case.get('expected_output_contains', [])
        contains_pass = all(
            kw.lower() in response_lower for kw in expected_contains
        ) if expected_contains else True
        
        # Check 2: must_have_facts
        must_facts = case.get('must_have_facts', [])
        facts_pass = all(
            f.lower() in response_lower for f in must_facts
        ) if must_facts else True
        
        # Check 3: expected_output_not_contains (adversarial)
        not_contains = case.get('expected_output_not_contains', [])
        not_contains_pass = not any(
            nc.lower() in response_lower for nc in not_contains
        ) if not_contains else True
        
        # Check 4: RBAC behavior
        expected_behavior = case.get('expected_behavior', 'allow')
        admin_indicators = ["created", "updated", "deleted", "price changed", "inventory set"]
        if expected_behavior == "deny":
            behavior_pass = not any(ind.lower() in response_lower for ind in admin_indicators)
        else:
            behavior_pass = True
        
        overall = contains_pass and facts_pass and not_contains_pass and behavior_pass
        
        results.append({
            'test_case': case_id,
            'category': case['category'],
            'level': 'deterministic',
            'contains_pass': contains_pass,
            'facts_pass': facts_pass,
            'not_contains_pass': not_contains_pass,
            'behavior_pass': behavior_pass,
            'overall_pass': overall
        })
    
    return results


def run_llm_judge(test_cases: list, responses: dict, model_id: str = "global.anthropic.claude-sonnet-4-6") -> list:
    """
    Run Layer 2 LLM-as-judge evaluations.
    
    Requires: strands-agents-evals, boto3
    """
    try:
        from strands_evals import judge
    except ImportError:
        print("Warning: strands-agents-evals not installed. Skipping LLM judge.", file=sys.stderr)
        return []
    
    results = []
    evaluators = ['goal_success', 'helpfulness', 'tool_accuracy', 'rbac_compliance', 'response_quality']
    
    for case in test_cases:
        case_id = case['id']
        response = responses.get(case_id, "")
        
        for evaluator_name in evaluators:
            try:
                result = judge(
                    query=case['input'],
                    response=response,
                    expected_output=case.get('ground_truth', ''),
                    rubric=f"Evaluate {evaluator_name} on a scale of 0.0 to 1.0.",
                    model_id=model_id
                )
                score = result.score if hasattr(result, 'score') else 0.0
            except Exception as e:
                score = None
                print(f"  Warning: {evaluator_name} failed for {case_id}: {e}", file=sys.stderr)
            
            results.append({
                'test_case': case_id,
                'category': case['category'],
                'level': 'llm-judge',
                'evaluator': evaluator_name,
                'score': score
            })
    
    return results


def summarize_results(results: list, threshold: float = 0.7) -> dict:
    """Summarize evaluation results."""
    if not results:
        return {'total': 0, 'passed': 0, 'pass_rate': 0.0}
    
    deterministic = [r for r in results if r['level'] == 'deterministic']
    llm_judge = [r for r in results if r['level'] == 'llm-judge']
    
    summary = {
        'total_cases': len(set(r['test_case'] for r in results)),
        'threshold': threshold,
    }
    
    if deterministic:
        det_passed = sum(1 for r in deterministic if r['overall_pass'])
        summary['deterministic'] = {
            'total': len(deterministic),
            'passed': det_passed,
            'pass_rate': det_passed / len(deterministic)
        }
    
    if llm_judge:
        scores = [r['score'] for r in llm_judge if r['score'] is not None]
        passed = sum(1 for s in scores if s >= threshold)
        summary['llm_judge'] = {
            'total_evaluations': len(llm_judge),
            'valid_scores': len(scores),
            'mean_score': sum(scores) / len(scores) if scores else 0,
            'passed': passed,
            'pass_rate': passed / len(scores) if scores else 0
        }
    
    return summary


def main():
    parser = argparse.ArgumentParser(description='Run agent evaluation pipeline')
    parser.add_argument('--dataset', default='02-evaluation-baseline/evaluation_dataset.json',
                        help='Path to evaluation dataset')
    parser.add_argument('--responses', default=None,
                        help='Path to cached agent responses JSON (if not provided, runs agent)')
    parser.add_argument('--level', choices=['deterministic', 'llm-judge', 'all'], default='all',
                        help='Evaluation level to run')
    parser.add_argument('--category', default=None,
                        help='Comma-separated list of categories to evaluate')
    parser.add_argument('--threshold', type=float, default=0.7,
                        help='Pass/fail threshold for LLM judge scores')
    parser.add_argument('--model', default='global.anthropic.claude-sonnet-4-6',
                        help='Model ID for LLM judge')
    parser.add_argument('--output', default=None,
                        help='Output file for results JSON')
    parser.add_argument('--ci', action='store_true',
                        help='CI mode: exit with non-zero code if below threshold')
    
    args = parser.parse_args()
    
    # Load dataset
    dataset = load_dataset(args.dataset)
    test_cases = dataset['test_cases']
    
    # Filter by category
    if args.category:
        categories = [c.strip() for c in args.category.split(',')]
        test_cases = [tc for tc in test_cases if tc['category'] in categories]
    
    print(f"Evaluation dataset: {len(test_cases)} test cases")
    if args.category:
        print(f"Filtered categories: {args.category}")
    
    # Load or generate responses
    if args.responses:
        with open(args.responses) as f:
            responses = json.load(f)
    else:
        # Placeholder — in production, this would call the agent
        print("Note: No --responses file provided. Using empty responses for deterministic checks.")
        print("      For LLM-judge, provide cached responses or integrate agent invocation.")
        responses = {}
    
    all_results = []
    
    # Run deterministic checks
    if args.level in ('deterministic', 'all'):
        print("\n--- Layer 1: Deterministic Assertions ---")
        det_results = run_deterministic_checks(test_cases, responses)
        all_results.extend(det_results)
        
        passed = sum(1 for r in det_results if r['overall_pass'])
        total = len(det_results)
        rate = passed / total if total > 0 else 0
        print(f"Pass rate: {rate:.0%} ({passed}/{total})")
    
    # Run LLM judge
    if args.level in ('llm-judge', 'all'):
        print("\n--- Layer 2: LLM-as-Judge ---")
        judge_results = run_llm_judge(test_cases, responses, args.model)
        all_results.extend(judge_results)
    
    # Summarize
    summary = summarize_results(all_results, args.threshold)
    print(f"\n=== Summary ===")
    print(json.dumps(summary, indent=2))
    
    # Save results
    if args.output:
        output_data = {
            'summary': summary,
            'results': all_results,
            'config': {
                'dataset': args.dataset,
                'level': args.level,
                'category': args.category,
                'threshold': args.threshold,
                'model': args.model
            }
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to {args.output}")
    
    # CI mode: exit code based on pass rate
    if args.ci:
        det_summary = summary.get('deterministic', {})
        if det_summary and det_summary.get('pass_rate', 1.0) < args.threshold:
            print(f"\n❌ CI FAILED: Deterministic pass rate {det_summary['pass_rate']:.0%} < {args.threshold:.0%}")
            sys.exit(1)
        
        judge_summary = summary.get('llm_judge', {})
        if judge_summary and judge_summary.get('pass_rate', 1.0) < args.threshold:
            print(f"\n❌ CI FAILED: LLM judge pass rate {judge_summary['pass_rate']:.0%} < {args.threshold:.0%}")
            sys.exit(1)
        
        print("\n✅ CI PASSED")
        sys.exit(0)


if __name__ == '__main__':
    main()
