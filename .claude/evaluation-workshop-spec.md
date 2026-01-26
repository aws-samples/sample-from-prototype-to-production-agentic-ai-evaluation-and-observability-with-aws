# E-Commerce Agent Evaluation Workshop Specification

## Development Lifecycle Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        AGENT DEVELOPMENT LIFECYCLE                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘

 STAGE 1: PROTOTYPE              STAGE 2: PRODUCTION             STAGE 3: IMPROVEMENT
 (Local Development)             (AgentCore Deployment)          (Continuous Loop)
 ─────────────────────          ─────────────────────────       ─────────────────────────

 ┌─────────────────┐            ┌─────────────────────┐         ┌─────────────────────┐
 │ Build Agent     │            │ Deploy to AgentCore │         │ Analyze Failures    │
 │ Locally         │            │ with Observability  │         │ from Production     │
 └────────┬────────┘            └──────────┬──────────┘         └──────────┬──────────┘
          │                                │                               │
 ┌────────▼────────┐            ┌──────────▼──────────┐         ┌──────────▼──────────┐
 │ Evaluation      │            │ Online Eval:        │         │ Update Eval Dataset │
 │ Dataset         │            │ - strands-eval      │         │ - Add failing cases │
 │ (Ground Truth)  │            │ - AgentCore eval    │         │ - New ground truth  │
 └────────┬────────┘            └──────────┬──────────┘         └──────────┬──────────┘
          │                                │                               │
 ┌────────▼────────┐            ┌──────────▼──────────┐         ┌──────────▼──────────┐
 │ DeepEval        │            │ CloudWatch Logs     │         │ DeepEval Batch Eval │
 │ Offline Eval    │            │ & Observability     │         │ with Updated Dataset│
 └────────┬────────┘            └──────────┬──────────┘         └──────────┬──────────┘
          │                                │                               │
 ┌────────▼────────┐            ┌──────────▼──────────┐         ┌──────────▼──────────┐
 │ Results + Tags  │            │ Firehose → S3       │         │ Validate Improvement│
 │ Version Control │            │ (Data Export)       │         │ vs Baseline         │
 └────────┬────────┘            └──────────┬──────────┘         └──────────┬──────────┘
          │                                │                               │
 ┌────────▼────────┐            ┌──────────▼──────────┐         ┌──────────▼──────────┐
 │ Ready for       │────────────▶ Offline Analysis    │         │ Deploy Updated      │
 │ Production?     │            │ (DeepEval on S3)    │────────▶│ Agent to Production │
 └─────────────────┘            └─────────────────────┘         └─────────────────────┘
                                                                          │
                                         ◄────────────────────────────────┘
                                              (Continue Monitoring)
```

---

## Stage 1: Prototype & Offline Evaluation (Local)

### Objective
Build and validate the agent locally using a pre-built evaluation dataset with ground truth before deploying to production.

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 1: PROTOTYPE                            │
└─────────────────────────────────────────────────────────────────┘

  ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
  │   Agent      │     │  Evaluation  │     │    DeepEval      │
  │   Code       │     │  Dataset     │     │    Metrics       │
  │  (Local)     │     │  (JSON)      │     │                  │
  └──────┬───────┘     └──────┬───────┘     └────────┬─────────┘
         │                    │                      │
         └────────────────────┼──────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  DeepEval Runner  │
                    │  (Local Python)   │
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼────┐  ┌──────▼──────┐  ┌─────▼──────┐
     │ Agent       │  │ Eval        │  │ Experiment │
     │ Results     │  │ Results     │  │ Metadata   │
     │ (responses) │  │ (scores)    │  │ (tags)     │
     └──────┬──────┘  └──────┬──────┘  └─────┬──────┘
            │                │               │
            └────────────────┼───────────────┘
                             │
                    ┌────────▼────────┐
                    │  Version Control │
                    │  (Git/S3)        │
                    │  - experiment_v1 │
                    │  - experiment_v2 │
                    └─────────────────┘
```

### Evaluation Dataset Structure

