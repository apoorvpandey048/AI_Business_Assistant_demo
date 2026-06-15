#!/usr/bin/env bash
# Provider validation runner (sprint §13.9). Runs the full suite under one provider with
# cache disabled (real, live measurements) and copies the trust report per-provider.
#
#   bash scripts/run_provider_eval.sh openai       # uses repo .env (gpt-4o, openai embeddings)
#   bash scripts/run_provider_eval.sh ollama       # qwen2.5:7b-instruct on the local server
#
# For ollama it overrides the three ABA_MODEL_* (the repo .env pins gpt-4o, which would
# otherwise win) and uses OpenAI embeddings for parity + low RAM (see embedding-strategy.md).
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null
LABEL="${1:?usage: run_provider_eval.sh <openai|ollama>}"
LOG="/tmp/eval_${LABEL}"
export ABA_REFERENCE_DATE=2026-06-08 ABA_CACHE_FIRST=false ABA_LLM_CACHE_WRITE=false
export OLLAMA_HOST=127.0.0.1:11434

if [ "$LABEL" = "ollama" ]; then
  export ABA_PROVIDER=ollama
  M="${ABA_OLLAMA_MODEL:-qwen2.5:7b-instruct}"
  export ABA_MODEL_GENERATION="$M" ABA_MODEL_ROUTER="$M" ABA_MODEL_SQL="$M"
  export ABA_EMBEDDING_BACKEND="${ABA_EMBEDDING_BACKEND:-openai}"
else
  export ABA_PROVIDER=openai
fi

echo "########## $LABEL ##########"
python -c "from app.config import get_settings as g;from app.llm.client import get_llm;s=g();st=get_llm().provider_status();print('provider',s.resolved_provider,'gen',s.model_generation,'health',st.health,'|',st.detail)"

echo "## eval.py";       python -u scripts/eval.py        > ${LOG}_eval.log 2>&1;  echo " exit=$?"; tail -3 ${LOG}_eval.log
echo "## eval_qa.py";    python -u scripts/eval_qa.py     > ${LOG}_qa.log 2>&1;    echo " exit=$?"; tail -5 ${LOG}_qa.log
echo "## eval_trust.py"; python -u scripts/eval_trust.py  > ${LOG}_trust.log 2>&1; echo " exit=$?"; tail -16 ${LOG}_trust.log
cp -f docs/trust-report.md docs/trust-report-${LABEL}.md 2>/dev/null
echo "## bench_provider.py"; python -u scripts/bench_provider.py --out data/eval/bench_${LABEL}.json > ${LOG}_bench.log 2>&1; echo " exit=$?"; tail -22 ${LOG}_bench.log
echo "########## $LABEL DONE ##########"
