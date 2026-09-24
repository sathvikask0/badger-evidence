#!/bin/sh
# Rerun the extraction benchmark with cheaper Claude models and score them (from the repository root).
#   export ANTHROPIC_API_KEY=...   (in your own terminal; never commit or paste it)
#   sh tools/compare_models.sh
# Cost: about $0.60 (Haiku 4.5) + $1.30 (Sonnet 5) for both benchmarks. Re-running skips finished tables.
set -e
[ -n "$ANTHROPIC_API_KEY" ] || { echo "Set ANTHROPIC_API_KEY first: export ANTHROPIC_API_KEY=..."; exit 1; }
for MODEL in claude-haiku-4-5-20251001 claude-sonnet-5; do
  for B in mtor_pi3ka gsk3b_jak2_parp1; do
    echo "== $MODEL on $B"
    uv run --with anthropic tools/llm_extract.py bench/$B --mode all --model $MODEL
  done
done
for B in mtor_pi3ka gsk3b_jak2_parp1; do
  for F in llm_all.json llm_all_haiku-4-5.json llm_all_sonnet-5.json; do
    echo "== score $F on $B"
    python3 tools/bench_eval.py bench/$B --method llm --llm-file $F | grep -E "precision|recall \(all"
  done
done
