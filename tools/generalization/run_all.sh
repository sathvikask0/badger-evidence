#!/bin/sh
# Run the whole generalization experiment (from the repository root):
#   sh tools/generalization/run_all.sh
# Uses the Apple GPU (MPS) on an M-series Mac, CUDA if present, else CPU. Needs uv (brew install uv).
set -e
D=bench/generalization
[ -f $D/chembl_train.csv ] || { echo "Run python3 tools/gen_fetch.py and python3 tools/gen_data.py first."; exit 1; }
RUN="uv run --python 3.11 --with chemprop==2.3.1 --with scikit-learn python"

echo "== 1/5 baseline (per-enzyme mean)";      $RUN tools/generalization/train.py $D null
echo "== 2/5 random forest (Morgan fingerprints)"; $RUN tools/generalization/train.py $D rf
echo "== 3/5 D-MPNN from scratch";             $RUN tools/generalization/train.py $D dmpnn --epochs 40
echo "== 4/5 CheMeleon fine-tuned";            $RUN tools/generalization/train.py $D chemeleon --epochs 25 --weights $D/chemeleon_mp.pt
echo "== 5/5 evaluation";                      $RUN tools/generalization/evaluate.py $D null rf dmpnn chemeleon
echo "Results: $D/results.json"
