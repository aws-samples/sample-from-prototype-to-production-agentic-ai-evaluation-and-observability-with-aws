# E-Commerce Agent Workshop - Quick Start Guide

**Workshop Status:** ✅ Ready to Run

---

## Prerequisites (5 minutes)

### 1. Install Dependencies
```bash
pip install -r 00-prerequisites/requirements.txt
```

**Key Packages:**
- `strands-agents>=0.1.0` - Agent framework
- `strands-agents-evals>=0.1.0` - Evaluation framework
- `boto3>=1.26.0` - AWS SDK

### 2. Setup Infrastructure
```bash
cd 00-prerequisites
python setup_infrastructure.py
```

**Creates:**
- ✅ 3 DynamoDB tables (orders, accounts, products)
- ✅ 150 sample records (orders, accounts, products)
- ✅ 3 SSM parameters for resource discovery

**Time:** ~2 minutes

### 3. Verify Setup
```bash
python verify_infrastructure.py
```

**Expected output:**
```
✅ All infrastructure checks PASSED!
✅ DynamoDB tables exist with data
✅ SSM parameters configured
✅ Bedrock model access verified
```

---

## Module 1: Multi-Agent Prototype (60 minutes)

### Run the Notebook
```bash
cd 01-multi-agent-prototype
jupyter notebook 01-multi-agent-prototype.ipynb
```

### What You'll Build

**Architecture:**
```
Orchestrator (Sonnet 4.5)
├── Order Agent (Haiku 4.5) - 4 tools
├── Product Agent (Haiku 4.5) - 6 tools
└── Account Agent (Haiku 4.5) - 3 tools
```

### Key Concepts
- ✅ Specialized agents with focused capabilities
- ✅ Cost optimization (43% savings with mixed models)
- ✅ Intelligent request routing
- ✅ Real tool implementations with DynamoDB

### Test Your Work
```bash
python test_notebook_fixes.py
```

---

## Module 2: Evaluation & Baseline (60 minutes)

### Run the Notebook
```bash
cd 02-evaluation-baseline
jupyter notebook 02-evaluation-baseline.ipynb
```

### What You'll Build

**Evaluation System:**
- ✅ 27 test cases across 6 categories
- ✅ 2 built-in evaluators (Goal Success, Helpfulness)
- ✅ 4 custom evaluators (Routing, Policy, Quality, Satisfaction)
- ✅ Baseline metrics for production monitoring

### Key Concepts
- ✅ LLM-as-judge evaluation pattern
- ✅ Custom evaluators with rubrics
- ✅ Baseline establishment
- ✅ Production threshold definition

### Test Your Work
```bash
python test_evaluation_fixes.py
```

---

## Sample Queries to Try

### Module 1 - Multi-Agent System

**Order Queries:**
```python
customer_service.chat("Where is my order ORD-2024-10002?")
customer_service.chat("I need to return order ORD-2024-10001")
customer_service.chat("Show me all orders for sarah.johnson@email.com")
```

**Product Queries:**
```python
customer_service.chat("Do you have wireless headphones under $100?")
customer_service.chat("Is product PROD-088 in stock?")
customer_service.chat("Show me gaming keyboards with RGB lighting")
```

**Account Queries:**
```python
customer_service.chat("What are the benefits of Gold membership?")
customer_service.chat("I need to reset my password for john.smith@email.com")
customer_service.chat("What's my account status?")
```

**Complex Multi-Agent:**
```python
customer_service.chat(
    "I want to return order ORD-2024-10001 because the headphones don't fit. "
    "Can you recommend a different pair?"
)
```

---

## Architecture Overview

### Cost-Optimized Design

**Model Selection:**
- **Orchestrator:** Claude Sonnet 4.5 ($3/$15 per 1M tokens)
  - Complex reasoning and intent classification
  - Global profile: `global.anthropic.claude-sonnet-4-5-20250929-v1:0`

- **Specialized Agents:** Claude Haiku 4.5 ($0.80/$4 per 1M tokens)
  - Focused domain tasks with tools
  - Global profile: `global.anthropic.claude-haiku-4-5-20251001-v1:0`

**Savings:** 43% vs all-Sonnet architecture

### Data Architecture

```
DynamoDB Tables:
├── ecommerce-workshop-orders (15 records)
│   └── Order history, tracking, returns
│
├── ecommerce-workshop-accounts (15 records)
│   └── Customer data, membership tiers
│
└── ecommerce-workshop-products (120 records)
    └── Product catalog with category GSI
```