```json
{
  "dataset_version": "1.0.0",
  "created_at": "2026-01-20T10:00:00Z",
  "description": "E-commerce agent baseline evaluation dataset",
  "test_cases": [
    {
      "id": "order_001",
      "category": "order_status",
      "difficulty": "easy",
      "input": "What's the status of order ORD-2024-10002?",
      "context": {
        "customer_id": "CUST-001",
        "order_exists": true
      },
      "ground_truth": {
        "expected_agent": "order_agent",
        "expected_tools": ["get_order_status"],
        "expected_response_contains": ["shipped", "tracking", "UPS"],
        "expected_behavior": "Agent should retrieve order status and provide tracking info"
      }
    }
  ]
}
```

### DeepEval Metrics for Prototype Stage

| Metric | Purpose | Threshold | Ground Truth Required |
|--------|---------|-----------|----------------------|
| **AnswerCorrectness** | Response matches ground truth | 0.70 | Yes |
| **ToolCorrectness** | Correct tools selected | 0.85 | Yes (expected_tools) |
| **RoutingAccuracy** | Correct agent delegation | 0.90 | Yes (expected_agent) |
| **AnswerRelevancy** | Response relevance to query | 0.70 | No |
| **Faithfulness** | Response grounded in context | 0.75 | No |
| **G-Eval (Helpfulness)** | Actionable and useful | 0.65 | No |

### Experiment Tracking Structure

```
experiments/
├── experiment_2026-01-20_v1/
│   ├── config.json              # Experiment configuration
│   ├── agent_config.json        # Agent parameters (model, prompts)
│   ├── dataset_version.txt      # Dataset version used
│   ├── agent_results/
│   │   ├── order_001.json       # Per-case agent output
│   │   ├── order_002.json
│   │   └── ...
│   ├── eval_results/
│   │   ├── summary.json         # Aggregated scores
│   │   ├── per_case.json        # Per-case eval scores
│   │   └── per_metric.json      # Per-metric breakdown
│   └── tags.json                # Experiment tags/metadata
│
├── experiment_2026-01-21_v2/    # New experiment after changes
│   └── ...
│
└── comparison_report.json       # Cross-experiment comparison
```

### Experiment Tags for Version Control

```json
{
  "experiment_id": "exp_2026-01-20_v1",
  "tags": {
    "agent_version": "1.0.0",
    "prompt_version": "baseline",
    "model_orchestrator": "claude-sonnet-4-5",
    "model_specialized": "claude-haiku-4-5",
    "dataset_version": "1.0.0",
    "hypothesis": "Baseline multi-agent with mixed models",
    "status": "completed"
  },
  "metrics_summary": {
    "answer_correctness": 0.72,
    "tool_correctness": 0.88,
    "routing_accuracy": 0.95,
    "overall_pass_rate": 0.78
  },
  "decision": "READY_FOR_PRODUCTION"
}
```

---

## Stage 2: Production Deployment & Online Evaluation

### Objective
Deploy validated agent to AgentCore with observability, run online evaluation with strands-eval/AgentCore eval, and export data to S3 for analysis.

### Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 2: PRODUCTION                                  │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   User Request   │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │    AgentCore     │
                              │    Runtime       │
                              │  (OTEL enabled)  │
                              └────────┬─────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
┌────────▼────────┐         ┌─────────▼─────────┐         ┌─────────▼─────────┐
│ strands-eval    │         │  AgentCore Eval   │         │  CloudWatch Logs  │
│ (Online)        │         │  (Built-in)       │         │  (Observability)  │
│                 │         │                   │         │                   │
│ - Goal Success  │         │ - HELPFULNESS     │         │ - otel-rt-logs    │
│ - Helpfulness   │         │ - CORRECTNESS     │         │ - X-Ray traces    │
│ - Routing       │         │ - SAFETY          │         │ - Metrics         │
│ - Policy        │         │ - GUARDRAILS      │         │                   │
└────────┬────────┘         └─────────┬─────────┘         └─────────┬─────────┘
         │                            │                             │
         └────────────────────────────┼─────────────────────────────┘
                                      │
                           ┌──────────▼──────────┐
                           │  CloudWatch Logs    │
                           │  (Unified Storage)  │
                           └──────────┬──────────┘
                                      │
                           ┌──────────▼──────────┐
                           │  Subscription Filter│
                           │  → Kinesis Firehose │
                           └──────────┬──────────┘
                                      │
                           ┌──────────▼──────────┐
                           │     S3 Bucket       │
                           │  (Parquet format)   │
                           │                     │
                           │ ├── traces/         │
                           │ ├── online_eval/    │
                           │ └── feedback/       │
                           └──────────┬──────────┘
                                      │
                           ┌──────────▼──────────┐
                           │  Offline Analysis   │
                           │  (DeepEval Batch)   │
                           └─────────────────────┘
