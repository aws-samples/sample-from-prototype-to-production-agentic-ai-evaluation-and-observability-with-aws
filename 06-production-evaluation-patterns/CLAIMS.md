# Claims, Sources, and Reproducibility: Module 06 Classification READMEs

This document tracks the empirical claims made in `single-label-classification/README.md` and `multi-label-classification/README.md`, and notes which numbers are reproducible from artifacts, which are illustrative, and which would require a fresh run to re-verify.

This file exists so reviewers, contributors, and customers can quickly distinguish *measured* values from *example* values, and re-run the relevant experiments before citing any number externally.

## Single-Label Classification README

### Empirical claims grounded in artifacts

| Claim in README | Source artifact | Notes |
|---|---|---|
| 220 evaluation samples, 11 intent classes, balanced (20 per class) | `baseline_220.csv` | Stratified sample drawn from Bitext public dataset. Class distribution computed from the `bitext_label` column. The evaluation set is balanced on purpose so each class gets equal scrutiny; production traffic is typically skewed. |
| Accuracy 82.3%, Macro-F1 0.81 (Claude Sonnet zero-shot) | `baseline_220.csv` (predictions in `rater_A_sonnet46` column) | Reproducible by running `predicted == ground_truth` over the file. |
| Per-class F1 table (INVOICE 1.00, SUBSCRIPTION 0.98, PAYMENT 0.93, REFUND 0.91, CONTACT 0.91, ACCOUNT 0.82, FEEDBACK 0.79, CANCEL 0.74, ORDER 0.72, SHIPPING 0.60, DELIVERY 0.56) | `baseline_220.csv` | Computed via `sklearn.metrics.classification_report(digits=2)`. |
| Confusion matrix: 8 of 20 DELIVERY → SHIPPING, 6 of 20 ORDER → CANCEL | `confusion_matrix.csv` | Top two off-diagonal cells. |
| Sonnet–Haiku kappa 0.86, Bitext-Sonnet kappa 0.74 | `spotcheck_kappa.csv` (50 samples) | Computed via Cohen's kappa on the three label columns: `bitext_label`, `rater_A_sonnet46`, `rater_B_haiku45`. |

### Illustrative or pedagogical values

| Statement in README | Why it's illustrative |
|---|---|
| "Run each evaluation sample 3 times and report majority label plus stability rate" | Recommended practice. Not derived from a specific experiment in this repo. |
| "Changing class definition by one word can swing per-class F1 by 10+ points" | Common operational observation, not measured on the Bitext dataset specifically. Cite a literature reference if used externally. |
| "Below 0.6 means labels too noisy to trust" (kappa rule of thumb) | Standard Landis-Koch interpretation, widely cited in inter-rater agreement literature. Not calibrated for this dataset specifically. |
| Self-serve checklist 6 items + 3 escalation triggers | Editorial guidance. Thresholds (kappa < 0.7, F1 < 0.7, F1 < 0.5) are conservative defaults; teams should calibrate to their own cost structure. |

## Multi-Label Classification README

### Empirical claims grounded in artifacts

None. The multi-label README does not cite specific measurements. The motivating example (5-tag customer feedback message) is a constructed illustration, not a sample from a real dataset.

### Illustrative or pedagogical values

| Statement in README | Why it's illustrative |
|---|---|
| "My order arrived two weeks late and I was charged twice for it" feedback message + 5-tag ground truth set | Constructed example for teaching. No real dataset behind it. |
| Metric table (8 metrics) | Standard multi-label evaluation metrics; mathematical definitions are authoritative, but no measured values are shown. |
| Hierarchical group examples (`product:*`, `issue:*`, `sentiment:*`, `urgency:*`) | Schema designed for pedagogy. Real customer feedback systems typically have richer or different schemas. |
| Self-serve checklist 6 items | Editorial guidance. Thresholds (F1 < 0.6) are conservative defaults. |

## Reproducibility

To re-verify the single-label numbers from scratch:

```python
import pandas as pd
from sklearn.metrics import classification_report, cohen_kappa_score, confusion_matrix

# Aggregate metrics (220 samples)
df = pd.read_csv("baseline_220.csv")
print(classification_report(df["bitext_label"], df["rater_A_sonnet46"], digits=3))

# Confusion matrix
cm = confusion_matrix(df["bitext_label"], df["rater_A_sonnet46"], labels=sorted(df["bitext_label"].unique()))
print(cm)

# Kappa (50-sample spot check)
spot = pd.read_csv("spotcheck_kappa.csv")
print("Sonnet-Haiku kappa:",
      cohen_kappa_score(spot["rater_A_sonnet46"], spot["rater_B_haiku45"]))
print("Bitext-Sonnet kappa:",
      cohen_kappa_score(spot["bitext_label"], spot["rater_A_sonnet46"]))
```

Source data files:

- `baseline_220.csv`: 220 messages with `bitext_label` (ground truth) and `rater_A_sonnet46` (Claude Sonnet zero-shot prediction).
- `spotcheck_kappa.csv`: 50 messages with three label columns: `bitext_label`, `rater_A_sonnet46`, `rater_B_haiku45`.
- `confusion_matrix.csv`: precomputed confusion matrix.

These files live in this repo under `06-production-evaluation-patterns/objective/single-label-classification/data/` once contributors push them in a follow-up commit. If the `data/` directory is empty, the CSVs are available on request from the maintainers.

## Model versions

The Claude Sonnet predictions in `baseline_220.csv` and `rater_A_sonnet46` were produced with `global.anthropic.claude-sonnet-4-6` via Amazon Bedrock. The Claude Haiku predictions in `rater_B_haiku45` used `global.anthropic.claude-haiku-4-5`. Re-running with different model versions will produce different numbers; pin the model alias when reproducing.

## Disclaimer

The Bitext customer support dataset is public and licensed for research and education. The numbers in the README are intended as a teaching example, not as a benchmark or production performance claim. Customer-facing teams should run their own evaluations on their own data before drawing conclusions about real-world classifier behavior.
