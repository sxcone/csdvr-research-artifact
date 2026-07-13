#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

: "${CSDVR_LLM_BASE_URL:?Set CSDVR_LLM_BASE_URL first}"
: "${CSDVR_LLM_MODEL_A:?Set CSDVR_LLM_MODEL_A first}"
: "${CSDVR_LLM_API_KEY:?Set CSDVR_LLM_API_KEY first}"

export CSDVR_LLM_RETRIES="${CSDVR_LLM_RETRIES:-4}"
export CSDVR_LLM_TIMEOUT="${CSDVR_LLM_TIMEOUT:-120}"
export CSDVR_LLM_REQUEST_DELAY="${CSDVR_LLM_REQUEST_DELAY:-0.35}"

LOG="sci_q34_v3/02_results/deepseek_v4_pipeline.log"
mkdir -p "$(dirname "$LOG")"

{
  echo "== C-SDVR DeepSeek v4 pipeline =="
  date
  echo "base_url=${CSDVR_LLM_BASE_URL}"
  echo "model_a=${CSDVR_LLM_MODEL_A}"
  echo "model_b=${CSDVR_LLM_MODEL_B:-}"
  echo "retries=${CSDVR_LLM_RETRIES}"
  echo "timeout=${CSDVR_LLM_TIMEOUT}"
  echo "request_delay=${CSDVR_LLM_REQUEST_DELAY}"

  echo
  echo "== Smoke: LLM-agent, all configured models =="
  python3 sci_q34_v3/01_experiments/run_llm_agent_validation_v4.py --smoke --smoke-all-models

  echo
  echo "== Smoke: postcondition generation, all configured models =="
  python3 sci_q34_v3/01_experiments/run_postcondition_generation_v4.py --smoke --smoke-all-models

  echo
  echo "== Smoke reports =="
  cat sci_q34_v3/02_results/llm_agent_validation_smoke_report_v4.md
  echo
  cat sci_q34_v3/02_results/postcondition_generation_smoke_report_v4.md

  echo
  echo "== Smoke gate: select stable model(s) for full run =="
  python3 - <<'PY'
import csv
from collections import defaultdict
from pathlib import Path

root = Path("sci_q34_v3/02_results")
agent = list(csv.DictReader((root / "llm_agent_validation_smoke_summary_v4.csv").open()))
pc = list(csv.DictReader((root / "postcondition_generation_smoke_summary_v4.csv").open()))

agent_ok = defaultdict(lambda: False)
for row in agent:
    if row["policy"] == "NoCheck":
        agent_ok[row["model"]] = float(row["invalid_json_rate"]) <= 0.25 and float(row["token_cost"]) > 0

pc_ok = {
    row["model"]: float(row["invalid_json_rate"]) <= 0.25 and float(row["token_cost"]) > 0
    for row in pc
}

models = []
for row in pc:
    model = row["model"]
    if agent_ok[model] and pc_ok.get(model, False):
        models.append(model)

seen = []
for model in models:
    if model not in seen:
        seen.append(model)

env_path = root / "deepseek_v4_selected_models.env"
if not seen:
    env_path.write_text("# no stable models selected\n")
    raise SystemExit(
        "No stable model passed smoke gate. Full run aborted. "
        "Check invalid_json_rate/token_cost in smoke summaries."
    )

lines = [f"export CSDVR_LLM_MODEL_A={seen[0]}"]
if len(seen) > 1:
    lines.append(f"export CSDVR_LLM_MODEL_B={seen[1]}")
else:
    lines.append("unset CSDVR_LLM_MODEL_B")
env_path.write_text("\n".join(lines) + "\n")
print("stable_models=" + ",".join(seen))
print(env_path)
PY
  source sci_q34_v3/02_results/deepseek_v4_selected_models.env
  echo "full_model_a=${CSDVR_LLM_MODEL_A}"
  echo "full_model_b=${CSDVR_LLM_MODEL_B:-}"

  echo
  echo "== Full: LLM-agent validation =="
  python3 sci_q34_v3/01_experiments/run_llm_agent_validation_v4.py

  echo
  echo "== Full: postcondition generation =="
  python3 sci_q34_v3/01_experiments/run_postcondition_generation_v4.py

  echo
  echo "== Full reports =="
  cat sci_q34_v3/02_results/llm_agent_validation_report_v4.md
  echo
  cat sci_q34_v3/02_results/postcondition_generation_report_v4.md

  echo
  echo "== Done =="
  date
} 2>&1 | tee "$LOG"