```

### Online Evaluation Configuration

#### strands-eval Integration
```python
# Use existing custom evaluators from Module 2
from custom_evaluators import (
    RoutingAccuracyEvaluator,
    PolicyComplianceEvaluator,
    ResponseQualityEvaluator,
    CustomerSatisfactionEvaluator
)

# Configure for online evaluation
online_eval_config = {
    "sampling_rate": 1.0,  # 100% for workshop demo (10% in real production)
    "evaluators": [
        {"name": "goal_success", "type": "builtin"},
        {"name": "helpfulness", "type": "builtin"},
        {"name": "routing_accuracy", "type": "custom", "class": "RoutingAccuracyEvaluator"},
        {"name": "policy_compliance", "type": "custom", "class": "PolicyComplianceEvaluator"}
    ],
    "output": {
        "cloudwatch_namespace": "EcommerceAgent/OnlineEval",
        "log_group": "/ecommerce-agent/online-eval"
    }
}
```

#### AgentCore Built-in Evaluators
```python
# Enable AgentCore evaluation in runtime config
agentcore_eval_config = {
    "evaluators": [
        "ANSWER_HELPFULNESS",
        "ANSWER_CORRECTNESS",
        "ANSWER_COMPLETENESS",
        "SAFETY_HARMFUL_CONTENT",
        "GUARDRAIL_ADHERENCE"
    ],
    "sampling_rate": 1.0,
    "results_log_group": "/aws/bedrock-agentcore/evaluations/results"
}
```

### Data Pipeline: CloudWatch → Firehose → S3

```
CloudWatch Logs
├── /aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT
│   ├── otel-rt-logs                    ← Agent telemetry (traces)
│   └── aws/spans                       ← X-Ray spans
│
├── /ecommerce-agent/online-eval        ← strands-eval results
│
└── /aws/bedrock-agentcore/evaluations/results  ← AgentCore eval results
         │
         │ Subscription Filters
         ▼
    Kinesis Firehose
    ├── traces-stream      → S3: traces/year=YYYY/month=MM/day=DD/
    ├── strands-eval-stream → S3: online_eval/strands/year=.../
    └── agentcore-eval-stream → S3: online_eval/agentcore/year=.../
         │
         │ Transform to Parquet
         ▼
    S3: ecommerce-eval-{account}/
    ├── traces/
    ├── online_eval/
    │   ├── strands/
    │   └── agentcore/
    └── feedback/
```

### S3 Data Schema

**traces/** (Agent execution data)
```python
{
    "event_id": "string",
    "timestamp": "bigint",
    "session_id": "string",
    "user_input": "string",
    "agent_response": "string",
    "delegated_agent": "string",
    "tools_used": "array<string>",
    "latency_ms": "bigint",
    "input_tokens": "bigint",
    "output_tokens": "bigint"
}
```

**online_eval/strands/** (strands-eval results)
```python
{
    "eval_id": "string",
    "timestamp": "bigint",
    "session_id": "string",
    "metric_name": "string",
    "score": "double",
    "passed": "boolean",
    "reasoning": "string"
}
```

**online_eval/agentcore/** (AgentCore eval results)
```python
{
    "eval_id": "string",
    "timestamp": "bigint",
    "session_id": "string",
    "evaluator_type": "string",
    "score": "double",
    "result": "string"
}
```

### Offline Analysis on Production Data

```python
# Query S3 data with Athena for offline DeepEval batch evaluation
def collect_production_data_for_offline_eval(days=7):
    """Collect production traces for offline evaluation with DeepEval"""

    query = f"""
    SELECT
        t.session_id,
        t.user_input,
        t.agent_response,
        t.delegated_agent,
        t.tools_used,
        s.metric_name as strands_metric,
        s.score as strands_score,
        a.evaluator_type as agentcore_metric,
        a.score as agentcore_score
    FROM ecommerce_eval.traces t
    LEFT JOIN ecommerce_eval.strands_eval s ON t.session_id = s.session_id
    LEFT JOIN ecommerce_eval.agentcore_eval a ON t.session_id = a.session_id
    WHERE t.timestamp > {days_ago_timestamp(days)}
    """

    results = run_athena_query(query)
    return convert_to_deepeval_testcases(results)
