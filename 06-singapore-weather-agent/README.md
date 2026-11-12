# Singapore Weather Agent

A Strands agent on Amazon Bedrock that answers questions about **weather forecasts** and
**haze / air quality** across Singapore, using live data from the National Environment
Agency (NEA). Its tools are served through an **AgentCore Gateway**, and a **Bedrock
Guardrail** protects it. It's evaluated against what NEA publishes on
[nea.gov.sg](https://www.nea.gov.sg/weather) and [haze.gov.sg](https://www.haze.gov.sg/),
and improved through logged **iterations**.

```
user ─► Strands Agent ─► Bedrock (Claude Sonnet) ◄── Bedrock Guardrail (input + output)
             │
             └─ MCP over HTTPS, SigV4 ─► AgentCore Gateway (AWS_IAM auth)
                                           └─► Lambda target "WeatherTools" ─► data.gov.sg (NEA feeds)

evaluate.py ─► agent answers  vs  nea.gov.sg + haze.gov.sg ground truth  (+ LLM judge)
```

## Quick start

```bash
cd 06-singapore-weather-agent
../.venv/bin/python -m pytest tests -q                       # offline unit tests

# Local tools only (no AWS resources besides Bedrock model access)
../.venv/bin/python weather_agent.py "Give me the weather across Singapore with haze conditions"

# Deploy Gateway + Lambda + Guardrail, then use them
../.venv/bin/python infra.py deploy
../.venv/bin/python infra.py smoke                           # list + call tools via the Gateway
../.venv/bin/python weather_agent.py --gateway --guardrail "Is it hazy in the west?"
```

The model defaults to `global.anthropic.claude-sonnet-5`; override it with
`WEATHER_AGENT_MODEL_ID`. The data.gov.sg API rate-limits anonymous callers. The client
caches responses for 60 seconds and retries when it's rate-limited. For higher limits, set
`DATA_GOV_SG_API_KEY` (in the Lambda's environment, if you're using the Gateway).

## Tools

The four tools have one implementation in `nea_data.py`, which uses only the standard
library. The local `@tool` wrappers and the Gateway Lambda both call it, so local and
Gateway runs return identical data.

| Tool | NEA feed | Use |
|---|---|---|
| `get_two_hour_forecast(area)` | `two-hr-forecast` | Nowcast for 47 towns; matches area names, tolerates typos, rejects ambiguous names |
| `get_24_hour_forecast()` | `twenty-four-hr-forecast` | Temperature, humidity and wind; per-region outlook by period |
| `get_four_day_outlook()` | `four-day-outlook` | Next 4 days |
| `get_haze_conditions(region)` | `psi`, `pm25` | 24-hr PSI with NEA descriptor, 1-hr PM2.5 band, health advisory |

The tools apply NEA's bands in code, not in the LLM. PSI: 0–50 Good, 51–100 Moderate,
101–200 Unhealthy, 201–300 Very Unhealthy, above 300 Hazardous. PM2.5: Band I is 0–55,
Band II is 56–150, Band III is 151–250, Band IV is 251 and above.

## AgentCore Gateway

`infra.py deploy` creates or updates each of the following. It's safe to run more than
once, and it writes resource ids to `infra_state.json`:

- **Lambda `sg-weather-tools`.** Runs `lambda_tools/weather_tools_lambda.py` with
  `nea_data.py`. It routes on `bedrockAgentCoreToolName`, strips the `WeatherTools___`
  prefix, and drops arguments that aren't in the tool's schema.
- **Gateway `sg-weather-gateway`.** An MCP gateway with the `AWS_IAM` authorizer. The agent
  signs requests with SigV4 using its own AWS credentials, so no Cognito setup is needed.
  To put this behind user login, switch to `CUSTOM_JWT` as module 03 does.
- **Gateway target `WeatherTools`.** Its tool schemas come from `nea_data.TOOL_SCHEMAS`.
  A unit test checks that they match the local tools.
- **IAM roles.** One for the Lambda (basic execution) and one for the Gateway, which may
  invoke only this Lambda.

`infra.py status` shows resource state. `infra.py destroy` removes everything.

## Guardrails

There are two layers:

1. **Bedrock Guardrail** (`config/guardrail.json`, attached through `BedrockModel(guardrail_id=...)`):
   - Content filters: sexual, violence, hate, insults and misconduct, all at HIGH.
   - Prompt-attack filter: HIGH, on input.
   - Denied topics: *MedicalTreatment* (dosages, diagnoses) and *PoliticalBlame* (blaming
     countries, sanctions).
   - PII: email and phone are anonymized; card numbers are blocked; a regex anonymizes
     Singapore NRIC/FIN numbers.
   - Word filter: the managed profanity list.

   If you edit the JSON and re-run `infra.py deploy`, it updates the guardrail and
   publishes a new version. The config hash is recorded so that unchanged configs don't
   create new versions.
2. **Prompt-level scope rules** (`config/prompts/system_v2.md`). The prompt keeps the agent
   to Singapore weather and haze. It forbids dosages, political blame and prompt
   disclosure, and tells the agent not to repeat personal data back.

## Evaluate against NEA

```bash
../.venv/bin/python evaluate.py                                  # local tools, prompt v2, LLM judge
../.venv/bin/python evaluate.py --variant v4-gateway-guardrail   # a named variant
../.venv/bin/python evaluate.py --gateway --guardrail --no-judge
../.venv/bin/python evaluate.py --cases haze_psi_pm25 safety_medical_dosage
```

The agent reads data.gov.sg. The evaluator reads a separate path: the JSON endpoints behind
the nea.gov.sg and haze.gov.sg pages (`nea_ground_truth.py`). There are 13 cases in
`eval_dataset.json`:

- **Quality (9).** Briefing, PSI/PM2.5, town nowcasts, 4-day outlook, 24-hour
  temperature and humidity, jogging advice, an unanswerable far-future PSI question, and a
  query containing PII.
- **Safety (4).** Prompt injection, a medical dosing request, political blame, and an
  off-topic coding request.

Each case is scored on:

1. **Tool selection.**
2. **Deterministic checks against NEA.** Per-region PSI and PM2.5, the PSI descriptor,
   temperature and humidity ranges, the town nowcast, the 4-day highs, and an NEA citation.
   Safety cases instead check for a refusal, no dosage, no system-prompt leak, and no
   echoed PII.
3. **No false block.** Every quality case fails if the guardrail blocked it.
4. **LLM judge.** Accuracy, completeness and helpfulness on a 1–5 scale, plus a
   hallucination flag. The judge sees the NEA ground truth *and* the agent's tool outputs,
   so it can tell a value that is unverifiable on nea.gov.sg from one that was invented.

**Freshness:** ground truth is captured before and after each run. For haze, the
evaluator reads the reading hour from the agent's tool output and compares against
haze.gov.sg's value *for that hour*. data.gov.sg usually publishes a few minutes earlier
than haze.gov.sg, so the evaluator waits up to 15 minutes for haze.gov.sg to catch up. If
the hour still isn't published, the check fails. It never passes by default.

## Iterations

`config/variants.json` defines a ladder of variants. Each one changes a single thing from
the one before:

| Variant | Change |
|---|---|
| `v1-local-baseline` | Local tools, prompt v1, no guardrail |
| `v2-local-prompt-v2` | Prompt v2 (scope and safety rules, "right now" recipe) |
| `v3-gateway` | Tools moved behind the AgentCore Gateway |
| `v4-gateway-guardrail` | Bedrock Guardrail attached |

```bash
../.venv/bin/python iterate.py                 # run all variants and compare
../.venv/bin/python iterate.py v4-gateway-guardrail
```

Each run is appended to `iterations/log.jsonl`. The comparison table is written to
`iterations/latest_comparison.md`. `ITERATIONS.md` records what each iteration found and
what was changed in response.

## Files

- `weather_agent.py`: agent factory (`open_agent(variant)`), local tools, Gateway SigV4 MCP client, CLI
- `nea_data.py`: data.gov.sg client, parsers, NEA bands, shared tool implementations and Gateway schemas
- `lambda_tools/weather_tools_lambda.py`: Gateway Lambda target
- `infra.py`: deploy, status, smoke and destroy for the Lambda, Gateway, target, Guardrail and IAM roles
- `config/guardrail.json`, `config/prompts/*.md`, `config/variants.json`: versioned behaviour config
- `nea_ground_truth.py`: ground truth from nea.gov.sg and haze.gov.sg
- `evaluate.py`, `eval_dataset.json`: evaluation runner and cases
- `iterate.py`, `iterations/`, `ITERATIONS.md`: iteration runner, log and write-up
