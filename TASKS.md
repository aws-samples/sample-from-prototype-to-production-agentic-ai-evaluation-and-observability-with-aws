# Workshop Improvement Tasks

## Overview

This document tracks the planned improvements to the Agentic AI Evaluation and Observability Workshop. Each task is described with context, scope, and open questions for discussion.

---

## Task 1: Build Presentation Deck (using `aws-slides` skill)

**Goal**: Create a customer-facing PowerPoint deck covering the workshop's evaluation and observability story.

**Scope**:
- Use the `aws-slides` skill to generate a production-ready `.pptx` with official AWS icons
- Cover the full narrative: agent prototype → evaluation → production deployment → observability → batch eval
- Include the Evaluation Pyramid (Layer 1 deterministic, Layer 2 LLM-as-judge, Layer 3 meta-eval)
- Include architecture diagrams: single agent with RBAC, AgentCore deployment, production eval pipeline

**Open questions**:
- Target audience: internal AWS SA deck, customer workshop intro, or conference talk?
- Desired length (number of slides)?
- Any specific AWS branding theme or color scheme preference?

---

## Task 2: Add On-Demand Evaluation to Lab 2 + Remove DeepEval (Module 02)

**Goal**: Simplify Module 02 by removing the optional DeepEval notebook (`02a`) and adding on-demand evaluation capability to the Strands evaluation notebook (`02b`).

**Current state**:
- `02a-deepeval-evaluation.ipynb` — DeepEval framework (currently marked optional)
- `02b-strands-evaluation.ipynb` — Core strands-evals path

**Proposed changes**:
- Remove or archive `02a-deepeval-evaluation.ipynb` (DeepEval)
- Add an on-demand evaluation section to `02b-strands-evaluation.ipynb` using AgentCore Evaluate API
- Update `README.md` and `CLAUDE.md` module table to reflect the removal of 02a

**Open questions**:
- Should `02a` be deleted entirely or moved to an `archive/` or `optional/` folder?
- What does "on-demand" mean here — triggering evaluation via the AgentCore Evaluate API on a specific conversation, or a new cell pattern for ad-hoc evaluation outside the full test suite?

---

## Task 3: Add CD Post-Deployment On-Demand Evaluation

**Goal**: Add a CI/CD gate that runs on-demand evaluation via AgentCore after a successful production deployment (post-deploy smoke test / quality gate).

**Scope**:
- Add a post-deployment evaluation step to the existing CI/CD section in `README.md`
- Potentially add a new script under `scripts/` (e.g., `run_postdeploy_eval.py`) that calls the AgentCore Evaluate API
- Hook into Module 03 (`03-production-deployment.ipynb`) — add a final cell demonstrating the post-deploy eval call
- Update the CI/CD Gates table to include a Gate 4: Post-Deploy On-Demand

**Proposed CI/CD gate**:

| Gate | Trigger | Level | Threshold | Purpose |
|------|---------|-------|-----------|---------|
| Gate 4 | Post-deploy | On-Demand (AgentCore) | Configurable | Smoke test deployed agent in production |

**Open questions**:
- Should this live in Module 03 as a notebook cell, in the `scripts/` dir as a standalone script, or both?
- What evaluators should run post-deploy? Subset of Module 02b evaluators (fast/cheap ones)?
- Should failures auto-rollback the deployment or just alert?

---

## Task 4: Add On-Demand Evaluation to Batch Eval (Module 05)

**Goal**: Augment `05-production-batch-evaluation.ipynb` with the ability to trigger on-demand evaluation for specific traces or conversations (not just scheduled batch runs).

**Current state**:
- Module 05 exports OTEL traces, classifies tool calls, and runs batch eval with strands-evals
- No ability to drill down and re-evaluate a single suspicious trace on-demand

**Proposed changes**:
- Add a section "On-Demand Re-evaluation" to `05-production-batch-evaluation.ipynb`
- Allow user to select a specific trace/conversation ID and trigger AgentCore Evaluate API for that record
- Show side-by-side: original batch score vs. on-demand re-evaluation score

**Open questions**:
- Is the on-demand evaluation here calling the same AgentCore Evaluate API as Tasks 2 and 3, or is this a different mechanism?
- Should this be a separate notebook (`05b-ondemand-eval.ipynb`) or a new section appended to `05`?

---

## Task 5: Review Workshop Notebooks

**Goal**: Audit all notebooks end-to-end for correctness, clarity, and consistency before the next workshop run.

**Notebooks to review**:

| Notebook | Directory | Review Focus |
|----------|-----------|--------------|
| `0-environment-setup.ipynb` | `00-prerequisites/` | Dependency installs, region config, IAM permissions |
| `01-single-agent-prototype.ipynb` | `01-single-agent-prototype/` | RBAC logic, MCP tool filtering, agent invocation |
| `02b-strands-evaluation.ipynb` | `02-evaluation-baseline/` | Evaluator definitions, test dataset, result analysis |
| `03-production-deployment.ipynb` | `03-production-deployment/` | AgentCore Runtime, Gateway, Identity setup steps |
| `04-agentcore-evaluations.ipynb` | `04-online-eval-observability/` | OTEL traces, CloudWatch dashboard, online eval config |
| `05-production-batch-evaluation.ipynb` | `05-production-batch-evaluation/` | Trace export, drift detection, feedback loop |

**Review checklist per notebook**:
- [ ] All code cells are executable in order (no hidden state dependencies)
- [ ] No stale references to old multi-agent architecture (run `validate_notebooks.py`)
- [ ] Markdown narrative matches the code (no doc/code drift)
- [ ] Prerequisites clearly stated at the top of each notebook
- [ ] Estimated run time per notebook is accurate
- [ ] Output cells are cleared (or representative outputs saved for reference)
- [ ] Links to AWS docs/services are valid

---

## Priority Discussion

Suggested priority order (to be confirmed):

1. **Task 5 (Notebook Review)** — foundational; other tasks build on clean notebooks
2. **Task 2 (Remove DeepEval + Add On-Demand to Lab 2)** — simplifies the critical path for participants
3. **Task 3 (CD Post-Deploy On-Demand Eval)** — extends the CI/CD story with production verification
4. **Task 4 (On-Demand in Batch Eval)** — closes the loop between production and offline evaluation
5. **Task 1 (Presentation Deck)** — can be parallelized with notebook work

---

## Notes

- "On-demand evaluation" across Tasks 2, 3, 4 likely refers to the **AgentCore Evaluate API** — we should confirm this is a single unified mechanism and design a consistent pattern across all three tasks.
- The `validate_notebooks.py` script should be run after every notebook edit.
- All on-demand eval additions should use `global.anthropic.claude-sonnet-4-6` as the judge model, consistent with the rest of the workshop.
