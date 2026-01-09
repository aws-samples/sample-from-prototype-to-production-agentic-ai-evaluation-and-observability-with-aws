# Module 2 Evaluation Fixes - Summary

## Issues Fixed

### 1. Incorrect strands-evals API Usage

**Problem:** The original notebook was calling `evaluator.evaluate()` directly, which is not the correct API.

**Root Cause:** The correct API (strands-agents-evals v0.1.1) uses:
- Create `Case` objects with test data
- Create `Experiment` objects with `evaluators` (plural) as a **list**
- Use `Experiment.run_evaluations(task_function)` method

**Solution:** Completely rewrote Module 2 notebook following the correct API patterns.

## Key Changes

### 1. Import Correct Classes
```python
from strands_evals import Case, Experiment
from strands_evals.evaluators import OutputEvaluator
```

### 2. Convert Test Cases to Case Objects
```python
test_cases = []
for tc in eval_data['test_cases']:
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
```

### 3. Create Task Function
```python
def run_customer_service_task(case: Case) -> str:
    """Task function that runs a test case through the multi-agent system."""
    try:
        response = customer_service.chat(case.input)
        return str(response)
    except Exception as e:
        return f"Error: {str(e)}"
```

### 4. One Experiment Per Set of Evaluators
**Important:** Pass `evaluators` (plural) as a **list**. To run multiple evaluations, create separate Experiment objects:

```python
# Goal Success Evaluation
goal_success_evaluator = OutputEvaluator(rubric="...")
goal_success_experiment = Experiment(
    cases=test_cases[:5],
    evaluators=[goal_success_evaluator]  # Pass as list!
)
goal_success_report = goal_success_experiment.run_evaluations(run_customer_service_task)

# Helpfulness Evaluation (separate Experiment)
helpfulness_evaluator = OutputEvaluator(rubric="...")
helpfulness_experiment = Experiment(
    cases=test_cases[:5],
    evaluators=[helpfulness_evaluator]  # Pass as list!
)
helpfulness_report = helpfulness_experiment.run_evaluations(run_customer_service_task)
```

### 5. Display Results
```python
# Display evaluation report
goal_success_report.run_display()

# Extract scores programmatically
def extract_scores_from_report(report):
    scores = []
    for result in report.results:
        if hasattr(result, 'eval_output') and result.eval_output:
            score = result.eval_output.get('score', 0.0)
            scores.append(float(score) if score is not None else 0.0)
        else:
            scores.append(0.0)
    return scores

scores = extract_scores_from_report(goal_success_report)
```

## Custom Evaluators

The custom evaluators in `custom_evaluators.py` are correctly implemented:
- They extend `OutputEvaluator`
- They use `OutputEvaluatorConfig` with proper rubrics
- They can be used the same way as built-in evaluators

Example:
```python
from custom_evaluators import RoutingAccuracyEvaluator

routing_evaluator = RoutingAccuracyEvaluator()
routing_experiment = Experiment(
    cases=test_cases[:5],
    evaluators=[routing_evaluator]  # Pass as list!
)
routing_report = routing_experiment.run_evaluations(run_customer_service_task)
routing_report.run_display()
```

## Evaluation Flow

```
Test Cases (JSON)
    ↓
Convert to Case objects
    ↓
Create Experiment with evaluators=[evaluator]
    ↓
Run evaluations with task function
    ↓
Get Report with scores and reasoning
    ↓
Extract scores for aggregation
```

## Module 2 Structure

1. **Step 1:** Setup - Create customer service instance
2. **Step 2:** Load evaluation dataset - Convert to Case objects
3. **Step 3:** Define task function - Wrapper for agent execution
4. **Step 4:** Run built-in evaluators - Goal Success & Helpfulness
5. **Step 5:** Run custom evaluators - Routing, Policy, Quality, Satisfaction
6. **Step 6:** Extract and analyze results - Create DataFrame
7. **Step 7:** Calculate baseline metrics - Average scores
8. **Step 8:** Define production thresholds - Alert levels
9. **Step 9:** Save results - For Module 3

## Testing

To test the fixed evaluation workflow:

```bash
cd 02-evaluation-baseline
jupyter notebook 02-evaluation-baseline.ipynb
```

Run all cells. Each evaluation will:
1. Run test cases through the multi-agent system
2. Evaluate responses using the specified rubric
3. Display scores and reasoning
4. Aggregate results for baseline metrics

## References

- [Strands Agents Samples - Built-in Evaluators](https://github.com/strands-agents/samples/blob/main/07-evals/01-built-in-evaluators/01-built-in-evaluators.ipynb)
- [Strands Agents Samples - Custom Evaluators](https://github.com/strands-agents/samples/tree/main/07-evals/02-custom-evaluators)
- [Strands Agents Samples - Multi-Agent Evaluation](https://github.com/strands-agents/samples/tree/main/07-evals/06-multi-agent-evaluation)

## Key Takeaways

1. ✅ **Always use Experiment.run_evaluations()** - Never call evaluator.evaluate() directly
2. ✅ **Pass evaluators as a list** - `evaluators=[evaluator]` not `evaluator=evaluator`
3. ✅ **One Experiment per set of evaluators** - Create separate experiments for multiple metrics
4. ✅ **Use Case objects** - Structured test case format with metadata
5. ✅ **Simple task functions** - Just wrap your agent execution
6. ✅ **OutputEvaluator is powerful** - Great for domain-specific metrics with rubrics
7. ✅ **Custom evaluators extend OutputEvaluator** - Same usage pattern as built-in ones
