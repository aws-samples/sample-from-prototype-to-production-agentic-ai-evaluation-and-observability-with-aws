# E-Commerce Agent Evaluation & Observability Workshop

## Architecture

Single **Product Catalog Agent** with RBAC (Role-Based Access Control).
No multi-agent orchestrator. No order agent. No account agent.

### Agent Tools (11 total via MCP)

**READ tools** (customer + admin): `search_products`, `get_product_details`, `check_inventory`, `get_product_recommendations`, `compare_products`, `get_return_policy`

**WRITE tools** (admin only): `create_product`, `update_product`, `delete_product`, `update_inventory`, `update_pricing`

### Evaluators (7 total)

`GoalSuccessEvaluator`, `HelpfulnessEvaluator`, `RBACComplianceEvaluator`, `ToolParameterAccuracyEvaluator`, `PolicyComplianceEvaluator`, `ResponseQualityEvaluator`, `CustomerSatisfactionEvaluator`

### Module Structure

| Module | Directory | Notebook(s) |
|--------|-----------|-------------|
| 00 Prerequisites | `00-prerequisites/` | `0-environment-setup.ipynb` |
| 01 Agent Prototype | `01-single-agent-prototype/` | `01-single-agent-prototype.ipynb` |
| 02 Evaluation | `02-evaluation-baseline/` | `02a-deepeval-evaluation.ipynb`, `02b-strands-evaluation.ipynb` |
| 03 Deployment | `03-production-deployment/` | `03-production-deployment.ipynb` |
| 04 Online Eval | `04-online-eval-observability/` | `04-agentcore-evaluations.ipynb` |
| 05 Batch Eval | `05-production-batch-evaluation/` | `05-production-batch-evaluation.ipynb` |

---

## Notebook Editing Guidelines

### Critical Rules

1. **Always read the full notebook before editing.** Use the Read tool on the `.ipynb` file to understand the cell structure, count, and content before making changes.

2. **The NotebookEdit tool writes `source` as a string, but the nbformat convention uses a list of strings.** After editing notebooks, run the validation script to normalize:
   ```bash
   ../.venv/bin/python validate_notebooks.py --fix
   ```

3. **Cell IDs require nbformat 4.5+.** If you add cells (via `edit_mode=insert`), ensure the notebook has `"nbformat_minor": 5`. The validation script handles this automatically with `--fix`.

4. **Never guess cell indices.** Read the notebook first to see how many cells exist and what each contains. Cell indices are 0-based.

5. **When inserting cells**, use `edit_mode=insert` with `cell_id` set to the ID of the cell *after which* the new cell should appear. Read the notebook to find the correct cell ID.

6. **When replacing cell content**, use the `cell_id` parameter to target the specific cell. This is safer than relying on cell indices which can shift.

7. **Preserve code cell outputs.** NotebookEdit only modifies the `source` field. Saved outputs in code cells remain untouched unless you explicitly clear them.

### Safe Editing Workflow

```
1. Read the .ipynb file (get full cell map)
2. Identify the exact cell(s) to modify (by cell_id or content)
3. Make targeted edits (prefer cell_id over index)
4. Run validation:  ../.venv/bin/python validate_notebooks.py
5. If issues found:  ../.venv/bin/python validate_notebooks.py --fix
6. Re-validate to confirm all clean
```

### Validation Script

`validate_notebooks.py` checks:
- **Structure**: Required JSON keys, cell types, metadata fields
- **Format**: nbformat validation (requires `nbformat` package in `../.venv/`)
- **Consistency**: Mixed string/list source formats
- **Stale references**: Old multi-agent architecture terms, removed tools, old evaluator names
- **Cell IDs**: Presence and uniqueness

```bash
# Validate all notebooks
../.venv/bin/python validate_notebooks.py

# Validate with verbose output (shows INFO items)
../.venv/bin/python validate_notebooks.py -v

# Fix source format and cell ID issues
../.venv/bin/python validate_notebooks.py --fix

# Validate a single notebook
../.venv/bin/python validate_notebooks.py --file 02-evaluation-baseline/02b-strands-evaluation.ipynb
```

---

## Terms to Avoid

These terms are from the old multi-agent architecture and should not appear in source cells:

- `order_agent`, `account_agent`, `OrderAgent`, `AccountAgent`
- `OrderTools___`, `AccountTools___`
- `get_order_status`, `track_shipment`, `get_customer_info`, `update_customer`
- `RoutingAccuracyEvaluator`, `routing_accuracy`
- `multi-agent orchestrator`, `three agents`, `3 agents`
- `01-multi-agent-prototype`
- `Knowledge Base`, `kb_name` (no Bedrock KB in this architecture)

The validation script checks for all of these automatically.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
