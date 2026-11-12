# Variant comparison: eval_dataset_haze_replay.json (2026-11-12 07:38)

| variant | change | cases | quality | safety | checks | accuracy | complete | helpful | halluc | guardrail blocks | false blocks | latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v5-local-prompt-v3 | Prompt v3: don't volunteer haze causes (the replay judge flagged them as unsupported) | 6/6 | 6/6 | 0/0 | 30/30 | 4.95 | 5.0 | 5.0 | 0 | 0 | 0 | 7.6 |
| v5-local-guardrail | Prompt v3 + guardrail v3 (narrowed MedicalTreatment topic), local tools for replay datasets | 6/6 | 6/6 | 0/0 | 30/30 | 4.95 | 4.95 | 4.89 | 0 | 0 | 0 | 8.4 |

- **v5-local-prompt-v3** failed: none
- **v5-local-guardrail** failed: none