---

## Common Issues & Solutions

### Issue: Package not found
```
ERROR: Could not find a version that satisfies the requirement strands-evals
```

**Solution:** Use correct package name:
```bash
pip install strands-agents-evals  # Not strands-evals
```

---

### Issue: ImportError in Module 2
```
ImportError: cannot import name 'Dataset' from 'strands_evals'
```

**Solution:** Use `Experiment` (correct for v0.1.1):
```python
from strands_evals import Case, Experiment  # Not Dataset
```

---

### Issue: Experiment TypeError
```
TypeError: Experiment() got an unexpected keyword argument 'evaluator'
```

**Solution:** Use `evaluators` (plural) as a list:
```python
experiment = Experiment(
    cases=test_cases,
    evaluators=[evaluator]  # Must be a list!
)
```

---

## Cleanup

### Remove All Workshop Resources
```bash
cd 00-prerequisites
python setup_infrastructure.py --cleanup
```

**Removes:**
- ✅ All DynamoDB tables
- ✅ All SSM parameters

**Note:** Bedrock model access is not removed (no resources to clean up)

---

## Validation & Testing

### Quick Validation
```bash
# Verify infrastructure
cd 00-prerequisites && python verify_infrastructure.py

# Test Module 1
cd ../01-multi-agent-prototype && python test_notebook_fixes.py

# Test Module 2
cd ../02-evaluation-baseline && python test_evaluation_fixes.py
```

### Expected Results
All three scripts should complete with:
```
✅ ALL TESTS PASSED
```

---

## Key Files Reference

### Documentation
- `README.md` - Workshop overview and architecture
- `WORKSHOP_VALIDATION_COMPLETE.md` - Complete validation report
- `EVALUATION_FIXES_SUMMARY.md` - Module 2 API usage guide
- `QUICK_START.md` - This file

### Notebooks
- `01-multi-agent-prototype/01-multi-agent-prototype.ipynb` - Module 1
- `02-evaluation-baseline/02-evaluation-baseline.ipynb` - Module 2

### Infrastructure
- `00-prerequisites/setup_infrastructure.py` - Setup automation
- `00-prerequisites/verify_infrastructure.py` - Validation script
- `00-prerequisites/sample_data/` - All synthetic data

### Code
- `01-multi-agent-prototype/tools/` - Tool implementations
- `01-multi-agent-prototype/agents/` - Agent implementations
- `02-evaluation-baseline/custom_evaluators.py` - Custom evaluators

---

## Learning Path

### Module 1 Learning Objectives
1. ✅ Build specialized agents with Strands SDK
2. ✅ Implement real tools using AWS services
3. ✅ Create intelligent orchestration layer
4. ✅ Understand cost optimization with mixed models

### Module 2 Learning Objectives
1. ✅ Use strands-agents-evals framework
2. ✅ Create custom evaluators with rubrics
3. ✅ Establish baseline metrics
4. ✅ Define production monitoring thresholds

---

## Time Estimates

| Activity | Time |
|----------|------|
| Prerequisites setup | 5 min |
| Module 1: Prototype | 60 min |
| Module 2: Evaluation | 60 min |
| **Total** | **~2 hours** |

---

## Support

### If You Need Help

1. **Check test scripts:**
   - All modules have test scripts to validate functionality
   - Run them if you encounter errors

2. **Review documentation:**
   - `EVALUATION_FIXES_SUMMARY.md` for Module 2 API help
   - `WORKSHOP_VALIDATION_COMPLETE.md` for comprehensive guide
   - Module-specific README files

3. **Common troubleshooting:**
   - Verify infrastructure with `verify_infrastructure.py`
   - Check AWS credentials are configured
   - Ensure correct region is set (default: us-west-2)

---

## What's Next?

After completing Modules 1 and 2, you'll have:

✅ **Working multi-agent system** with intelligent routing
✅ **Comprehensive evaluation framework** with 6 metrics
✅ **Baseline performance metrics** for production monitoring
✅ **Production-ready patterns** for agent development

**Future Modules (coming soon):**
- Module 3: Production Deployment
- Module 4: Monitoring & Observability

---

**Ready to start?** Run the prerequisites setup and jump into Module 1! 🚀

```bash
# Let's go!
cd 00-prerequisites
python setup_infrastructure.py
```