```

---

## Stage 3: Continuous Improvement

### Objective
Identify failing cases from production, update evaluation dataset with new ground truth, re-evaluate, and deploy improved agent.

### Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      STAGE 3: CONTINUOUS IMPROVEMENT                         │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ STEP 1: IDENTIFY FAILURES                                               │
  └─────────────────────────────────────────────────────────────────────────┘

  S3 Data (traces + eval results)
           │
           ▼
  ┌─────────────────────┐
  │ Athena Query:       │
  │ - Low scores (<0.5) │
  │ - Failed evals      │
  │ - User complaints   │
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Failure Analysis    │
  │ Report              │
  │ - 15 routing fails  │
  │ - 8 policy errors   │
  │ - 5 tool mistakes   │
  └──────────┬──────────┘
             │
  ┌──────────▼──────────────────────────────────────────────────────────────┐
  │ STEP 2: UPDATE EVALUATION DATASET                                       │
  └─────────────────────────────────────────────────────────────────────────┘
             │
             ▼
  ┌─────────────────────┐     ┌─────────────────────┐
  │ Existing Dataset    │     │ New Failing Cases   │
  │ v1.0.0 (27 cases)   │  +  │ from Production     │
  │                     │     │ (28 new cases)      │
  └──────────┬──────────┘     └──────────┬──────────┘
             │                           │
             └───────────┬───────────────┘
                         │
                         ▼
             ┌─────────────────────┐
             │ Updated Dataset     │
             │ v1.1.0 (55 cases)   │
             │ + New Ground Truth  │
             └──────────┬──────────┘
                        │
  ┌─────────────────────▼───────────────────────────────────────────────────┐
  │ STEP 3: IMPROVE AGENT                                                   │
  └─────────────────────────────────────────────────────────────────────────┘
                        │
             ┌──────────▼──────────┐
             │ Root Cause Analysis │
             │ - Prompt gaps       │
             │ - Tool issues       │
             │ - Routing logic     │
             └──────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │ Update Agent        │
             │ - Improve prompts   │
             │ - Fix tool logic    │
             │ - Update routing    │
             └──────────┬──────────┘
                        │
  ┌─────────────────────▼───────────────────────────────────────────────────┐
  │ STEP 4: BATCH EVALUATION WITH DEEPEVAL                                  │
  └─────────────────────────────────────────────────────────────────────────┘
                        │
             ┌──────────▼──────────┐
             │ DeepEval Batch Run  │
             │ - Updated Dataset   │
             │ - Updated Agent     │
             │ - All metrics       │
             └──────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │ Compare vs Baseline │
             │ - v1.0 → v1.1       │
             │ - Score improvement │
             │ - Regression check  │
             └──────────┬──────────┘
                        │
                        ▼
             ┌─────────────────────┐
             │ Improvement Report  │
             │ +12% routing acc    │
             │ +8% policy comply   │
             │ No regressions      │
             └──────────┬──────────┘
                        │
  ┌─────────────────────▼───────────────────────────────────────────────────┐
  │ STEP 5: DEPLOY & MONITOR                                                │
  └─────────────────────────────────────────────────────────────────────────┘
                        │
             ┌──────────▼──────────┐
             │ Deploy Updated      │
             │ Agent to AgentCore  │
             │ (v1.1.0)            │
             └──────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │ Continue Online     │
             │ Monitoring          │
             │ (Stage 2 loop)      │
             └─────────────────────┘
```

### Failure Identification Queries

