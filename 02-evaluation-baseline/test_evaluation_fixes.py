#!/usr/bin/env python3
"""
Test script to validate Module 2 evaluation fixes
Tests the correct usage of strands-agents-evals v0.1.1 API
"""

import boto3
import json
import os
import sys

print("=" * 60)
print("Testing Module 2 Evaluation Fixes")
print("=" * 60)

# Setup environment
sys.path.insert(0, '../01-multi-agent-prototype/agents')
sys.path.insert(0, '../01-multi-agent-prototype/tools')

session = boto3.Session()
REGION = session.region_name or 'us-west-2'
os.environ['AWS_REGION'] = REGION

print(f"\nRegion: {REGION}")

# Test 1: Verify correct imports
print("\n1. Testing strands-evals imports...")
try:
    from strands_evals import Case, Experiment
    from strands_evals.evaluators import OutputEvaluator
    print("   ✓ Correct imports: Case, Experiment, OutputEvaluator")
except ImportError as e:
    print(f"   ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Create Case objects
print("\n2. Testing Case object creation...")
try:
    test_case = Case(
        name="test-001",
        input="What is the status of order ORD-2024-10002?",
        expected_output="Order shipped",
        metadata={
            'category': 'order_inquiry',
            'expected_agent': 'order_agent'
        }
    )
    print(f"   ✓ Case created: {test_case.name}")
except Exception as e:
    print(f"   ✗ Case creation failed: {e}")
    sys.exit(1)

# Test 3: Create evaluator with rubric
print("\n3. Testing OutputEvaluator creation...")
try:
    evaluator = OutputEvaluator(
        rubric="""Evaluate if the response addresses the query.

Score 1.0: Fully addresses query
Score 0.5: Partially addresses query
Score 0.0: Does not address query

Respond with JSON: {"score": float, "reasoning": string}"""
    )
    print("   ✓ OutputEvaluator created with rubric")
except Exception as e:
    print(f"   ✗ Evaluator creation failed: {e}")
    sys.exit(1)

# Test 4: Create Experiment with evaluators list
print("\n4. Testing Experiment creation...")
try:
    experiment = Experiment(
        cases=[test_case],
        evaluators=[evaluator]  # Must be a list!
    )
    print("   ✓ Experiment created with evaluators=[evaluator]")
except Exception as e:
    print(f"   ✗ Experiment creation failed: {e}")
    sys.exit(1)

# Test 5: Create task function
print("\n5. Testing task function...")
try:
    from orchestrator import MultiAgentCustomerService

    # Get SSM parameters
    ssm = boto3.client('ssm', region_name=REGION)
    try:
        os.environ['ORDERS_TABLE_NAME'] = ssm.get_parameter(Name='ecommerce-workshop-orders-table')['Parameter']['Value']
        os.environ['ACCOUNTS_TABLE_NAME'] = ssm.get_parameter(Name='ecommerce-workshop-accounts-table')['Parameter']['Value']
        os.environ['PRODUCTS_TABLE_NAME'] = ssm.get_parameter(Name='ecommerce-workshop-products-table')['Parameter']['Value']
    except Exception as e:
        print(f"   ⚠ SSM parameters not available, using defaults")
        os.environ['ORDERS_TABLE_NAME'] = 'ecommerce-workshop-orders'
        os.environ['ACCOUNTS_TABLE_NAME'] = 'ecommerce-workshop-accounts'
        os.environ['PRODUCTS_TABLE_NAME'] = 'ecommerce-workshop-products'

    customer_service = MultiAgentCustomerService(region=REGION)

    def run_customer_service_task(case: Case) -> str:
        """Task function that runs a test case through the multi-agent system."""
        try:
            response = customer_service.chat(case.input)
            return str(response)
        except Exception as e:
            return f"Error: {str(e)}"

    print("   ✓ Task function defined")
    print("   ✓ Customer service instance created")
except Exception as e:
    print(f"   ✗ Task function setup failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Run evaluation (full end-to-end)
print("\n6. Testing full evaluation workflow...")
try:
    print("   Running evaluation on test case...")
    report = experiment.run_evaluations(run_customer_service_task)
    print("   ✓ Evaluation completed successfully")

    # Test result extraction
    if hasattr(report, 'results') and len(report.results) > 0:
        result = report.results[0]
        if hasattr(result, 'eval_output') and result.eval_output:
            score = result.eval_output.get('score', 0.0)
            reasoning = result.eval_output.get('reasoning', '')
            print(f"   ✓ Score extracted: {score}")
            print(f"   ✓ Reasoning present: {len(reasoning)} chars")
        else:
            print("   ⚠ Warning: eval_output not in expected format")
    else:
        print("   ⚠ Warning: No results in report")

except Exception as e:
    print(f"   ✗ Evaluation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Load evaluation dataset
print("\n7. Testing evaluation dataset loading...")
try:
    with open('evaluation_dataset.json', 'r') as f:
        eval_data = json.load(f)

    print(f"   ✓ Loaded {len(eval_data['test_cases'])} test cases")

    # Convert to Case objects
    test_cases = []
    for tc in eval_data['test_cases'][:3]:  # Just first 3 for testing
        case = Case(
            name=tc['id'],
            input=tc['input'],
            expected_output=tc.get('ground_truth', ''),
            metadata={
                'category': tc['category'],
                'expected_agent': tc.get('expected_agent'),
                'expected_tools': tc.get('expected_tools', [])
            }
        )
        test_cases.append(case)

    print(f"   ✓ Converted {len(test_cases)} test cases to Case objects")
except Exception as e:
    print(f"   ✗ Dataset loading failed: {e}")
    sys.exit(1)

# Test 8: Test custom evaluators
print("\n8. Testing custom evaluators...")
try:
    from custom_evaluators import (
        RoutingAccuracyEvaluator,
        PolicyComplianceEvaluator,
        ResponseQualityEvaluator,
        CustomerSatisfactionEvaluator
    )

    routing_evaluator = RoutingAccuracyEvaluator()
    policy_evaluator = PolicyComplianceEvaluator()
    quality_evaluator = ResponseQualityEvaluator()
    satisfaction_evaluator = CustomerSatisfactionEvaluator()

    print("   ✓ All 4 custom evaluators imported and created")

    # Test that they can be used in Experiment
    test_experiment = Experiment(
        cases=[test_cases[0]],
        evaluators=[routing_evaluator]
    )
    print("   ✓ Custom evaluator works with Experiment")

except Exception as e:
    print(f"   ✗ Custom evaluator test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 9: Test helper function for score extraction
print("\n9. Testing score extraction helper...")
try:
    def extract_scores_from_report(report):
        """Extract scores from evaluation report"""
        scores = []
        for result in report.results:
            if hasattr(result, 'eval_output') and result.eval_output:
                score = result.eval_output.get('score', 0.0)
                scores.append(float(score) if score is not None else 0.0)
            else:
                scores.append(0.0)
        return scores

    scores = extract_scores_from_report(report)
    print(f"   ✓ Extracted {len(scores)} scores from report")
    print(f"   ✓ Score values: {scores}")
except Exception as e:
    print(f"   ✗ Score extraction failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL EVALUATION TESTS PASSED")
print("=" * 60)
print("\nKey validations:")
print("  ✓ Correct API imports (Experiment, Case)")
print("  ✓ Experiment takes evaluators as list")
print("  ✓ Task function signature correct (Case -> str)")
print("  ✓ End-to-end evaluation workflow works")
print("  ✓ Custom evaluators compatible with API")
print("  ✓ Score extraction from reports works")
print("\nModule 2 evaluation notebook is ready to use!")