```sql
-- Find low-scoring interactions
SELECT
    t.session_id,
    t.user_input,
    t.agent_response,
    t.delegated_agent,
    s.metric_name,
    s.score,
    s.reasoning
FROM ecommerce_eval.traces t
JOIN ecommerce_eval.strands_eval s ON t.session_id = s.session_id
WHERE s.score < 0.5
  AND t.timestamp > date_add('day', -7, current_date)
ORDER BY s.score ASC
LIMIT 50;

-- Categorize failures by type
SELECT
    s.metric_name,
    COUNT(*) as failure_count,
    AVG(s.score) as avg_score
FROM ecommerce_eval.strands_eval s
WHERE s.score < 0.5
  AND s.timestamp > date_add('day', -7, current_date)
GROUP BY s.metric_name
ORDER BY failure_count DESC;

-- Find routing failures specifically
SELECT
    t.user_input,
    t.delegated_agent as actual_agent,
    s.reasoning
FROM ecommerce_eval.traces t
JOIN ecommerce_eval.strands_eval s ON t.session_id = s.session_id
WHERE s.metric_name = 'routing_accuracy'
  AND s.score < 0.5
LIMIT 20;
```

### Updated Dataset Structure

```json
{
  "dataset_version": "1.1.0",
  "created_at": "2026-01-27T10:00:00Z",
  "base_version": "1.0.0",
  "description": "Updated dataset with production failure cases",
  "changelog": [
    {
      "version": "1.1.0",
      "date": "2026-01-27",
      "changes": [
        "Added 15 routing failure cases from production",
        "Added 8 policy compliance edge cases",
        "Added 5 multi-agent complex queries",
        "Updated ground truth for return policy (30→45 days)"
      ]
    }
  ],
  "test_cases": [
    // Original 27 cases from v1.0.0
    // ...

    // New cases from production failures
    {
      "id": "prod_fail_001",
      "category": "routing_failure",
      "source": "production",
      "discovered_at": "2026-01-25T14:32:00Z",
      "original_session_id": "sess_abc123",
      "input": "I ordered a laptop but want to know if you have wireless mice",
      "context": {
        "multi_domain": true,
        "requires_both": ["order_agent", "product_agent"]
      },
      "ground_truth": {
        "expected_agent": "orchestrator",
        "expected_delegation": ["product_agent"],
        "expected_tools": ["search_products"],
        "expected_response_contains": ["wireless", "mouse", "mice"],
        "expected_behavior": "Should recognize product inquiry even with order context"
      },
      "failure_analysis": {
        "original_routing": "order_agent",
        "root_cause": "Orchestrator confused by 'ordered' keyword",
        "fix_applied": "Updated routing prompt to prioritize current intent"
      }
    }
  ]
}
```

### Improvement Validation

```python
def validate_improvement(baseline_experiment, improved_experiment):
    """Compare improved agent against baseline"""

    comparison = {
        "baseline": baseline_experiment["metrics_summary"],
        "improved": improved_experiment["metrics_summary"],
        "improvements": {},
        "regressions": [],
        "recommendation": None
    }

    for metric in baseline_experiment["metrics_summary"]:
        baseline_score = baseline_experiment["metrics_summary"][metric]
        improved_score = improved_experiment["metrics_summary"][metric]
        delta = improved_score - baseline_score

        comparison["improvements"][metric] = {
            "baseline": baseline_score,
            "improved": improved_score,
            "delta": delta,
            "delta_percent": (delta / baseline_score) * 100
        }

        if delta < -0.05:  # >5% regression
            comparison["regressions"].append(metric)

    # Decision logic
    if len(comparison["regressions"]) > 0:
        comparison["recommendation"] = "HOLD - Regressions detected"
    elif all(d["delta"] >= 0 for d in comparison["improvements"].values()):
        comparison["recommendation"] = "DEPLOY - All metrics improved or stable"
    else:
        comparison["recommendation"] = "REVIEW - Mixed results"

    return comparison
```

---

## Module Structure

```
ecommerce-agent-workshop/
│
├── 00-prerequisites/                    # Existing (unchanged)
│
├── 01-multi-agent-prototype/            # Existing (unchanged)
│
├── 02-evaluation-baseline/              # ENHANCED
│   ├── 02-evaluation-baseline.ipynb
│   ├── evaluation_dataset_v1.0.0.json   # Versioned dataset
│   ├── custom_evaluators.py             # strands-eval evaluators
│   ├── deepeval_config.py               # DeepEval configuration
│   ├── deepeval_metrics.py              # Custom DeepEval metrics
│   ├── experiment_tracker.py            # Experiment versioning
│   └── experiments/                     # Version-controlled results
│       └── .gitkeep
│
├── 03-production-deployment/            # ENHANCED
│   ├── 03-production-deployment.ipynb
│   ├── app.py
│   ├── online_eval_config.py            # strands-eval + AgentCore config
│   └── .bedrock_agentcore.yaml
│
├── 04-online-eval-observability/        # NEW MODULE
│   ├── 04-online-eval-observability.ipynb
│   ├── infrastructure/
│   │   ├── setup_data_pipeline.py       # Firehose, S3, Glue
│   │   └── cleanup_data_pipeline.py
│   ├── online_eval/
│   │   ├── strands_eval_wrapper.py      # Online strands-eval
│   │   └── agentcore_eval_config.json   # AgentCore evaluators
│   └── data_export/
│       ├── subscription_filters.json
│       └── firehose_config.json
│
├── 05-continuous-improvement/           # NEW MODULE
│   ├── 05-continuous-improvement.ipynb
│   ├── failure_analysis/
│   │   ├── identify_failures.py
│   │   ├── queries/
│   │   │   ├── low_scores.sql
│   │   │   ├── routing_failures.sql
│   │   │   └── policy_violations.sql
│   │   └── analysis_report_template.md
│   ├── dataset_updater/
│   │   ├── add_production_cases.py
│   │   ├── update_ground_truth.py
│   │   └── version_dataset.py
│   ├── improvement_validation/
│   │   ├── batch_eval_runner.py
│   │   ├── compare_experiments.py
│   │   └── generate_report.py
│   ├── improved_prompts/
│   │   ├── orchestrator_v2.py
│   │   ├── order_agent_v2.py
│   │   └── changelog.md
│   └── drift_scenarios.json
│
└── evaluation_datasets/                 # Centralized datasets
    ├── v1.0.0/
    │   ├── dataset.json
    │   └── README.md
    ├── v1.1.0/
    │   ├── dataset.json
    │   ├── changelog.md
    │   └── README.md
    └── schema.json
```

---

## Workshop Flow

### Module 2: Evaluation & Baseline (60 min) - ENHANCED

**Content:**
1. Introduction to DeepEval vs strands-eval
2. Configure DeepEval with custom Bedrock model
3. Run offline evaluation with ground truth dataset
4. Track experiments with tags and version control
5. Analyze results and determine production readiness

**Key Deliverables:**
- Experiment results stored with tags
- Baseline metrics established
- Go/No-Go decision for production

### Module 3: Production Deployment (60 min) - ENHANCED

**Content:**
1. Configure online evaluation with strands-eval
2. Enable AgentCore built-in evaluators
3. Deploy with observability enabled
4. Verify online eval results in CloudWatch

**Key Deliverables:**
- Agent deployed with online evaluation
- Evaluation results flowing to CloudWatch

### Module 4: Online Eval & Observability (45 min) - NEW

**Content:**
1. Set up data pipeline (Firehose → S3)
2. Configure subscription filters for eval results
3. Create Glue tables for Athena queries
4. Verify data in S3 (Parquet format)
5. Run sample Athena queries

**Key Deliverables:**
- Data pipeline operational
- Production data exported to S3
- Athena queries working

### Module 5: Continuous Improvement (60 min) - NEW

**Content:**
1. Query S3 for low-scoring interactions
2. Analyze failure patterns
3. Add failing cases to evaluation dataset
4. Update ground truth
5. Improve agent prompts
6. Run batch evaluation with DeepEval
7. Compare vs baseline
8. Deploy improved agent
9. Continue monitoring

**Key Deliverables:**
- Updated evaluation dataset (v1.1.0)
- Improved agent deployed
- Improvement metrics documented

---

## Summary

| Stage | Location | Eval Framework | Data Storage | Purpose |
|-------|----------|----------------|--------------|---------|
| **1. Prototype** | Local | DeepEval | Git/S3 (experiments/) | Validate before production |
| **2. Production** | AgentCore | strands-eval + AgentCore | CloudWatch → S3 | Monitor live traffic |
| **3. Improvement** | Local → AgentCore | DeepEval batch | Updated dataset | Fix failures, redeploy |

**Key Workflow:**
1. **Build** → **DeepEval offline** → **Ready?** → **Deploy**
2. **Monitor** → **strands/AgentCore online** → **Export to S3**
3. **Analyze failures** → **Update dataset** → **Improve** → **DeepEval batch** → **Redeploy**
4. **Repeat**
